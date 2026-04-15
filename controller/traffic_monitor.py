# Import core POX controller modules

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.recoco import Timer

# For saving logs and stats

import json
import csv
import os
import time

log = core.getLogger() # Logger for printing info in terminal

# ─────────────────────────────────────────────
# BLOCKING CONFIG (To test Allowed vs Blocked)
# ─────────────────────────────────────────────

# Enable/disable blocking feature
ENABLE_BLOCKING = True

BLOCK_RULES = [
    ("10.0.0.1", "10.0.0.4"),
    ("10.0.0.4", "10.0.0.1")
]

# mac_to_port[dpid][mac] = port
mac_to_port = {}
history = []        # Stores past stats for graphing
event_log = []      # Stores events like spikes, blocking, etc.

# Previous values used to calculate rate (delta)
prev_total_bytes = 0
prev_total_packets = 0
prev_delta_bytes = 0

# ─────────────────────────────────────────────
# FILE STORAGE SETUP
# ─────────────────────────────────────────────

# Directory where logs are stored
DATA_DIR = os.path.expanduser("~/CN-Orange-PES1UG24CS330/sdn-traffic-monitor/data")
os.makedirs(DATA_DIR, exist_ok=True)

# File paths
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
SUMMARY_LOG = os.path.join(DATA_DIR, "traffic_log.csv")
FLOW_LOG = os.path.join(DATA_DIR, "flow_log.csv")

# CSV fields
SUMMARY_FIELDS = [
    "date", "timestamp", "session_id",
    "total_packets", "total_bytes", "active_flows",
    "top_talker", "alert"
]

FLOW_FIELDS = [
    "date", "timestamp", "session_id",
    "switch", "src", "dst", "packets", "bytes", "priority"
]

# Unique ID per run/session
SESSION_ID = time.strftime("%Y%m%d_%H%M%S")

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS (LOGGING)
# ─────────────────────────────────────────────

def _ensure_csv(path, fieldnames):
    """Create CSV file with header if it doesn't exist"""
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()


def append_summary(row):
    """Append overall traffic summary"""
    _ensure_csv(SUMMARY_LOG, SUMMARY_FIELDS)
    with open(SUMMARY_LOG, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=SUMMARY_FIELDS).writerow(row)


def append_flows(rows):
    """Append per-flow statistics"""
    if not rows:
        return
    _ensure_csv(FLOW_LOG, FLOW_FIELDS)
    with open(FLOW_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FLOW_FIELDS)
        for row in rows:
            w.writerow(row)


def save_stats(data):
    """Save latest snapshot as JSON (used by dashboard)"""
    tmp = STATS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STATS_FILE)


# ─────────────────────────────────────────────
#  PERIODIC STATS REQUEST
# ─────────────────────────────────────────────

def request_stats():
    """Ask all switches for flow statistics every 5 seconds"""
    for conn in core.openflow._connections.values():
        conn.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
    Timer(5, request_stats)


# ─────────────────────────────────────────────
#  SWITCH CONNECT EVENT
# ─────────────────────────────────────────────

def _handle_ConnectionUp(event):
    """Triggered when a switch connects to controller"""
    log.info("Switch connected: %s", event.dpid)
    mac_to_port.setdefault(event.dpid, {})

# ─────────────────────────────────────────────
#  PACKET HANDLING 
# ─────────────────────────────────────────────

def _handle_PacketIn(event):
    """
    Triggered when switch sends packet to controller
    This is where:
    - learning switch happens
    - blocking happens
    """

    packet = event.parsed
    if not packet.parsed:
        return

    dpid = event.connection.dpid
    in_port = event.port
    src = packet.src
    dst = packet.dst

    # learn source MAC first
    mac_to_port.setdefault(dpid, {})[src] = in_port

    ip = packet.find('ipv4')
    if ip:
        src_ip = str(ip.srcip)
        dst_ip = str(ip.dstip)

        #  BLOCKING LOGIC
        if ENABLE_BLOCKING and (src_ip, dst_ip) in BLOCK_RULES:
            log.info("BLOCKED traffic between %s and %s", src_ip, dst_ip)

            # Log event for dashboard
            event_log.append({
                "timestamp": time.strftime("%H:%M:%S"),
                "label": f"Blocked Event: {src_ip} -> {dst_ip}",
                "bytes": 0
            })
            event_log[:] = event_log[-50:]

            msg = of.ofp_flow_mod()
            msg.match.dl_type = 0x0800
            msg.match.nw_src = ip.srcip
            msg.match.nw_dst = ip.dstip
            msg.priority = 65535
            msg.hard_timeout = 30
            msg.idle_timeout = 10

            # no actions => drop
            event.connection.send(msg)
            return


    if dst in mac_to_port[dpid]:
        out_port = mac_to_port[dpid][dst]
        msg = of.ofp_flow_mod()
        msg.match.dl_src = src
        msg.match.dl_dst = dst
        msg.actions.append(of.ofp_action_output(port=out_port))
        msg.data = event.ofp
        event.connection.send(msg)
    else:
        msg = of.ofp_packet_out()
        msg.data = event.ofp
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        msg.in_port = in_port
        event.connection.send(msg)

# ─────────────────────────────────────────────
#  FLOW STATS PROCESSING
# ─────────────────────────────────────────────

def _handle_FlowStatsReceived(event):
    """
    Called when switch sends stats
    Used to:
    - compute traffic
    - detect spikes
    - log data
    """

    total_packets = 0
    total_bytes = 0
    active_flows = 0
    flow_rows = []

    global prev_total_bytes, prev_total_packets, prev_delta_bytes

    now = time.strftime("%H:%M:%S")
    date = time.strftime("%Y-%m-%d")
    dpid = event.connection.dpid

    for stat in event.stats:
        if not hasattr(stat, "packet_count") or stat.priority == 0:
            continue

        total_packets += stat.packet_count
        total_bytes += stat.byte_count
        active_flows += 1

        raw_src = getattr(stat.match, "dl_src", None)
        raw_dst = getattr(stat.match, "dl_dst", None)

        src_str = str(raw_src) if raw_src is not None else "unknown"
        dst_str = str(raw_dst) if raw_dst is not None else "unknown"

        if src_str != "unknown" and dst_str != "unknown":
            flow_rows.append({
                "switch": str(dpid),
                "src": src_str,
                "dst": dst_str,
                "packets": stat.packet_count,
                "bytes": stat.byte_count,
                "priority": stat.priority,
            })
    # Calculate traffic change
    delta_bytes = total_bytes - prev_total_bytes
    delta_packets = total_packets - prev_total_packets
    if delta_bytes < 0:
        delta_bytes = 0
    if delta_packets < 0:
        delta_packets = 0

    top_talker = "N/A"
    if flow_rows:
        top = max(flow_rows, key=lambda x: x["bytes"])
        top_talker = f"{top['src']} -> {top['dst']}"
    # Traffic classification
    if delta_bytes > 100_000_000:      # 100 MB
        alert = "High Traffic"
    elif delta_bytes > 100_000:        # 100 KB
        alert = "Moderate Traffic"
    else:
        alert = "Normal"
    
    prev_alert = history[-1].get("alert", "Normal") if history else "Normal"
    if alert != prev_alert:
        event_log.append({
            "timestamp": now,
            "label": f"-> {alert}",
            "bytes": total_bytes
        })
        event_log[:] = event_log[-50:]
    # Spike detection: detect sudden burst even if already High
    if prev_delta_bytes > 0:
        if delta_bytes > 1_000_000 and delta_bytes > prev_delta_bytes * 1.5:
            event_log.append({
                "timestamp": now,
                "label": f"Spike Detected ({delta_bytes / 1_000_000:.2f} MB in last 5s)",
                "bytes": total_bytes
            })
            event_log[:] = event_log[-50:]
    snapshot = {
        "timestamp": now,
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "active_flows": active_flows,
        "top_talker": top_talker,
        "alert": alert,
        "flows": flow_rows,
        "events": list(event_log),
        "delta_bytes": delta_bytes,
        "delta_packets": delta_packets,
    }

    history.append({
        "timestamp": now,
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "active_flows": active_flows,
        "alert": alert,
        "delta_bytes": delta_bytes,
        "delta_packets": delta_packets,
    })
    history[:] = history[-20:]
    snapshot["history"] = history

    save_stats(snapshot)

    append_summary({
        "date": date,
        "timestamp": now,
        "session_id": SESSION_ID,
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "active_flows": active_flows,
        "top_talker": top_talker,
        "alert": alert,
    })

    append_flows([
        {"date": date, "timestamp": now, "session_id": SESSION_ID, **row}
        for row in flow_rows
    ])
    prev_total_bytes = total_bytes
    prev_total_packets = total_packets
    prev_delta_bytes = delta_bytes
    log.info(
        "Stats: packets=%s bytes=%s flows=%s alert=%s saved_to=%s",
        total_packets, total_bytes, active_flows, alert, DATA_DIR
    )

# ─────────────────────────────────────────────
#  CONTROLLER START
# ─────────────────────────────────────────────

def launch():
    """Entry point when POX starts"""
    # Register event handlers
    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    core.openflow.addListenerByName("PacketIn", _handle_PacketIn)
    core.openflow.addListenerByName("FlowStatsReceived", _handle_FlowStatsReceived)

    # Start periodic stats polling
    Timer(5, request_stats)

    log.info("Traffic monitor started — session_id=%s data->%s", SESSION_ID, DATA_DIR)

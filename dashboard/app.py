import streamlit as st
import pandas as pd
import json
import os
import time

# ---------------------------------------------------------
# Streamlit page setup
# ---------------------------------------------------------
st.set_page_config(
    page_title="SDN Traffic Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)
# ---------------------------------------------------------
# CSS styling for the dashboard
# ---------------------------------------------------------
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [data-testid="stAppViewContainer"] {
      background-color: #F5F0E8;
      font-family: 'DM Sans', sans-serif;
  }
  [data-testid="stAppViewContainer"] { padding: 0; }
  [data-testid="block-container"] { padding: 2rem 2.5rem 2rem 2.5rem; }

  .dash-header {
      background: linear-gradient(135deg, #2E5B8A 0%, #3D7ABF 100%);
      border-radius: 16px;
      padding: 28px 36px;
      margin-bottom: 1.8rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
  }
  .dash-title {
      font-family: 'DM Serif Display', serif;
      font-size: 2rem;
      color: #F5F0E8;
      margin: 0;
      letter-spacing: -0.5px;
  }
  .dash-sub {
      color: #B8D4F0;
      font-size: 0.82rem;
      margin-top: 4px;
      font-weight: 300;
  }
  .status-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 6px;
      animation: pulse 2s infinite;
  }
  @keyframes pulse {
      0%,100% { opacity: 1; }
      50% { opacity: 0.4; }
  }

  .metric-card {
      background: #FFFDF7;
      border: 1px solid #E2D9C8;
      border-radius: 14px;
      padding: 20px 22px;
      text-align: center;
      box-shadow: 0 2px 8px rgba(46,91,138,0.07);
  }
  .metric-label {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: #8A7B6A;
      margin-bottom: 6px;
  }
  .metric-value {
      font-family: 'DM Serif Display', serif;
      font-size: 1.9rem;
      color: #2E5B8A;
      line-height: 1.1;
  }
  .metric-sub {
      font-size: 0.72rem;
      color: #A89880;
      margin-top: 4px;
  }

  .alert-low {
      background: #EAF4EA; border: 1px solid #8BC48B;
      border-radius: 10px; padding: 12px 18px;
      color: #2D6E2D; font-weight: 500; font-size: 0.88rem;
  }
  .alert-mid {
      background: #FFF7E6; border: 1px solid #F5B942;
      border-radius: 10px; padding: 12px 18px;
      color: #7A5200; font-weight: 500; font-size: 0.88rem;
  }
  .alert-high {
      background: #FDECEA; border: 1px solid #E57373;
      border-radius: 10px; padding: 12px 18px;
      color: #8B1A1A; font-weight: 500; font-size: 0.88rem;
  }

  .section-title {
      font-family: 'DM Serif Display', serif;
      font-size: 1.15rem;
      color: #3D4B5C;
      margin: 1.4rem 0 0.6rem 0;
      padding-bottom: 6px;
      border-bottom: 2px solid #D4C9B4;
  }

  .event-pill {
      display: inline-block;
      border-radius: 20px;
      padding: 3px 10px;
      font-size: 0.75rem;
      font-weight: 600;
      margin: 2px 3px;
  }

  .timeline-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 8px;
  }
  .timeline-dot {
      width: 12px; height: 12px;
      border-radius: 50%;
      margin-top: 3px;
      flex-shrink: 0;
  }
  .timeline-line {
      border-left: 2px solid #D4C9B4;
      margin-left: 5px;
      padding-left: 14px;
  }

  [data-testid="stDataFrame"] {
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #E2D9C8;
  }

  #MainMenu, footer, header { visibility: hidden; }
  [data-testid="stDecoration"] { display: none; }
</style>
""", unsafe_allow_html=True)
# ---------------------------------------------------------
# File paths
# These are the files created by the controller script.
# stats.json -> latest snapshot for live dashboard
# traffic_log.csv -> historical overall traffic logs
# flow_log.csv -> historical per-flow logs
# ---------------------------------------------------------
BASE_DIR   = os.path.expanduser("~/CN-Orange-PES1UG24CS330/sdn-traffic-monitor/data")
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
SUMMARY_LOG = os.path.join(BASE_DIR, "traffic_log.csv")
FLOW_LOG    = os.path.join(BASE_DIR, "flow_log.csv")

# ---------------------------------------------------------
# Streamlit session state initialization
# ---------------------------------------------------------
if "session_history" not in st.session_state:
    st.session_state.session_history = []
if "session_start" not in st.session_state:
    st.session_state.session_start = time.strftime("%H:%M:%S")
if "session_base_packets" not in st.session_state:
    st.session_state.session_base_packets = None    # first total packet count seen
if "session_base_bytes" not in st.session_state:
    st.session_state.session_base_bytes = None       # first total byte count seen
if "level_timeline" not in st.session_state:
    st.session_state.level_timeline = []          # stores transitions/spikes for session timeline
if "last_level" not in st.session_state:
    st.session_state.last_level = None
if "seen_spike_ts" not in st.session_state:
    st.session_state.seen_spike_ts = set()
# ---------------------------------------------------------
# Helper function:
# ---------------------------------------------------------
# Converts delta_bytes into traffic category
def traffic_level(delta_bytes):
    if delta_bytes < 100_000:
        return "low", "#2D6E2D", "🟢 Low Traffic"
    elif delta_bytes < 100_000_000:
        return "mid", "#7A5200", "🟡 Moderate Traffic"
    else:
        return "high", "#8B1A1A", "🔴 High Traffic Detected"
# Converts raw byte values into readable format
def fmt_bytes(b):
    if b >= 1_000_000_000:
        return f"{b/1_000_000_000:.2f} GB"
    elif b >= 1_000_000:
        return f"{b/1_000_000:.2f} MB"
    elif b >= 1_000:
        return f"{b/1_000:.1f} KB"
    return f"{b} B"

# ---------------------------------------------------------
# Dashboard header
# ---------------------------------------------------------

st.markdown(f"""
<div class="dash-header">
  <div>
    <div class="dash-title">SDN Traffic Monitor - Made by Prakruti Prasanna Bhat</div>
    <div class="dash-sub">Software-Defined Networking · POX Controller · Mininet Topology</div>
  </div>
  <div style="text-align:right; color:#B8D4F0; font-size:0.8rem;">
    <span class="status-dot" style="background:#7EE8A2;"></span>Live · Session started {st.session_state.session_start}
  </div>
</div>
""", unsafe_allow_html=True)
# Create two tabs:
# 1. Live Dashboard -> current live monitoring
# 2. Historical Data -> data stored across runs
tab_live, tab_history = st.tabs(["Live Dashboard", "Historical Data"])

# =========================================================
# Historical Tab
# Shows previously saved traffic logs from CSV files
# =========================================================

with tab_history:
    st.markdown('<div class="section-title">Persisted Traffic Log</div>', unsafe_allow_html=True)

    if not os.path.exists(SUMMARY_LOG):
        st.markdown('<div class="alert-mid">No historical data yet — run the controller first to start logging.</div>', unsafe_allow_html=True)
    else:
        df_hist = pd.read_csv(SUMMARY_LOG)
        df_hist["bytes_mb"] = df_hist["total_bytes"] / 1_000_000

        sessions = df_hist["session_id"].unique().tolist()
        selected = st.multiselect(
            "Filter by session (leave blank for all)",
            options=sessions, default=[], placeholder="All sessions"
        )
        df_view = df_hist[df_hist["session_id"].isin(selected)] if selected else df_hist

        h1, h2, h3, h4 = st.columns(4)
        with h1:
            st.markdown(f'''<div class="metric-card">
                <div class="metric-label">Total Snapshots</div>
                <div class="metric-value">{len(df_view):,}</div>
                <div class="metric-sub">poll cycles logged</div>
            </div>''', unsafe_allow_html=True)
        with h2:
            st.markdown(f'''<div class="metric-card">
                <div class="metric-label">Sessions Recorded</div>
                <div class="metric-value">{df_view["session_id"].nunique()}</div>
                <div class="metric-sub">distinct runs</div>
            </div>''', unsafe_allow_html=True)
        with h3:
            peak = df_view["total_bytes"].max() if len(df_view) else 0
            st.markdown(f'''<div class="metric-card">
                <div class="metric-label">Peak Bytes</div>
                <div class="metric-value">{fmt_bytes(int(peak))}</div>
                <div class="metric-sub">single snapshot max</div>
            </div>''', unsafe_allow_html=True)
        with h4:
            high_count = len(df_view[df_view["alert"] == "High Traffic"])
            st.markdown(f'''<div class="metric-card">
                <div class="metric-label">High Traffic Events</div>
                <div class="metric-value" style="color:#8B1A1A">{high_count}</div>
                <div class="metric-sub">threshold breaches</div>
            </div>''', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Bytes Over All Recorded Time</div>', unsafe_allow_html=True)
        st.area_chart(df_view.reset_index(drop=True)["bytes_mb"], color="#3D7ABF", height=240)
        st.caption("Each point = one 5-second poll cycle.")

        st.markdown('<div class="section-title">Traffic Level Breakdown</div>', unsafe_allow_html=True)
        alert_counts = df_view["alert"].value_counts().reset_index()
        alert_counts.columns = ["Level", "Count"]
        st.dataframe(alert_counts, width="stretch", hide_index=True)

        st.markdown('<div class="section-title">Raw Log</div>', unsafe_allow_html=True)
        st.dataframe(
            df_view[["date","timestamp","session_id","total_packets",
                     "total_bytes","active_flows","alert","top_talker"]],
            width="stretch", hide_index=True
        )

        if os.path.exists(FLOW_LOG):
            st.markdown('<div class="section-title">Persisted Flow Log</div>', unsafe_allow_html=True)
            df_flows_hist = pd.read_csv(FLOW_LOG)
            if selected:
                df_flows_hist = df_flows_hist[df_flows_hist["session_id"].isin(selected)]
            df_flows_hist["bytes_fmt"] = df_flows_hist["bytes"].apply(fmt_bytes)
            st.dataframe(
                df_flows_hist[["date","timestamp","session_id","switch",
                               "src","dst","packets","bytes_fmt","priority"]].rename(
                    columns={"bytes_fmt": "bytes"}
                ),
                width="stretch", hide_index=True
            )

# =========================================================
# Live tab
# This tab keeps refreshing and shows current traffic data
# =========================================================
with tab_live:
    placeholder = st.empty()

while True:
    with placeholder.container():
        if not os.path.exists(STATS_FILE):
            st.markdown('<div class="alert-mid">Waiting ..... start POX and Mininet first.</div>', unsafe_allow_html=True)
        else:
            try:
                with open(STATS_FILE, "r") as f:
                    content = f.read()
                if not content.strip():
                    time.sleep(1)
                    continue
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                time.sleep(1)
                continue

            total_packets_raw = data.get("total_packets", 0)
            total_bytes_raw   = data.get("total_bytes", 0)
            active_flows      = data.get("active_flows", 0)
            top_talker        = data.get("top_talker", "N/A")
            delta_bytes       = data.get("delta_bytes", 0)
            delta_packets     = data.get("delta_packets", 0)

            # ── zero-based session metrics ────────────────────────────
            if st.session_state.session_base_packets is None:
                st.session_state.session_base_packets = total_packets_raw
            if st.session_state.session_base_bytes is None:
                st.session_state.session_base_bytes = total_bytes_raw

            session_packets = max(0, total_packets_raw - st.session_state.session_base_packets)
            session_bytes   = max(0, total_bytes_raw   - st.session_state.session_base_bytes)

            level, color, label = traffic_level(delta_bytes)
            ts = data.get("timestamp", time.strftime("%H:%M:%S"))

            # ── update rolling session history ───────────────────────────────
            last = st.session_state.session_history[-1] if st.session_state.session_history else {}
            if not last or last.get("timestamp") != ts:
                st.session_state.session_history.append({
                    "timestamp":      ts,
                    "session_packets": session_packets,
                    "session_bytes":   session_bytes,
                    "active_flows":    active_flows,
                    "delta_bytes":     delta_bytes,
                    "level":           level,
                })

            # ── level-transition timeline ─────────────────────────────
            if level != st.session_state.last_level and st.session_state.last_level is not None:
                st.session_state.level_timeline.append({
                    "timestamp": ts,
                    "kind":      "transition",
                    "level":     level,
                    "label":     label.replace("🟢 ","").replace("🟡 ","").replace("🔴 ",""),
                    "bytes_mb":  session_bytes / 1_000_000,
                })
            st.session_state.last_level = level

            # add controller-side spike events (deduplicated)
            for ev in data.get("events", []):
                spike_key = ev["timestamp"] + ev.get("label","")
                label_text = ev.get("label", "")
                if ("Spike" in label_text or "Blocked Event" in label_text) and spike_key not in st.session_state.seen_spike_ts:
                    st.session_state.seen_spike_ts.add(spike_key)
                    st.session_state.level_timeline.append({
                        "timestamp": ev["timestamp"],
                        "kind":      "spike",
                        "level":     "spike",
                        "label":     ev["label"],
                        "bytes_mb":  ev.get("bytes", 0) / 1_000_000,
                    })
            st.session_state.level_timeline = st.session_state.level_timeline[-100:]

            # ─────────────────────────────────────────────────────────────────
            # METRIC CARDS  (session-relative, start at 0)
            # ─────────────────────────────────────────────────────────────────
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Session Packets</div>
                    <div class="metric-value">{session_packets:,}</div>
                    <div class="metric-sub">since session start</div>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Session Bytes</div>
                    <div class="metric-value">{fmt_bytes(session_bytes)}</div>
                    <div class="metric-sub">{session_bytes:,} B raw</div>
                </div>""", unsafe_allow_html=True)
            with c3:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Active Flows</div>
                    <div class="metric-value">{active_flows}</div>
                    <div class="metric-sub">installed rules</div>
                </div>""", unsafe_allow_html=True)
            with c4:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Top Talker</div>
                    <div class="metric-value" style="font-size:1rem; padding-top:6px">{top_talker}</div>
                    <div class="metric-sub">highest byte flow</div>
                </div>""", unsafe_allow_html=True)

            # ─────────────────────────────────────────────────────────────────
            # ALERT BAR — current status + spike pills inline
            # ─────────────────────────────────────────────────────────────────
            spike_events = [e for e in st.session_state.level_timeline if e["kind"] == "spike"]
            spike_pills_html = ""
            if spike_events:
                spike_pills_html = '<div style="margin-top:8px; display:flex; flex-wrap:wrap; gap:5px;">'
                for sp in spike_events[-6:]:
                    icon = "🚫" if "Blocked Event" in sp["label"] else "⚡"
                    spike_pills_html += (
                        f'<span class="event-pill" '
                        f'style="background:#FDECEA;color:#8B1A1A;border:1px solid #E57373;">'
                        f'{icon} {sp["timestamp"]} — {sp["label"]}</span>'
                    )
                spike_pills_html += "</div>"

            st.markdown(
                f'<div class="alert-{level}" style="margin-top:1rem">'
                f'{label}{spike_pills_html}'
                f'</div>',
                unsafe_allow_html=True
            )

            # ─────────────────────────────────────────────────────────────────
            # LIVE TRAFFIC RATE
            #   Left:  MB/s (rolling delta)
            #   Right: Traffic Trend Since Session Start (MB)  
            # ─────────────────────────────────────────────────────────────────
            sess = st.session_state.session_history
            if len(sess) >= 2:
                st.markdown('<div class="section-title">Live Traffic Rate</div>', unsafe_allow_html=True)
                df_sess = pd.DataFrame(sess).set_index("timestamp")
                df_sess["byte_rate_mb"] = df_sess["delta_bytes"] / 1_000_000
                df_sess["trend_mb"]     = df_sess["session_bytes"] / 1_000_000

                r1, r2 = st.columns(2)
                with r1:
                    st.caption("🟣 Live Traffic Rate (MB/s)")
                    st.line_chart(df_sess[["byte_rate_mb"]], color=["#8A2BE2"], height=250)
                with r2:
                    st.caption("🟤 Traffic Trend Since Session Start (MB)")
                    st.line_chart(df_sess[["trend_mb"]], color=["#8B4513"], height=250)

            # ─────────────────────────────────────────────────────────────────
            # CUMULATIVE TRAFFIC 
            # ─────────────────────────────────────────────────────────────────
            history = data.get("history", [])
            if history:
                st.markdown('<div class="section-title">Cumulative Traffic (Rolling 20-poll Window)</div>', unsafe_allow_html=True)
                df_rt = pd.DataFrame(history).set_index("timestamp")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.line_chart(df_rt[["total_bytes"]], color=["#3D7ABF"], height=200)
                    st.caption("🔵 Total Bytes")
                with c2:
                    st.line_chart(df_rt[["total_packets"]], color=["#C47A3D"], height=200)
                    st.caption("🟠 Total Packets")
                with c3:
                    st.line_chart(df_rt[["active_flows"]], color=["#5A8A5A"], height=200)
                    st.caption("🟢 Active Flows")

            # ─────────────────────────────────────────────────────────────────
            # SESSION TRAFFIC TIMELINE
            # Shows Low→Moderate→High transitions + spike events as a timeline
            # ─────────────────────────────────────────────────────────────────
            timeline = st.session_state.level_timeline
            if len(sess) >= 1:
                st.markdown('<div class="section-title">Session Traffic Timeline</div>', unsafe_allow_html=True)
                col_tl, col_bands = st.columns([3, 1])

                with col_tl:
                    if len(sess) >= 2:
                        df_trend = pd.DataFrame(sess).set_index("timestamp")
                        df_trend["bytes_mb"] = df_trend["session_bytes"] / 1_000_000
                        st.area_chart(df_trend[["bytes_mb"]], color=["#3D7ABF"], height=200)
                        st.caption("Session bytes (MB) — full session since page load")

                    if timeline:
                        st.markdown("**Events this session:**")
                        tl_html = '<div class="timeline-line">'
                        for entry in reversed(timeline[-20:]):
                            kind = entry["kind"]
                            lvl  = entry["level"]
                            ts_e = entry["timestamp"]
                            lbl  = entry["label"]
                            mb   = entry["bytes_mb"]

                            if kind == "spike":
                                dot_color = "#E57373"
                                pill_bg, pill_fg, icon = "#FDECEA", "#8B1A1A", "⚡"
                            elif "Blocked Event" in lbl:
                                dot_color = "#E57373"
                                pill_bg, pill_fg, icon = "#FDECEA", "#8B1A1A", "🚫"
                            elif lvl == "high":
                                dot_color = "#E57373"
                                pill_bg, pill_fg, icon = "#FDECEA", "#8B1A1A", "🔴"
                            elif lvl == "mid":
                                dot_color = "#F5B942"
                                pill_bg, pill_fg, icon = "#FFF7E6", "#7A5200", "🟡"
                            else:
                                dot_color = "#8BC48B"
                                pill_bg, pill_fg, icon = "#EAF4EA", "#2D6E2D", "🟢"

                            tl_html += f"""
                            <div class="timeline-row">
                              <div class="timeline-dot" style="background:{dot_color};"></div>
                              <div>
                                <span class="event-pill" style="background:{pill_bg};color:{pill_fg};">
                                  {icon} {ts_e} &nbsp;·&nbsp; {lbl}
                                </span>
                                <span style="font-size:0.72rem;color:#8A7B6A;margin-left:6px;">@ {mb:.2f} MB</span>
                              </div>
                            </div>"""
                        tl_html += "</div>"
                        st.markdown(tl_html, unsafe_allow_html=True)
                    else:
                        st.caption("Level-change events and spikes will appear here as traffic changes.")

                with col_bands:
                    low_count  = sum(1 for e in timeline if e["level"] == "low")
                    mid_count  = sum(1 for e in timeline if e["level"] == "mid")
                    high_count = sum(1 for e in timeline if e["level"] == "high")
                    spk_count  = sum(1 for e in timeline if e["kind"]  == "spike")

                    cur_label = {"low": "🟢 Low", "mid": "🟡 Moderate", "high": "🔴 High"}.get(level, "—")

                    st.markdown(f"""
                    <div style="background:#FFFDF7; border:1px solid #E2D9C8; border-radius:12px; padding:16px; margin-top:4px">
                      <div style="font-size:0.7rem;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#8A7B6A;margin-bottom:12px">Session Summary</div>

                      <div style="margin-bottom:10px">
                        <span style="font-size:0.75rem;color:#3D4B5C;font-weight:600;">Current Level</span><br>
                        <span style="font-size:1.1rem;font-weight:700;color:#2E5B8A">{cur_label}</span>
                      </div>
                      <hr style="border:none;border-top:1px solid #E2D9C8;margin:8px 0">

                      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                        <div style="width:11px;height:11px;border-radius:3px;background:#8BC48B;flex-shrink:0"></div>
                        <span style="font-size:0.78rem;color:#3D4B5C">Low &lt; 100 KB</span>
                        <span style="margin-left:auto;font-size:0.78rem;font-weight:600;color:#2D6E2D">{low_count}×</span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                        <div style="width:11px;height:11px;border-radius:3px;background:#F5B942;flex-shrink:0"></div>
                        <span style="font-size:0.78rem;color:#3D4B5C">Mid 100KB-100MB</span>
                        <span style="margin-left:auto;font-size:0.78rem;font-weight:600;color:#7A5200">{mid_count}×</span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                        <div style="width:11px;height:11px;border-radius:3px;background:#E57373;flex-shrink:0"></div>
                        <span style="font-size:0.78rem;color:#3D4B5C">High &gt; 100 MB</span>
                        <span style="margin-left:auto;font-size:0.78rem;font-weight:600;color:#8B1A1A">{high_count}×</span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px">
                        <div style="width:11px;height:11px;border-radius:3px;background:#FDECEA;border:1px solid #E57373;flex-shrink:0"></div>
                        <span style="font-size:0.78rem;color:#3D4B5C">Spikes </span>
                        <span style="margin-left:auto;font-size:0.78rem;font-weight:600;color:#8B1A1A">{spk_count}×</span>
                      </div>

                      <hr style="border:none;border-top:1px solid #E2D9C8;margin:10px 0">
                      <div style="font-size:0.72rem;color:#8A7B6A">{len(sess)} snapshots recorded</div>
                      <div style="font-size:0.72rem;color:#8A7B6A">since {st.session_state.session_start}</div>
                    </div>
                    """, unsafe_allow_html=True)
            # ─────────────────────────────────────────────────────────────────
            # flow table + top talkers
            # ─────────────────────────────────────────────────────────────────
            flows = data.get("flows", [])
            if flows:
                st.markdown('<div class="section-title">Recent Flow Statistics</div>', unsafe_allow_html=True)
                df_flows = pd.DataFrame(flows)
                df_flows["bytes_fmt"] = df_flows["bytes"].apply(fmt_bytes)
                st.dataframe(
                    df_flows[["switch","src","dst","packets","bytes_fmt","priority"]].rename(
                        columns={"bytes_fmt": "bytes"}
                    ),
                    width="stretch", hide_index=True,
                )

                st.markdown('<div class="section-title">Top Talkers</div>', unsafe_allow_html=True)
                top_df = (
                    df_flows.groupby(["src","dst"], as_index=False)["bytes"]
                    .sum()
                    .sort_values("bytes", ascending=False)
                    .head(5)
                )
                top_df["pair"] = top_df["src"] + " → " + top_df["dst"]
                st.bar_chart(top_df.set_index("pair")["bytes"], color="#3D7ABF", height=200)

    time.sleep(3)

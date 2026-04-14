# SDN Traffic Monitoring Dashboard using Mininet and POX

![Python](https://img.shields.io/badge/language-Python-blue)
![Mininet](https://img.shields.io/badge/network-Mininet-green)
![POX](https://img.shields.io/badge/controller-POX-orange)
![OpenFlow](https://img.shields.io/badge/protocol-OpenFlow-purple)

An SDN-based traffic monitoring project built using **Mininet**, **POX controller**, and a **Streamlit dashboard** to demonstrate controller-switch interaction, flow-rule logic, traffic statistics collection, and observable network behavior.

---

##  Problem Statement

The goal of this project is to build a controller module that collects and displays traffic statistics in a Mininet-based SDN environment.

The project demonstrates:

- Controller–switch interaction  
- OpenFlow match–action rule behavior  
- Packet handling through controller logic  
- Traffic monitoring using packet and byte counts  
- Performance observation using ping, iperf, and flow tables  

This project is implemented on an **Ubuntu 24 VM** using Mininet and POX.

---

##  Objectives

- Create a working Mininet topology  
- Connect Mininet to a POX controller  
- Handle `packet_in` events in the controller  
- Install flow rules dynamically  
- Monitor traffic and flow statistics  
- Visualize collected data through a dashboard  
- Demonstrate allowed vs blocked or normal vs failure behavior  

---

##  Features

- SDN controller logic using POX  
- Traffic statistics monitoring  
- Packet count and byte count collection  
- Flow-level logging  
- Dashboard-based visualization  
- Support for traffic observation using `pingall` and `iperf`  
- Proof of execution using flow tables and screenshots  

---

##  Topology Used

This project uses a simple Mininet topology for easy demonstration and observation.

Example setup:
- 1 switch  
- 4 hosts  
- remote POX controller  

This simple topology helps clearly demonstrate forwarding, monitoring, and blocked traffic behavior.

---

##  Project Workflow

1. Hosts send traffic through the Mininet switch  
2. If no matching flow rule exists, the switch sends a `packet_in` event to the controller  
3. The POX controller processes the packet  
4. The controller decides whether to allow, forward, or block traffic  
5. Flow rules are installed in the switch  
6. Traffic statistics are collected and stored  
7. The dashboard reads the stored data and displays traffic behavior  

---

##  Folder Structure

```text
sdn-traffic-monitor/
├── controller/
│   └── traffic_monitor.py
├── dashboard/
│   └── app.py
├── data/
│   ├── flow_log.csv
│   ├── stats.json
│   └── traffic_log.csv
├── screenshots/
├── .gitignore
├── README.md
└── requirements.txt

---

##  Data Files

All monitoring outputs are stored in the `data/` folder:

- `flow_log.csv` → flow-level statistics  
- `traffic_log.csv` → traffic trend data  
- `stats.json` → aggregated or latest statistics  

---

##  Requirements

### System Requirements
- Ubuntu 24 VM  
- Python 3  
- Mininet  
- Open vSwitch  
- POX controller  

### Python Packages

Install using:
pip install -r requirements.txt

Packages used:
streamlit
pandas
matplotlib

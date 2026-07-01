# Meraki Network Diagram Generator

Automatically generates network topology diagrams for all networks in your Cisco Meraki organization using the official [Meraki Dashboard API](https://developer.cisco.com/meraki/api-v1/). No browser sessions or manual exports required.

**One command. All networks. Two diagram formats.**

```
python main.py
```

---

## Output

For every network in your Meraki org, the tool produces:

| File | How to open |
|---|---|
| `diagram.mmd` | VS Code with [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension |
| `diagram.drawio` | [diagrams.net](https://app.diagrams.net) — drag, resize, export to PNG/PDF |

Diagrams include:
- **Hierarchical layout** — MX firewall at top, switches in middle, APs and endpoints below
- **Interface labels** — port IDs and descriptions on every connection
- **Engineer notes** — STP mode, storm control thresholds, MTU, access policies, VLANs embedded as annotations

---

## Project Structure

```
meraki-network-diagrams/
  main.py                    <- Run this
  .env                       <- Your API key (not committed to git)
  .env.example               <- Template showing required variables
  .gitignore
  requirements.txt
  meraki_diagrams/
    collect.py               <- Phase 1: fetch topology data from Meraki API
    diagram.py               <- Phase 2: generate diagrams from saved JSON
  Network Diagram/           <- Output folder (created on first run)
    {network_name}/
      topology.json
      diagram.mmd
      diagram.drawio
    collection_summary.xlsx
  MerakiNetworkDiagram-PLAN.txt   <- Technical design reference
  meraki network diagram.txt      <- Original approach reference
```

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/meraki-network-diagrams.git
cd meraki-network-diagrams
```

### 2. Create a virtual environment and install dependencies

```powershell
python -m venv .venv-meraki
.venv-meraki\Scripts\Activate       # Windows
# source .venv-meraki/bin/activate  # Mac/Linux
pip install -r requirements.txt
```

### 3. Add your API key

Copy `.env.example` to `.env` and fill in your Meraki API key:

```
MERAKI_API_KEY=your_api_key_here
ORG_ID=                            # leave blank to auto-discover
```

**How to get your API key:**
1. Log in to [dashboard.meraki.com](https://dashboard.meraki.com)
2. Click your profile (top right) → **My profile**
3. Scroll to **API access** → **Generate new API key**

### 4. Run

```powershell
python main.py
```

---

## Configuration

All settings are in `main.py` under the configuration block. No code changes needed for normal use — just edit the values.

| Setting | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `"Network Diagram"` | Where diagrams are saved |
| `NETWORK_FILTER` | `[]` | Limit to specific networks, e.g. `["HQ", "Branch-A"]`. Empty = all |
| `INCLUDE_SWITCH_SETTINGS` | `True` | Collect STP, storm control, MTU, access policies |
| `INCLUDE_VLANS` | `True` | Collect VLAN list from MX networks |
| `INCLUDE_PORT_DETAILS` | `True` | Collect port names for interface labels |
| `GENERATE_MERMAID` | `True` | Output `.mmd` diagram files |
| `GENERATE_DRAWIO` | `True` | Output `.drawio` diagram files |
| `SHOW_MODEL` | `True` | Show device model in node labels |
| `SHOW_SERIAL` | `False` | Show serial number in node labels |
| `SHOW_IP` | `True` | Show management IP in node labels |
| `SHOW_PORT_LABELS` | `True` | Show interface names on connections |
| `SHOW_PORT_DESC` | `True` | Show port descriptions alongside port IDs |

---

## How It Works

The tool runs in two phases:

**Phase 1 — `meraki_diagrams/collect.py`**
Connects to the Meraki API and collects for each network:
- Link-layer topology (`/networks/{id}/topology/link-layer`)
- Device inventory including firmware and IP
- Switch settings: STP, storm control, MTU, access policies, DHCP policy
- VLAN configuration (MX networks)
- LLDP/CDP neighbor data (fallback for networks without managed switches)

**Phase 2 — `meraki_diagrams/diagram.py`**
Reads the saved JSON files and generates:
- Mermaid flowchart with top-down directed layout and styled root nodes
- draw.io XML with hierarchical positioning and engineer notes text box

---

## Viewing Diagrams

### Mermaid (.mmd) in VS Code
1. Install the [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension
2. Open any `diagram.mmd` file
3. Press `Ctrl+Shift+P` → **"Mermaid: Open Preview"**

### draw.io in browser
1. Go to [https://app.diagrams.net](https://app.diagrams.net)
2. Click **Open Existing Diagram** → select the `.drawio` file
3. Full drag-and-drop editor — arrange, restyle, export to PNG/PDF/SVG

### Confluence
- Paste Mermaid code directly into a Confluence **Mermaid** macro
- Embed draw.io files using the **draw.io** Confluence app

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `MERAKI_API_KEY is not set` | Copy `.env.example` to `.env` and add your key |
| `No organizations found` | Check your API key has org-level read access |
| `ModuleNotFoundError: meraki` | Activate the venv: `.venv-meraki\Scripts\Activate` |
| Empty diagram for a network | Network may be wireless-only; tool falls back to LLDP/CDP |
| draw.io file won't open | Regenerate with `python main.py` — older files may have formatting issues |

---

## API Reference

- Base URL: `https://api.meraki.com/api/v1`
- Auth: `X-Cisco-Meraki-API-Key` header
- Docs: [https://developer.cisco.com/meraki/api-v1/](https://developer.cisco.com/meraki/api-v1/)
- Python SDK: [https://github.com/meraki/dashboard-api-python](https://github.com/meraki/dashboard-api-python)


---

## Files

| File | Purpose |
|---|---|
| `MerakiNetworkDiagram-P1.py` | Fetches topology + network settings from Meraki API and saves JSON data |
| `MerakiNetworkDiagram-P2.py` | Reads saved JSON and generates diagram files |
| `MerakiNetworkDiagram-PLAN.txt` | Full technical plan and API endpoint reference |
| `Network Diagram/` | Output folder — all JSON and diagram files are saved here |

---

## Prerequisites

### 1. Python packages
```
pip install meraki pandas openpyxl
```

### 2. Meraki API key
1. Log in to [dashboard.meraki.com](https://dashboard.meraki.com)
2. Click your profile (top right) → **My profile**
3. Scroll to **API access** → **Generate new API key**
4. Copy the key — you only see it once

### 3. VS Code extension (for viewing Mermaid diagrams)
- Open Extensions (`Ctrl+Shift+X`)
- Search for **Mermaid Preview** by Vlad Stirbu
- Click Install

---

## Quick Start

### Step 1 — Configure P1
Open `MerakiNetworkDiagram-P1.py` and update the config block at the top:

```python
API_KEY  = "your_api_key_here"   # Paste your Meraki API key
ORG_ID   = ""                    # Leave blank to auto-discover, or paste your org ID
```

All other settings have sensible defaults — see the [Configuration](#configuration) section below.

### Step 2 — Run P1 (Data Collection)
```
python MerakiNetworkDiagram-P1.py
```

You will see output like:
```
============================================================
Meraki Network Topology Capture -- Phase 1
Started: 2026-06-30 10:00:00
============================================================
Fetching organizations...
  Found 1 organization(s).
Using org: Contoso (ID: 123456)
Fetching networks for org 123456...
  Found 47 network(s).

[1/47] HQ-Switch (switch, appliance)
  Devices: 6
  Topology: 6 nodes, 5 links
  Switch settings: ['stp', 'stormControl', 'mtu', 'accessPolicies']
  VLANs: 8
  Port details: 4 switch(es)
  Saved --> Network Diagram/HQ-Switch/topology.json
...
Summary saved --> Network Diagram/collection_summary.xlsx
```

### Step 3 — Run P2 (Diagram Generation)
```
python MerakiNetworkDiagram-P2.py
```

You will see output like:
```
Generating: HQ-Switch
  Mermaid  --> Network Diagram/HQ-Switch/diagram.mmd
  draw.io  --> Network Diagram/HQ-Switch/diagram.drawio
...
Complete. 47 diagram(s) generated.
```

---

## Output Structure

After running both scripts, your `Network Diagram/` folder will look like:

```
Network Diagram/
├── collection_summary.xlsx        <- Summary of all networks processed
├── HQ-Switch/
│   ├── topology.json              <- Raw collected data (devices, links, settings)
│   ├── diagram.mmd                <- Mermaid diagram
│   └── diagram.drawio             <- draw.io diagram
├── Branch-Office/
│   ├── topology.json
│   ├── diagram.mmd
│   └── diagram.drawio
└── ...
```

---

## Viewing the Diagrams

### Mermaid (.mmd) — in VS Code
1. Open any `diagram.mmd` file
2. Press `Ctrl+Shift+P` → type **Mermaid** → select **"Mermaid: Open Preview"**
3. A visual diagram appears in a side panel and updates as you edit the text

### draw.io (.drawio) — in browser
1. Go to [https://app.diagrams.net](https://app.diagrams.net)
2. Click **Open Existing Diagram** → upload the `.drawio` file
3. Full drag-and-drop visual editor — resize, restyle, add annotations, export to PNG/PDF

### Confluence
- Mermaid diagrams can be pasted directly into a Confluence Mermaid macro
- draw.io files can be embedded using the draw.io Confluence app

---

## Configuration

### P1 — MerakiNetworkDiagram-P1.py

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `"your_api_key_here"` | Your Meraki API key |
| `ORG_ID` | `""` | Your org ID, or leave blank to auto-discover |
| `OUTPUT_DIR` | `"Network Diagram"` | Folder where JSON files are saved |
| `NETWORK_FILTER` | `[]` | Limit to specific networks, e.g. `["HQ", "Branch-A"]`. Empty = all |
| `INCLUDE_SWITCH_SETTINGS` | `True` | Collect STP, storm control, MTU, access policies, DHCP policy |
| `INCLUDE_VLANS` | `True` | Collect VLAN list from MX/appliance networks |
| `INCLUDE_PORT_DETAILS` | `True` | Collect port names/descriptions for interface labels |

> **Note:** Rate limiting and pagination are handled automatically by the Meraki SDK — no manual delay settings needed.

### P2 — MerakiNetworkDiagram-P2.py

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `"Network Diagram"` | Must match the P1 value |
| `GENERATE_MERMAID` | `True` | Output `.mmd` files |
| `GENERATE_DRAWIO` | `True` | Output `.drawio` files |
| `SHOW_MODEL` | `True` | Show device model in node labels (e.g. MS225) |
| `SHOW_SERIAL` | `True` | Show serial number in node labels |
| `SHOW_IP` | `True` | Show management IP in node labels |
| `SHOW_PORT_LABELS` | `True` | Label edges with interface names |
| `SHOW_PORT_DESC` | `True` | Append port descriptions alongside port IDs |

---

## Engineer Notes in Diagrams

Every diagram file includes a commented section at the bottom with network-wide settings:

**In Mermaid (.mmd):**
```
%% --- Network Engineer Notes ---
%% STP: RSTP, 0 root bridge override(s)
%% Storm Control -- Broadcast: 30%, Multicast: 30%, Unknown Unicast: 30%
%% MTU: 9578 bytes
%% Access Policy: Corp-Dot1x | Type: 802.1x | Dot1x: both | RADIUS: True
%% DHCP Server Policy: block
%% VLANs: VLAN 1 (Default), VLAN 10 (Corp), VLAN 20 (Guest), VLAN 99 (Mgmt)
```

**In draw.io (.drawio):**
```xml
<!-- Network Engineer Notes:
  STP: RSTP, 0 root bridge override(s)
  Storm Control -- Broadcast: 30%, Multicast: 30%, Unknown Unicast: 30%
  ...
-->
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No organizations found` | Check your API key is correct and has org-level read access |
| `HTTP error: 404` | That setting doesn't exist for this network type — safe to ignore |
| `No topology.json files found` | Run P1 before P2 |
| Diagrams are empty / no nodes | The network may be wireless-only; P1 falls back to LLDP/CDP data |
| Script is slow | The SDK manages rate limiting automatically — no manual tuning needed |
| Want only certain networks | Set `NETWORK_FILTER = ["Site-A", "HQ"]` in P1 config |

---

## API Reference

Base URL: `https://api.meraki.com/api/v1`  
Auth header: `X-Cisco-Meraki-API-Key: <your_key>`  
Full docs: [https://developer.cisco.com/meraki/api-v1/](https://developer.cisco.com/meraki/api-v1/)

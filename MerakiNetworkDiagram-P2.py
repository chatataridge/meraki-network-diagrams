import json
import os
import glob
import xml.etree.ElementTree as ET
from datetime import datetime

# --- Configuration: UPDATE THESE VALUES ---
OUTPUT_DIR       = "Network Diagram"   # Must match OUTPUT_DIR in P1
GENERATE_MERMAID = True                # Output .mmd files (open in VS Code Mermaid Preview)
GENERATE_DRAWIO  = True                # Output .drawio files (open at diagrams.net)
SHOW_MODEL       = True                # Include model (e.g. MS225) in node labels
SHOW_SERIAL      = False               # Include serial number in node labels
SHOW_IP          = True                # Include management IP in node labels
SHOW_PORT_LABELS = True                # Label diagram edges with interface names
SHOW_PORT_DESC   = True                # Append port description alongside port ID


def load_network_data(topology_file):
    """Loads a topology.json file."""
    with open(topology_file) as f:
        return json.load(f)


def build_device_map(data):
    """
    Creates a lookup dict keyed by derivedId and serial -> device info.
    Device details come directly from the topology node's embedded device field,
    enriched with lanIp from the P1 devices list.
    """
    # Index P1 device list by serial for IP lookup
    device_by_serial = {
        d["serial"]: d for d in data.get("devices", []) if d.get("serial")
    }

    device_map = {}
    for node in data.get("topology", {}).get("nodes", []):
        derived_id  = node.get("derivedId", "")
        dev_info    = node.get("device", {})
        serial      = dev_info.get("serial", "")
        full_device = device_by_serial.get(serial, {})

        entry = {
            "name":   dev_info.get("name") or full_device.get("name", derived_id[:20]),
            "model":  dev_info.get("model") or full_device.get("model", ""),
            "serial": serial,
            "lanIp":  full_device.get("lanIp", ""),
        }
        device_map[derived_id] = entry
        if serial:
            device_map[serial] = entry

    return device_map


def get_node_label(node_id, device_map, separator=" | "):
    """Builds a display label for a topology node."""
    device = device_map.get(node_id, {})
    name   = device.get("name") or node_id[:20]
    parts  = [name]
    if SHOW_MODEL and device.get("model"):
        parts.append(device["model"])
    if SHOW_SERIAL and device.get("serial"):
        parts.append(f"S/N: {device['serial']}")
    if SHOW_IP and device.get("lanIp"):
        parts.append(device["lanIp"])
    return separator.join(parts)


def get_port_label(end):
    """Builds an interface label using LLDP data embedded directly in the topology link end."""
    if not SHOW_PORT_LABELS:
        return ""
    lldp    = (end.get("discovered") or {}).get("lldp") or {}
    port_id = lldp.get("portId", "")
    if not port_id:
        return ""
    if SHOW_PORT_DESC:
        desc = lldp.get("portDescription", "")
        # Skip redundant descriptions like "Port 4" when port_id is already "4"
        if desc and desc.lower() not in (f"port {port_id}".lower(), str(port_id).lower()):
            return f"{port_id} ({desc})"
    return str(port_id)


def build_mermaid(data):
    """Generates a Mermaid flowchart diagram string from topology data."""
    lines      = ["graph TD", "    classDef root fill:#dae8fc,stroke:#6c8ebf,font-weight:bold"]
    topo       = data.get("topology", {})
    nodes      = topo.get("nodes", [])
    links      = topo.get("links", [])
    device_map = build_device_map(data)

    if not nodes:
        # Fallback: build from LLDP/CDP data
        lines.append("    %% Built from LLDP/CDP fallback data")
        lldp_data  = data.get("lldpCdp", {})
        seen_edges = set()
        for serial, lldp in lldp_data.items():
            src_device = device_map.get(serial, {})
            src_name   = src_device.get("name", serial)
            src_id     = f"dev_{serial.replace(':', '_')}"
            lines.append(f'    {src_id}["{src_name}"]')
            for port_id, port_data in lldp.get("ports", {}).items():
                for proto in ["lldp", "cdp"]:
                    neighbor = port_data.get(proto, {})
                    if not neighbor:
                        continue
                    nbr_name = (neighbor.get("systemName")
                                or neighbor.get("deviceId", "Unknown"))
                    nbr_id   = ("nbr_"
                                + nbr_name.replace(" ", "_").replace(":", "_")[:20])
                    edge_key = tuple(sorted([src_id, nbr_id]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        src_port = neighbor.get("sourcePort", port_id)
                        nbr_port = neighbor.get("portId", "")
                        label    = (f"{src_port} <-> {nbr_port}"
                                    if SHOW_PORT_LABELS and nbr_port
                                    else str(src_port))
                        lines.append(f'    {nbr_id}["{nbr_name}"]')
                        lines.append(f'    {src_id} ---|"{label}"| {nbr_id}')
        return "\n".join(lines)

    # Map derivedId to safe Mermaid identifiers
    node_id_map   = {}
    root_node_ids = set()
    for idx, node in enumerate(nodes):
        node_id_map[node["derivedId"]] = f"n{idx}"
        if node.get("root", False):
            root_node_ids.add(f"n{idx}")

    # Compute hierarchy for directed edge rendering
    levels = compute_hierarchy(nodes, links)

    # Emit node definitions
    lines.append("")
    for node in nodes:
        derived_id = node["derivedId"]
        safe_id    = node_id_map[derived_id]
        label      = get_node_label(derived_id, device_map).replace('"', "'")
        lines.append(f'    {safe_id}["{label}"]')

    # Apply root styling
    if root_node_ids:
        lines.append(f'    class {",".join(sorted(root_node_ids))} root')

    # Emit links — directed from higher level (closer to root) to lower
    lines.append("")
    for link in links:
        ends = link.get("ends", [])
        if len(ends) != 2:
            continue
        a_did  = ends[0]["node"]["derivedId"]
        b_did  = ends[1]["node"]["derivedId"]
        a_safe = node_id_map.get(a_did)
        b_safe = node_id_map.get(b_did)
        if not a_safe or not b_safe:
            continue
        # Direct edge from shallower node to deeper node
        if levels.get(a_did, 0) > levels.get(b_did, 0):
            a_did, b_did   = b_did, a_did
            a_safe, b_safe = b_safe, a_safe
            ends           = [ends[1], ends[0]]
        a_port = get_port_label(ends[0])
        b_port = get_port_label(ends[1])
        label  = f"{a_port} --> {b_port}".strip(" -->")
        if label:
            lines.append(f'    {a_safe} -->|"{label}"| {b_safe}')
        else:
            lines.append(f"    {a_safe} --> {b_safe}")

    return "\n".join(lines)


def compute_hierarchy(nodes, links):
    """
    BFS from root nodes to assign a depth level to each node.
    Level 0 = root (MX/firewall), Level 1 = switches, Level 2 = APs/endpoints.
    Returns dict: {derivedId: level}
    """
    # Build undirected adjacency from links
    adj = {n["derivedId"]: [] for n in nodes}
    for link in links:
        ends = link.get("ends", [])
        if len(ends) == 2:
            a = ends[0]["node"]["derivedId"]
            b = ends[1]["node"]["derivedId"]
            if a in adj:
                adj[a].append(b)
            if b in adj:
                adj[b].append(a)

    levels  = {}
    queue   = []
    visited = set()

    # Seed BFS from root nodes
    for node in nodes:
        if node.get("root", False):
            nid = node["derivedId"]
            levels[nid] = 0
            queue.append(nid)
            visited.add(nid)

    while queue:
        nid = queue.pop(0)
        for neighbor in adj.get(nid, []):
            if neighbor not in visited:
                visited.add(neighbor)
                levels[neighbor] = levels[nid] + 1
                queue.append(neighbor)

    # Assign level 0 to any disconnected nodes
    for node in nodes:
        if node["derivedId"] not in levels:
            levels[node["derivedId"]] = 0

    return levels


def build_drawio(data):
    """Generates draw.io XML (mxGraph format) from topology data."""
    net_name     = data.get("networkName", "Network")
    topo       = data.get("topology", {})
    nodes      = topo.get("nodes", [])
    links      = topo.get("links", [])
    device_map = build_device_map(data)

    # Compute hierarchical levels (BFS from root)
    levels      = compute_hierarchy(nodes, links)
    # Group derivedIds by level
    by_level    = {}
    for nid, lvl in levels.items():
        by_level.setdefault(lvl, []).append(nid)
    max_level   = max(by_level.keys(), default=0)

    # Canvas sizing
    node_w, node_h = 180, 60
    x_gap, y_gap   = 60, 100
    y_start        = 80

    # Pre-calculate x positions per level so nodes are centered
    level_positions = {}   # {derivedId: (cx, cy)}
    for lvl in range(max_level + 1):
        nids     = by_level.get(lvl, [])
        count    = len(nids)
        total_w  = count * node_w + (count - 1) * x_gap
        x_origin = max(80, 600 - total_w // 2)   # center around x=600
        cy       = y_start + lvl * (node_h + y_gap)
        for i, nid in enumerate(nids):
            cx = x_origin + i * (node_w + x_gap)
            level_positions[nid] = (cx, cy)

    mxfile  = ET.Element("mxfile")
    diagram = ET.SubElement(mxfile, "diagram", name=net_name[:31])
    model   = ET.SubElement(
        diagram, "mxGraphModel",
        dx="1422", dy="762", grid="1", gridSize="10",
        guides="1", tooltips="1", connect="1", arrows="1",
        fold="1", page="1", pageScale="1",
        pageWidth="1169", pageHeight="827", math="0", shadow="0",
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    node_cell_ids    = {}

    for idx, node in enumerate(nodes):
        derived_id = node["derivedId"]
        cell_id    = f"cell_{idx + 2}"
        node_cell_ids[derived_id] = cell_id

        label = get_node_label(derived_id, device_map, separator="&#xa;")
        role  = node.get("root", False)
        style = (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;"
            if role
            else "rounded=1;whiteSpace=wrap;html=1;"
        )
        cx, cy = level_positions.get(derived_id, (100, 100))

        cell = ET.SubElement(
            root, "mxCell",
            id=cell_id, value=label, style=style,
            vertex="1", parent="1",
        )
        ET.SubElement(
            cell, "mxGeometry",
            x=str(cx), y=str(cy), width="180", height="60",
            **{"as": "geometry"},
        )

    # Emit edges
    for lidx, link in enumerate(links):
        ends = link.get("ends", [])
        if len(ends) != 2:
            continue
        a_id = node_cell_ids.get(ends[0]["node"]["derivedId"])
        b_id = node_cell_ids.get(ends[1]["node"]["derivedId"])
        if not a_id or not b_id:
            continue
        a_port = get_port_label(ends[0])
        b_port = get_port_label(ends[1])
        label  = f"{a_port} <-> {b_port}".strip(" <->")

        edge = ET.SubElement(
            root, "mxCell",
            id=f"edge_{lidx}", value=label,
            style="edgeStyle=orthogonalEdgeStyle;rounded=0;",
            edge="1", source=a_id, target=b_id, parent="1",
        )
        ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})

    return ET.tostring(mxfile, encoding="unicode", xml_declaration=False)


def add_notes_to_drawio(drawio_str, notes):
    """Appends engineer notes as a read-only text box inside the draw.io XML."""
    if not notes or not drawio_str:
        return drawio_str
    notes_text = "&#xa;".join(notes)
    notes_cell = (
        f'<mxCell id="notes" value="Engineer Notes:&#xa;{notes_text}" '
        f'style="text;html=1;strokeColor=none;fillColor=#fff2cc;align=left;'
        f'verticalAlign=top;whiteSpace=wrap;overflow=hidden;" '
        f'vertex="1" parent="1">'
        f'<mxGeometry x="10" y="10" width="400" height="120" as="geometry"/>'
        f'</mxCell>'
    )
    return drawio_str.replace("</root>", notes_cell + "</root>", 1)


def build_engineer_notes(data):
    """Builds a list of network-wide setting strings for engineer troubleshooting."""
    notes    = []
    settings = data.get("switchSettings", {})

    stp = settings.get("stp", {})
    if stp:
        mode      = "RSTP" if stp.get("rstpEnabled") else "STP"
        overrides = len(stp.get("overrides", []))
        notes.append(f"STP: {mode}, {overrides} root bridge override(s)")

    storm = settings.get("stormControl", {})
    if storm:
        notes.append(
            f"Storm Control -- Broadcast: {storm.get('broadcastThreshold')}%, "
            f"Multicast: {storm.get('multicastThreshold')}%, "
            f"Unknown Unicast: {storm.get('unknownUnicastThreshold')}%"
        )

    mtu = settings.get("mtu", {})
    if mtu:
        notes.append(f"MTU: {mtu.get('defaultMtuSize')} bytes")

    for policy in settings.get("accessPolicies", []):
        notes.append(
            f"Access Policy: {policy.get('name')} | "
            f"Type: {policy.get('accessPolicyType')} | "
            f"Dot1x: {policy.get('dot1xControlDirection', 'N/A')} | "
            f"RADIUS: {bool(policy.get('radius'))}"
        )

    dhcp = settings.get("dhcpServerPolicy", {})
    if dhcp:
        notes.append(f"DHCP Server Policy: {dhcp.get('defaultPolicy', 'N/A')}")

    vlans = data.get("vlans", [])
    if vlans:
        vlan_list = ", ".join(
            f"VLAN {v['id']} ({v.get('name', '')})" for v in vlans[:10]
        )
        if len(vlans) > 10:
            vlan_list += f" ... +{len(vlans) - 10} more"
        notes.append(f"VLANs: {vlan_list}")

    return notes


def save_diagrams(network_name, mermaid_str, drawio_str, notes):
    """Saves .mmd and .drawio files into the network's output folder."""
    safe_name = "".join(
        c if c.isalnum() or c in " -_." else "_" for c in network_name
    )
    folder = os.path.join(OUTPUT_DIR, safe_name)
    os.makedirs(folder, exist_ok=True)

    if GENERATE_MERMAID and mermaid_str:
        mmd_path = os.path.join(folder, "diagram.mmd")
        with open(mmd_path, "w", encoding="utf-8") as f:
            f.write(mermaid_str)
            if notes:
                f.write("\n\n%% --- Network Engineer Notes ---\n")
                for note in notes:
                    f.write(f"%% {note}\n")
        print(f"  Mermaid  --> {mmd_path}")

    if GENERATE_DRAWIO and drawio_str:
        drawio_path = os.path.join(folder, "diagram.drawio")
        with open(drawio_path, "w", encoding="utf-8") as f:
            f.write(drawio_str)
        print(f"  draw.io  --> {drawio_path}")


def main():
    print("=" * 60)
    print("Meraki Network Diagram Generator -- Phase 2")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    topology_files = glob.glob(
        os.path.join(OUTPUT_DIR, "**", "topology.json"), recursive=True
    )

    if not topology_files:
        print(f"No topology.json files found in '{OUTPUT_DIR}/'")
        print("Run MerakiNetworkDiagram-P1.py first to collect data.")
        return

    print(f"Found {len(topology_files)} network(s) to diagram.\n")

    for topo_file in sorted(topology_files):
        data     = load_network_data(topo_file)
        net_name = data.get("networkName", os.path.basename(os.path.dirname(topo_file)))
        print(f"Generating: {net_name}")

        mermaid_str = build_mermaid(data)
        drawio_str  = build_drawio(data)
        notes       = build_engineer_notes(data)
        drawio_str  = add_notes_to_drawio(drawio_str, notes)

        save_diagrams(net_name, mermaid_str, drawio_str, notes)

    print("\n" + "=" * 60)
    print(f"Complete. {len(topology_files)} diagram(s) generated.")
    print("=" * 60)


if __name__ == "__main__":
    main()

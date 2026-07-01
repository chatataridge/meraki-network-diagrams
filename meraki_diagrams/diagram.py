"""Phase 2: Read topology JSON files and generate Mermaid and draw.io diagrams."""

import io
import json
import os
import glob
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

# Module-level config — set by run() from the config dict passed by main.py
SHOW_MODEL       = True
SHOW_SERIAL      = False
SHOW_IP          = True
SHOW_PORT_LABELS = True
SHOW_PORT_DESC   = True
GENERATE_MERMAID = True
GENERATE_DRAWIO  = True
GENERATE_VISIO   = True


def load_network_data(topology_file):
    with open(topology_file) as f:
        return json.load(f)


def build_device_map(data):
    """
    Lookup dict keyed by derivedId and serial -> device info.
    Device details come from the topology node's embedded device field,
    enriched with lanIp from the P1 devices list.
    """
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
    """Interface label using LLDP data embedded directly in the topology link end."""
    if not SHOW_PORT_LABELS:
        return ""
    lldp    = (end.get("discovered") or {}).get("lldp") or {}
    port_id = lldp.get("portId", "")
    if not port_id:
        return ""
    # Bare numeric portIds (e.g. "4") are promoted to "Port 4" for readability
    port_str = f"Port {port_id}" if str(port_id).isdigit() else str(port_id)
    if SHOW_PORT_DESC:
        desc = lldp.get("portDescription", "")
        # Only append description if it adds new information beyond port_str
        if desc and desc.lower() not in (
            port_str.lower(),
            str(port_id).lower(),
            f"port {str(port_id)}".lower(),
        ):
            return f"{port_str} ({desc})"
    return port_str


def compute_hierarchy(nodes, links):
    """
    BFS from root nodes to assign depth levels.
    Level 0 = root (MX/firewall), Level 1 = switches, Level 2 = APs/endpoints.
    """
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

    for node in nodes:
        if node["derivedId"] not in levels:
            levels[node["derivedId"]] = 0

    return levels


def build_mermaid(data):
    """Generates a Mermaid flowchart diagram string from topology data."""
    lines      = ["graph TD", "    classDef root fill:#dae8fc,stroke:#6c8ebf,font-weight:bold"]
    topo       = data.get("topology", {})
    nodes      = topo.get("nodes", [])
    links      = topo.get("links", [])
    device_map = build_device_map(data)

    if not nodes:
        # Fallback: LLDP/CDP data
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
                    nbr_name = neighbor.get("systemName") or neighbor.get("deviceId", "Unknown")
                    nbr_id   = "nbr_" + nbr_name.replace(" ", "_").replace(":", "_")[:20]
                    edge_key = tuple(sorted([src_id, nbr_id]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        src_port = neighbor.get("sourcePort", port_id)
                        nbr_port = neighbor.get("portId", "")
                        label    = (f"{src_port} --> {nbr_port}"
                                    if SHOW_PORT_LABELS and nbr_port else str(src_port))
                        lines.append(f'    {nbr_id}["{nbr_name}"]')
                        lines.append(f'    {src_id} -->|"{label}"| {nbr_id}')
        return "\n".join(lines)

    node_id_map   = {}
    root_node_ids = set()
    levels        = compute_hierarchy(nodes, links)

    for idx, node in enumerate(nodes):
        node_id_map[node["derivedId"]] = f"n{idx}"
        if node.get("root", False):
            root_node_ids.add(f"n{idx}")

    lines.append("")
    for node in nodes:
        derived_id = node["derivedId"]
        safe_id    = node_id_map[derived_id]
        label      = get_node_label(derived_id, device_map).replace('"', "'")
        lines.append(f'    {safe_id}["{label}"]')

    if root_node_ids:
        lines.append(f'    class {",".join(sorted(root_node_ids))} root')

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
        # Direct edge from shallower to deeper level
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


def build_drawio(data):
    """Generates draw.io XML (mxGraph format) with hierarchical layout."""
    net_name   = data.get("networkName", "Network")
    topo       = data.get("topology", {})
    nodes      = topo.get("nodes", [])
    links      = topo.get("links", [])
    device_map = build_device_map(data)

    levels    = compute_hierarchy(nodes, links)
    by_level  = {}
    for nid, lvl in levels.items():
        by_level.setdefault(lvl, []).append(nid)
    max_level = max(by_level.keys(), default=0)

    node_w, node_h = 180, 60
    x_gap, y_gap   = 60, 100
    y_start        = 80

    level_positions = {}
    for lvl in range(max_level + 1):
        nids     = by_level.get(lvl, [])
        count    = len(nids)
        total_w  = count * node_w + (count - 1) * x_gap
        x_origin = max(80, 600 - total_w // 2)
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

    node_cell_ids = {}
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
        cell   = ET.SubElement(
            root, "mxCell",
            id=cell_id, value=label, style=style,
            vertex="1", parent="1",
        )
        ET.SubElement(
            cell, "mxGeometry",
            x=str(cx), y=str(cy), width=str(node_w), height=str(node_h),
            **{"as": "geometry"},
        )

    for lidx, link in enumerate(links):
        ends = link.get("ends", [])
        if len(ends) != 2:
            continue
        a_id   = node_cell_ids.get(ends[0]["node"]["derivedId"])
        b_id   = node_cell_ids.get(ends[1]["node"]["derivedId"])
        if not a_id or not b_id:
            continue
        a_port = get_port_label(ends[0])
        b_port = get_port_label(ends[1])
        edge_id = f"edge_{lidx}"

        # No fixed exit/entry points — let draw.io auto-route each edge
        # independently so multiple edges from the same device fan out
        # rather than stacking on top of each other.
        edge = ET.SubElement(
            root, "mxCell",
            id=edge_id, value="",
            style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;",
            edge="1", source=a_id, target=b_id, parent="1",
        )
        ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})

        # Source-end port label — floated close to source device (x=-0.8)
        if a_port:
            src_lbl = ET.SubElement(
                root, "mxCell",
                id=f"lbl_{lidx}_a", value=a_port,
                style=(
                    "edgeLabel;html=1;align=center;verticalAlign=middle;"
                    "resizable=0;points=[];fontSize=9;"
                ),
                vertex="1", connectable="0", parent=edge_id,
            )
            g = ET.SubElement(src_lbl, "mxGeometry", relative="1", **{"as": "geometry"})
            g.set("x", "-0.8")

        # Target-end port label — floated close to target device (x=0.8)
        if b_port:
            tgt_lbl = ET.SubElement(
                root, "mxCell",
                id=f"lbl_{lidx}_b", value=b_port,
                style=(
                    "edgeLabel;html=1;align=center;verticalAlign=middle;"
                    "resizable=0;points=[];fontSize=9;"
                ),
                vertex="1", connectable="0", parent=edge_id,
            )
            g = ET.SubElement(tgt_lbl, "mxGeometry", relative="1", **{"as": "geometry"})
            g.set("x", "0.8")

    return ET.tostring(mxfile, encoding="unicode", xml_declaration=False)


def build_visio(data):
    """
    Generates a .vsdx Visio file (as bytes) with hierarchical layout.
    Uses only Python standard library — no extra packages required.
    Open the output .vsdx file directly in Microsoft Visio.
    """
    net_name   = data.get("networkName", "Network")
    topo       = data.get("topology", {})
    nodes      = topo.get("nodes", [])
    links      = topo.get("links", [])
    device_map = build_device_map(data)
    levels     = compute_hierarchy(nodes, links)

    # Layout (inches; Visio Y=0 is bottom of page, Y increases upward)
    page_w, page_h = 11.0, 8.5
    node_w, node_h = 2.0,  0.6
    x_gap,  y_gap  = 0.5,  1.5
    y_top          = page_h - 0.8   # top-most level sits here

    by_level = {}
    for nid, lvl in levels.items():
        by_level.setdefault(lvl, []).append(nid)
    max_level = max(by_level.keys(), default=0)

    positions = {}
    for lvl in range(max_level + 1):
        nids    = by_level.get(lvl, [])
        count   = len(nids)
        total_w = count * node_w + (count - 1) * x_gap
        x_start = (page_w - total_w) / 2 + node_w / 2
        cy      = y_top - lvl * y_gap
        for i, nid in enumerate(nids):
            positions[nid] = (x_start + i * (node_w + x_gap), cy)

    shape_ids = {node["derivedId"]: idx + 1 for idx, node in enumerate(nodes)}

    def _esc(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    shapes_parts   = []
    connects_parts = []
    connector_id   = 1000
    label_id       = 2000

    # Node shapes
    for node in nodes:
        did    = node["derivedId"]
        sid    = shape_ids[did]
        label  = _esc(get_node_label(did, device_map, separator="&#xa;"))
        cx, cy = positions.get(did, (5.5, 4.25))
        is_root = node.get("root", False)
        fill   = "#dae8fc" if is_root else "#ffffff"
        stroke = "#6c8ebf" if is_root else "#000000"
        bold   = "1"       if is_root else "0"
        shapes_parts.append(
            f'    <Shape ID="{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">\n'
            f'      <XForm>\n'
            f'        <PinX>{cx:.4f}</PinX>\n'
            f'        <PinY>{cy:.4f}</PinY>\n'
            f'        <Width>{node_w}</Width>\n'
            f'        <Height>{node_h}</Height>\n'
            f'        <LocPinX F="Width*0.5">{node_w / 2}</LocPinX>\n'
            f'        <LocPinY F="Height*0.5">{node_h / 2}</LocPinY>\n'
            f'      </XForm>\n'
            f'      <Fill><FillForegnd>{fill}</FillForegnd><FillBkgnd>#ffffff</FillBkgnd></Fill>\n'
            f'      <Line><LineColor>{stroke}</LineColor><LineWeight>0.01389</LineWeight></Line>\n'
            f'      <Char><Style>{bold}</Style><Size>0.1389</Size></Char>\n'
            f'      <Text>{label}</Text>\n'
            f'    </Shape>'
        )

    # Connector + per-end port label shapes
    for lidx, link in enumerate(links):
        ends = link.get("ends", [])
        if len(ends) != 2:
            continue
        a_did = ends[0]["node"]["derivedId"]
        b_did = ends[1]["node"]["derivedId"]
        a_sid = shape_ids.get(a_did)
        b_sid = shape_ids.get(b_did)
        if not a_sid or not b_sid:
            continue

        a_cx, a_cy = positions.get(a_did, (5.5, 4.25))
        b_cx, b_cy = positions.get(b_did, (5.5, 2.75))

        # Connector: source center-bottom -> target center-top
        bx = a_cx;  by = a_cy - node_h / 2
        ex = b_cx;  ey = b_cy + node_h / 2

        shapes_parts.append(
            f'    <Shape ID="{connector_id}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">\n'
            f'      <XForm1D>\n'
            f'        <BeginX>{bx:.4f}</BeginX>\n'
            f'        <BeginY>{by:.4f}</BeginY>\n'
            f'        <EndX>{ex:.4f}</EndX>\n'
            f'        <EndY>{ey:.4f}</EndY>\n'
            f'      </XForm1D>\n'
            f'      <Line><LineWeight>0.01389</LineWeight><EndArrow>4</EndArrow></Line>\n'
            f'    </Shape>'
        )
        connects_parts.append(
            f'  <Connect FromSheet="{connector_id}" FromCell="BeginX" ToSheet="{a_sid}" ToCell="PinX"/>'
        )
        connects_parts.append(
            f'  <Connect FromSheet="{connector_id}" FromCell="EndX"   ToSheet="{b_sid}" ToCell="PinX"/>'
        )
        connector_id += 1

        # Port label near source (just below source shape)
        a_port = get_port_label(ends[0])
        if a_port:
            lx = bx + 0.15;  ly = by - 0.20
            shapes_parts.append(
                f'    <Shape ID="{label_id}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">\n'
                f'      <XForm>\n'
                f'        <PinX>{lx:.4f}</PinX><PinY>{ly:.4f}</PinY>\n'
                f'        <Width>1.2</Width><Height>0.22</Height>\n'
                f'        <LocPinX F="Width*0.5">0.6</LocPinX><LocPinY F="Height*0.5">0.11</LocPinY>\n'
                f'      </XForm>\n'
                f'      <Fill><FillPattern>0</FillPattern></Fill>\n'
                f'      <Line><LinePattern>0</LinePattern></Line>\n'
                f'      <Char><Size>0.0972</Size></Char>\n'
                f'      <Text>{_esc(a_port)}</Text>\n'
                f'    </Shape>'
            )
            label_id += 1

        # Port label near target (just above target shape)
        b_port = get_port_label(ends[1])
        if b_port:
            lx = ex + 0.15;  ly = ey + 0.20
            shapes_parts.append(
                f'    <Shape ID="{label_id}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">\n'
                f'      <XForm>\n'
                f'        <PinX>{lx:.4f}</PinX><PinY>{ly:.4f}</PinY>\n'
                f'        <Width>1.2</Width><Height>0.22</Height>\n'
                f'        <LocPinX F="Width*0.5">0.6</LocPinX><LocPinY F="Height*0.5">0.11</LocPinY>\n'
                f'      </XForm>\n'
                f'      <Fill><FillPattern>0</FillPattern></Fill>\n'
                f'      <Line><LinePattern>0</LinePattern></Line>\n'
                f'      <Char><Size>0.0972</Size></Char>\n'
                f'      <Text>{_esc(b_port)}</Text>\n'
                f'    </Shape>'
            )
            label_id += 1

    shapes_xml   = "\n".join(shapes_parts)
    connects_xml = "\n".join(connects_parts)

    # ---- Build .vsdx XML parts ----
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>\n'
        '  <Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>\n'
        '  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>\n'
        '</Types>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" '
        'Type="http://schemas.microsoft.com/visio/2010/relationships/document" '
        'Target="visio/document.xml"/>\n'
        '</Relationships>'
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main"\n'
        '               xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <DocumentSheet UniqueID="{00000000-0000-0000-0000-000000000001}">\n'
        '    <StyleSheets>\n'
        '      <StyleSheet ID="0" NameU="Normal" IsCustomName="0" IsCustomNameU="0"\n'
        '                  LineStyle="0" FillStyle="0" TextStyle="0">\n'
        '        <Line><LineWeight>0.01389</LineWeight><LineColor>#000000</LineColor><LinePattern>1</LinePattern></Line>\n'
        '        <Fill><FillForegnd>#ffffff</FillForegnd><FillPattern>1</FillPattern></Fill>\n'
        '        <Char><Size>0.1389</Size></Char>\n'
        '      </StyleSheet>\n'
        '    </StyleSheets>\n'
        '  </DocumentSheet>\n'
        '  <Pages r:id="rId1"/>\n'
        '</VisioDocument>'
    )
    document_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" '
        'Type="http://schemas.microsoft.com/visio/2010/relationships/pages" '
        'Target="pages/pages.xml"/>\n'
        '</Relationships>'
    )
    pages_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main"\n'
        '       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <Page ID="1" NameU="Page-1" Name="Page-1" r:id="rId1"/>\n'
        '</Pages>'
    )
    pages_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" '
        'Type="http://schemas.microsoft.com/visio/2010/relationships/page" '
        'Target="page1.xml"/>\n'
        '</Relationships>'
    )
    page1_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main"\n'
        '              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"\n'
        '              xml:space="preserve">\n'
        '  <Shapes>\n'
        f'{shapes_xml}\n'
        '  </Shapes>\n'
        '  <Connects>\n'
        f'{connects_xml}\n'
        '  </Connects>\n'
        '</PageContents>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",               content_types_xml)
        zf.writestr("_rels/.rels",                        rels_xml)
        zf.writestr("visio/document.xml",                 document_xml)
        zf.writestr("visio/_rels/document.xml.rels",      document_rels_xml)
        zf.writestr("visio/pages/pages.xml",              pages_xml)
        zf.writestr("visio/pages/_rels/pages.xml.rels",   pages_rels_xml)
        zf.writestr("visio/pages/page1.xml",              page1_xml)
    return buf.getvalue()


def add_notes_to_drawio(drawio_str, notes):
    """Appends engineer notes as a yellow text box inside the draw.io diagram."""
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
    """List of network-wide setting strings for engineer troubleshooting."""
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


def save_diagrams(network_name, mermaid_str, drawio_str, data, notes, output_dir):
    safe_name = "".join(
        c if c.isalnum() or c in " -_." else "_" for c in network_name
    )
    folder = os.path.join(output_dir, safe_name)
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
            f.write(add_notes_to_drawio(drawio_str, notes))
        print(f"  draw.io  --> {drawio_path}")

    if GENERATE_VISIO:
        visio_bytes = build_visio(data)
        visio_path  = os.path.join(folder, "diagram.vsdx")
        with open(visio_path, "wb") as f:
            f.write(visio_bytes)
        print(f"  Visio    --> {visio_path}")


def run(config):
    """Entry point for Phase 2 — generate diagrams from collected topology JSON."""
    global SHOW_MODEL, SHOW_SERIAL, SHOW_IP, SHOW_PORT_LABELS
    global SHOW_PORT_DESC, GENERATE_MERMAID, GENERATE_DRAWIO, GENERATE_VISIO

    SHOW_MODEL       = config.get("show_model", True)
    SHOW_SERIAL      = config.get("show_serial", False)
    SHOW_IP          = config.get("show_ip", True)
    SHOW_PORT_LABELS = config.get("show_port_labels", True)
    SHOW_PORT_DESC   = config.get("show_port_desc", True)
    GENERATE_MERMAID = config.get("generate_mermaid", True)
    GENERATE_DRAWIO  = config.get("generate_drawio", True)
    GENERATE_VISIO   = config.get("generate_visio", True)
    output_dir       = config.get("output_dir", "Network Diagram")

    print("\n" + "=" * 60)
    print("Meraki Network Diagram Generator -- Phase 2")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    topology_files = glob.glob(
        os.path.join(output_dir, "**", "topology.json"), recursive=True
    )

    if not topology_files:
        print(f"No topology.json files found in '{output_dir}/'")
        print("Phase 1 must complete successfully before running Phase 2.")
        return

    print(f"Found {len(topology_files)} network(s) to diagram.\n")

    for topo_file in sorted(topology_files):
        data     = load_network_data(topo_file)
        net_name = data.get("networkName", os.path.basename(os.path.dirname(topo_file)))
        print(f"Generating: {net_name}")
        mermaid_str = build_mermaid(data)
        drawio_str  = build_drawio(data)
        notes       = build_engineer_notes(data)
        save_diagrams(net_name, mermaid_str, drawio_str, data, notes, output_dir)

    print("\n" + "=" * 60)
    print(f"Phase 2 complete. {len(topology_files)} diagram(s) generated.")
    print("=" * 60)

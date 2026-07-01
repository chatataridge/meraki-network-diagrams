"""Phase 1: Fetch Meraki topology data and network settings, save as JSON."""

import meraki
import json
import os
import pandas as pd
from datetime import datetime


def get_dashboard(api_key):
    return meraki.DashboardAPI(
        api_key,
        suppress_logging=True,
        wait_on_rate_limit=True,
        output_log=False,
        print_console=False,
    )


def get_organizations(dashboard):
    print("Fetching organizations...")
    data = dashboard.organizations.getOrganizations()
    print(f"  Found {len(data)} organization(s).")
    return data


def get_networks(dashboard, org_id):
    print(f"Fetching networks for org {org_id}...")
    data = dashboard.organizations.getOrganizationNetworks(
        org_id, total_pages="all"
    )
    print(f"  Found {len(data)} network(s).")
    return data


def get_devices(dashboard, network_id):
    return dashboard.networks.getNetworkDevices(network_id)


def get_topology(dashboard, network_id):
    try:
        return dashboard.networks.getNetworkTopologyLinkLayer(network_id)
    except meraki.APIError:
        return None


def get_lldp_cdp(dashboard, serial):
    try:
        return dashboard.devices.getDeviceLldpCdp(serial)
    except meraki.APIError:
        return None


def get_switch_settings(dashboard, network_id):
    settings = {}
    calls = [
        ("stp",              dashboard.switch.getNetworkSwitchStp),
        ("stormControl",     dashboard.switch.getNetworkSwitchStormControl),
        ("mtu",              dashboard.switch.getNetworkSwitchMtu),
        ("accessPolicies",   dashboard.switch.getNetworkSwitchAccessPolicies),
        ("dhcpServerPolicy", dashboard.switch.getNetworkSwitchDhcpServerPolicy),
    ]
    for key, method in calls:
        try:
            result = method(network_id)
            if result:
                settings[key] = result
        except meraki.APIError:
            pass
    return settings


def get_vlans(dashboard, network_id):
    try:
        return dashboard.appliance.getNetworkApplianceVlans(network_id)
    except meraki.APIError:
        return []


def get_switch_ports(dashboard, serial):
    try:
        ports = dashboard.switch.getDeviceSwitchPorts(serial)
        return {str(p["portId"]): p for p in ports}
    except meraki.APIError:
        return {}


def save_network_data(network_name, data, output_dir):
    safe_name = "".join(
        c if c.isalnum() or c in " -_." else "_" for c in network_name
    )
    folder   = os.path.join(output_dir, safe_name)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, "topology.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def run(config):
    """Entry point for Phase 1 — collect topology data for all networks."""
    print("=" * 60)
    print("Meraki Network Topology Capture -- Phase 1")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    api_key    = config["api_key"]
    org_id     = config.get("org_id", "")
    output_dir = config.get("output_dir", "Network Diagram")
    net_filter = config.get("network_filter", [])

    dashboard = get_dashboard(api_key)

    if not org_id:
        orgs = get_organizations(dashboard)
        if not orgs:
            print("ERROR: No organizations found. Check your API key.")
            return
        org_id = orgs[0]["id"]
        print(f"Using org: {orgs[0]['name']} (ID: {org_id})")

    all_networks = get_networks(dashboard, org_id)
    if net_filter:
        all_networks = [n for n in all_networks if n["name"] in net_filter]
        print(f"Filtered to {len(all_networks)} network(s).")

    summary = []

    for i, network in enumerate(all_networks, 1):
        net_id   = network["id"]
        net_name = network["name"]
        net_type = network.get("productTypes", [])
        print(f"\n[{i}/{len(all_networks)}] {net_name} ({', '.join(net_type)})")

        network_data = {
            "networkId":      net_id,
            "networkName":    net_name,
            "productTypes":   net_type,
            "collectedAt":    datetime.now().isoformat(),
            "devices":        [],
            "topology":       {},
            "lldpCdp":        {},
            "switchSettings": {},
            "vlans":          [],
            "portDetails":    {},
        }

        # Devices
        devices = get_devices(dashboard, net_id)
        network_data["devices"] = devices
        print(f"  Devices: {len(devices)}")

        # Topology
        topo = get_topology(dashboard, net_id)
        if topo and topo.get("nodes"):
            network_data["topology"] = topo
            print(f"  Topology: {len(topo.get('nodes', []))} nodes, "
                  f"{len(topo.get('links', []))} links")
        else:
            print("  Topology: No link-layer data -- falling back to LLDP/CDP")
            lldp_data = {}
            for device in devices:
                serial = device.get("serial")
                if serial:
                    lldp = get_lldp_cdp(dashboard, serial)
                    if lldp:
                        lldp_data[serial] = lldp
            network_data["lldpCdp"] = lldp_data
            print(f"  LLDP/CDP: {len(lldp_data)} device(s)")

        # Switch settings
        if config.get("include_switch_settings") and "switch" in net_type:
            sw = get_switch_settings(dashboard, net_id)
            network_data["switchSettings"] = sw
            print(f"  Switch settings: {list(sw.keys())}")

        # VLANs
        if config.get("include_vlans") and "appliance" in net_type:
            vlans = get_vlans(dashboard, net_id)
            network_data["vlans"] = vlans
            print(f"  VLANs: {len(vlans)}")

        # Port details
        if config.get("include_port_details") and "switch" in net_type:
            port_map = {}
            for device in devices:
                if device.get("model", "").startswith("MS"):
                    serial = device["serial"]
                    ports  = get_switch_ports(dashboard, serial)
                    if ports:
                        port_map[serial] = ports
            network_data["portDetails"] = port_map
            print(f"  Port details: {len(port_map)} switch(es)")

        filepath = save_network_data(net_name, network_data, output_dir)
        print(f"  Saved --> {filepath}")

        summary.append({
            "Network Name":  net_name,
            "Product Types": ", ".join(net_type),
            "Device Count":  len(devices),
            "Has Topology":  bool(network_data["topology"]),
            "VLAN Count":    len(network_data["vlans"]),
            "Output File":   filepath,
        })

    if summary:
        df           = pd.DataFrame(summary)
        summary_path = os.path.join(output_dir, "collection_summary.xlsx")
        df.to_excel(summary_path, index=False)
        print(f"\nCollection summary --> {summary_path}")

    print("\n" + "=" * 60)
    print(f"Phase 1 complete. {len(summary)} network(s) processed.")
    print("=" * 60)

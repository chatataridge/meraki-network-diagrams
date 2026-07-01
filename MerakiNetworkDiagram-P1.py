import meraki
import json
import os
import pandas as pd
from datetime import datetime

# --- Configuration: UPDATE THESE VALUES ---
API_KEY                 = "your_api_key_here"
ORG_ID                  = ""               # Leave blank to auto-discover from /organizations
OUTPUT_DIR              = "Network Diagram"
NETWORK_FILTER          = []               # Leave empty for all networks, e.g. ["Site-A", "HQ"]
INCLUDE_SWITCH_SETTINGS = True             # STP, storm control, MTU, access policies, DHCP policy
INCLUDE_VLANS           = True             # VLAN list (appliance/MX networks)
INCLUDE_PORT_DETAILS    = True             # Switch port names/descriptions for interface labels


def get_dashboard():
    """Initializes the Meraki SDK client. Rate limiting and retries are automatic."""
    return meraki.DashboardAPI(
        API_KEY,
        suppress_logging=True,   # Suppress verbose per-request SDK output
        wait_on_rate_limit=True, # Auto-retry if rate limit is hit
        output_log=False,        # No SDK log file
        print_console=False,     # No SDK console output
    )


def get_organizations(dashboard):
    """Fetches all organizations accessible with the API key."""
    print("Fetching organizations...")
    data = dashboard.organizations.getOrganizations()
    print(f"  Found {len(data)} organization(s).")
    return data


def get_networks(dashboard, org_id):
    """Fetches all networks in an organization (pagination handled by SDK)."""
    print(f"Fetching networks for org {org_id}...")
    data = dashboard.organizations.getOrganizationNetworks(
        org_id, total_pages="all"
    )
    print(f"  Found {len(data)} network(s).")
    return data


def get_devices(dashboard, network_id):
    """Fetches all devices in a network."""
    return dashboard.networks.getNetworkDevices(network_id)


def get_topology(dashboard, network_id):
    """Fetches link-layer topology (nodes + links) for a network."""
    try:
        return dashboard.networks.getNetworkTopologyLinkLayer(network_id)
    except meraki.APIError:
        return None


def get_lldp_cdp(dashboard, serial):
    """Fetches LLDP/CDP neighbor data for a device (fallback topology source)."""
    try:
        return dashboard.devices.getDeviceLldpCdp(serial)
    except meraki.APIError:
        return None


def get_switch_settings(dashboard, network_id):
    """Collects network-wide switch settings useful for troubleshooting."""
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
    """Fetches VLAN configuration for appliance/MX networks."""
    try:
        return dashboard.appliance.getNetworkApplianceVlans(network_id)
    except meraki.APIError:
        return []


def get_switch_ports(dashboard, serial):
    """Fetches switch port details including names/descriptions for interface labels."""
    try:
        ports = dashboard.switch.getDeviceSwitchPorts(serial)
        return {str(p["portId"]): p for p in ports}
    except meraki.APIError:
        return {}


def save_network_data(network_name, data):
    """Saves collected network data as JSON to the output directory."""
    safe_name = "".join(c if c.isalnum() or c in " -_." else "_" for c in network_name)
    folder    = os.path.join(OUTPUT_DIR, safe_name)
    os.makedirs(folder, exist_ok=True)
    filepath  = os.path.join(folder, "topology.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def main():
    print("=" * 60)
    print("Meraki Network Topology Capture -- Phase 1")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Initialize SDK client (handles rate limiting and retries automatically)
    dashboard = get_dashboard()

    # Resolve org ID
    org_id = ORG_ID
    if not org_id:
        orgs = get_organizations(dashboard)
        if not orgs:
            print("ERROR: No organizations found. Check your API key.")
            return
        org_id = orgs[0]["id"]
        print(f"Using org: {orgs[0]['name']} (ID: {org_id})")

    # Fetch all networks
    all_networks = get_networks(dashboard, org_id)
    if NETWORK_FILTER:
        all_networks = [n for n in all_networks if n["name"] in NETWORK_FILTER]
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

        # Topology via official link-layer API
        topo = get_topology(dashboard, net_id)
        if topo and topo.get("nodes"):
            network_data["topology"] = topo
            print(f"  Topology: {len(topo.get('nodes', []))} nodes, "
                  f"{len(topo.get('links', []))} links")
        else:
            # Fallback: LLDP/CDP per device
            print("  Topology: No link-layer data -- falling back to LLDP/CDP per device")
            lldp_data = {}
            for device in devices:
                serial = device.get("serial")
                if serial:
                    lldp = get_lldp_cdp(dashboard, serial)
                    if lldp:
                        lldp_data[serial] = lldp
            network_data["lldpCdp"] = lldp_data
            print(f"  LLDP/CDP: collected for {len(lldp_data)} device(s)")

        # Switch settings: STP, storm control, MTU, access policies, DHCP policy
        if INCLUDE_SWITCH_SETTINGS and "switch" in net_type:
            sw_settings = get_switch_settings(dashboard, net_id)
            network_data["switchSettings"] = sw_settings
            print(f"  Switch settings: {list(sw_settings.keys())}")

        # VLANs
        if INCLUDE_VLANS and "appliance" in net_type:
            vlans = get_vlans(dashboard, net_id)
            network_data["vlans"] = vlans
            print(f"  VLANs: {len(vlans)}")

        # Port details for interface labels on MS switches
        if INCLUDE_PORT_DETAILS and "switch" in net_type:
            port_map = {}
            for device in devices:
                if device.get("model", "").startswith("MS"):
                    serial = device["serial"]
                    ports  = get_switch_ports(dashboard, serial)
                    if ports:
                        port_map[serial] = ports
            network_data["portDetails"] = port_map
            print(f"  Port details: {len(port_map)} switch(es)")

        # Save network data
        filepath = save_network_data(net_name, network_data)
        print(f"  Saved --> {filepath}")

        summary.append({
            "Network Name":   net_name,
            "Product Types":  ", ".join(net_type),
            "Device Count":   len(devices),
            "Has Topology":   bool(network_data["topology"]),
            "VLAN Count":     len(network_data["vlans"]),
            "Output File":    filepath,
        })

    # Write summary Excel
    if summary:
        df = pd.DataFrame(summary)
        summary_path = os.path.join(OUTPUT_DIR, "collection_summary.xlsx")
        df.to_excel(summary_path, index=False)
        print(f"\nSummary saved --> {summary_path}")

    print("\n" + "=" * 60)
    print(f"Complete. {len(summary)} network(s) processed.")
    print("=" * 60)


if __name__ == "__main__":
    main()

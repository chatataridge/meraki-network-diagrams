"""
Meraki Network Diagram Generator
---------------------------------
Run this file to generate topology diagrams for all networks in your Meraki org.

  python main.py

Diagrams are saved to the 'Network Diagram' folder:
  .mmd    -> open in VS Code with the Mermaid Preview extension
  .drawio -> open at https://app.diagrams.net

Configuration:
  Credentials  -> edit .env
  Diagram options -> edit the config block below
"""

import os
from dotenv import load_dotenv
from meraki_diagrams import collect, diagram

# Load MERAKI_API_KEY and ORG_ID from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration — edit these to control what is collected and how diagrams look
# ---------------------------------------------------------------------------
OUTPUT_DIR               = "Network Diagram"
NETWORK_FILTER           = []      # [] = all networks; or ["Site-A", "HQ"] to limit scope

# Data collection options
INCLUDE_SWITCH_SETTINGS  = True    # STP, storm control, MTU, access policies, DHCP policy
INCLUDE_VLANS            = True    # VLAN list (appliance/MX networks)
INCLUDE_PORT_DETAILS     = True    # Switch port names for interface labels

# Diagram output options
GENERATE_MERMAID         = True    # Output .mmd files
GENERATE_DRAWIO          = True    # Output .drawio files
GENERATE_VISIO           = True    # Output .vsdx files (open in Microsoft Visio)

# Node label options
SHOW_MODEL               = True    # e.g. MS225, MX68
SHOW_SERIAL              = False   # Serial number (disable for customer sharing)
SHOW_IP                  = True    # Management IP address

# Edge label options
SHOW_PORT_LABELS         = True    # Interface names on connections
SHOW_PORT_DESC           = True    # Port descriptions alongside port IDs
# ---------------------------------------------------------------------------


def validate_config(config):
    if not config["api_key"]:
        print("ERROR: MERAKI_API_KEY is not set.")
        print("  1. Copy .env.example to .env")
        print("  2. Add your Meraki API key to .env")
        return False
    return True


if __name__ == "__main__":

    config = {
        "api_key":                os.getenv("MERAKI_API_KEY", ""),
        "org_id":                 os.getenv("ORG_ID", ""),
        "output_dir":             OUTPUT_DIR,
        "network_filter":         NETWORK_FILTER,
        "include_switch_settings": INCLUDE_SWITCH_SETTINGS,
        "include_vlans":          INCLUDE_VLANS,
        "include_port_details":   INCLUDE_PORT_DETAILS,
        "generate_mermaid":       GENERATE_MERMAID,
        "generate_drawio":        GENERATE_DRAWIO,
        "generate_visio":         GENERATE_VISIO,
        "show_model":             SHOW_MODEL,
        "show_serial":            SHOW_SERIAL,
        "show_ip":                SHOW_IP,
        "show_port_labels":       SHOW_PORT_LABELS,
        "show_port_desc":         SHOW_PORT_DESC,
    }

    if not validate_config(config):
        exit(1)

    # Phase 1: Collect topology data from Meraki API
    collect.run(config)

    # Phase 2: Generate Mermaid and draw.io diagrams
    diagram.run(config)

    print("\n" + "=" * 60)
    print("All done!")
    print(f"  Diagrams saved to: {OUTPUT_DIR}/")
    print("  .mmd   -> VS Code: Ctrl+Shift+P -> 'Mermaid: Open Preview'")
    print("  .drawio -> https://app.diagrams.net -> Open Existing Diagram")
    print("=" * 60)

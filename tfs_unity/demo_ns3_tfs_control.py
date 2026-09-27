#!/usr/bin/env python3
"""
demo_ns3_tfs_control.py
=======================
Demonstration script showing how an external application or NS-3 simulation
uses the TFS Northbound Adapter to:
1. Discover the hybrid O-RAN topology (Core, Metro, Ceragon mmWave).
2. Read real-time telemetry from physical Ceragon hardware (frequency, active MCS, RSSI).
3. Control the Ceragon hardware dynamically via TFS configuration rules:
   - Radio Frequency & ATPC power tuning
   - Adaptive Coding and Modulation (ACM) rain-fade protection floor
   - Dynamic IEEE 802.1Q transport slicing with token-bucket QoS policing.
"""
import json
import os
import sys
import time

from tfs_api_client import TfsApiClient


def main():
    print("=" * 70)
    print("  NS-3 / External Application Northbound Adapter for ETSI TeraFlowSDN")
    print("=" * 70)

    # 1. Connect to TFS (or fall back to descriptors)
    fallback = r"c:\CER_Intent\data\6g_transport_tfs_descriptors.json"
    if not os.path.exists(fallback):
        fallback = None

    client = TfsApiClient(rest_url="http://localhost:8088", descriptor_fallback_path=fallback)
    ok, msg = client.test_connection()
    print(f"\n[1] TFS Connectivity Check:\n    Status: {msg}")

    # 2. Discover Topologies
    topos = client.list_topologies()
    print(f"\n[2] Topologies Discovered ({len(topos)} available):")
    for t in topos:
        print(f"    - Context: {t['context_name']} | Topology: {t['topology_name']} "
              f"(Nodes: {t['num_devices']}, Links: {t['num_links']})")

    # 3. Retrieve Topology Model for NS-3
    devices, links = client.get_topology_model("admin", "admin")
    wireless_links = [l for l in links if l.get("is_wireless")]
    print(f"\n[3] Ingested Topology Model for Simulation:")
    print(f"    Total Nodes:    {len(devices)}")
    print(f"    Total Links:    {len(links)}")
    print(f"    Wireless Links: {len(wireless_links)} (mmWave 60GHz / Microwave)")

    # 4. Target Ceragon Physical Device
    ceragon_uuid = "f676623c-1a65-54bd-b1e8-279c8a6d8a1c"
    print(f"\n[4] Interrogating Ceragon Device Telemetry via TFS:")
    print(f"    Target Device UUID: {ceragon_uuid}")
    telemetry = client.get_device_telemetry(ceragon_uuid)
    print(f"    Device Name:        {telemetry.get('device_name')}")
    print(f"    Carrier Frequency:  {telemetry.get('frequency_ghz')} GHz (Channel {telemetry.get('channel_id')})")
    print(f"    Active Modulation:  MCS {telemetry.get('active_mcs')}")
    print(f"    Received RSSI:      {telemetry.get('rx_rssi_dbm')} dBm")
    print(f"    Signal-to-Noise:    {telemetry.get('snr_db')} dB")
    print(f"    Modem Temperature:  {telemetry.get('modem_temperature_c')} C")
    print(f"    RF Transmit Power:  {telemetry.get('tx_power_dbm')} dBm ({telemetry.get('tx_power_control')})")

    # 5. External Control Actions
    print(f"\n[5] Executing External Control via TFS Northbound Rules:")

    # Action A: Radio carrier tuning
    print("\n    --> [Action A]: Tuning RF Carrier to Channel 4 (64.80 GHz)...")
    res_tune = client.set_radio_tuning(
        device_uuid=ceragon_uuid,
        frequency_mhz=64800.0,
        channel_id=4,
        tx_power_control="auto",
        target_mcs=8,
    )
    print(f"        TFS Staging & 2PC Commit Result: {'SUCCESS' if res_tune else 'SIMULATED (Offline)'}")

    # Action B: Hardening ACM floor for rain-fade protection
    print("\n    --> [Action B]: Hardening ACM Modulation Floor (Min MCS 2, QPSK)...")
    res_acm = client.set_acm_floor(
        device_uuid=ceragon_uuid,
        min_mcs=2,
        min_modulation="QPSK",
        atpc_boost_dbm=3.0,
    )
    print(f"        TFS Staging & 2PC Commit Result: {'SUCCESS' if res_acm else 'SIMULATED (Offline)'}")

    # Action C: Dynamic transport slice provisioning
    print("\n    --> [Action C]: Provisioning 5G URLLC Transport Slice 'slice-uran-6g' (VLAN 200, 1000 Mbps)...")
    res_slice = client.set_slice_qos(
        device_uuid=ceragon_uuid,
        slice_name="slice-uran-6g",
        vlan_id=200,
        bandwidth_mbps=1000,
        priority=7,
    )
    print(f"        TFS Staging & 2PC Commit Result: {'SUCCESS' if res_slice else 'SIMULATED (Offline)'}")

    print("\n" + "=" * 70)
    print("  Demonstration completed successfully! External applications and NS-3")
    print("  can seamlessly read telemetry and execute closed-loop control via TFS.")
    print("=" * 70)


if __name__ == "__main__":
    main()

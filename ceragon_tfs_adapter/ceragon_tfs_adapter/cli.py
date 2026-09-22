"""
Ceragon TFS Adapter CLI
=======================
Command-line interface for device discovery, TFS synchronization, status checking, and daemon execution.
"""
from __future__ import annotations

import json
import logging
import sys
import click

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.client import CeragonRestClient
from ceragon_tfs_adapter.driver import TFSCeragonDriver
from ceragon_tfs_adapter.service import AdapterService
from ceragon_tfs_adapter.registrar import TFSRegistrar


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logging.")
def main(verbose: bool) -> None:
    """Ceragon TeraFlowSDN (TFS) Device Adapter CLI."""
    configure_logging(verbose)


@main.command()
@click.option("--ip", default=None, help="Ceragon device management IP (default: 192.168.1.225).")
@click.option("--port", default=None, type=int, help="Ceragon management port (default: 80).")
@click.option("--user", default=None, help="Username (default: admin).")
@click.option("--password", default=None, help="Password (default: admin).")
def discover(ip, port, user, password) -> None:
    """Probe connected Ceragon device and print inventory, interfaces, and radio state."""
    cfg = AdapterConfig()
    if ip: cfg.device_ip = ip
    if port: cfg.device_port = port
    if user: cfg.username = user
    if password: cfg.password = password

    click.echo(f"[*] Probing Ceragon device at {cfg.ceragon_base_url}...")
    client = CeragonRestClient(cfg)
    ok, msg = client.test_connection()
    if not ok:
        click.secho(f"[!] Connection failed: {msg}", fg="red")
        sys.exit(1)

    click.secho(f"[+] {msg}", fg="green")
    click.echo("[*] Fetching live operational state...")
    try:
        state = client.get_device_state()
        click.echo("\n" + "=" * 60)
        click.secho(f"  Device: {state.vendor} {state.model} ({state.node_name})", bold=True)
        click.echo("=" * 60)
        click.echo(f"  Serial Number:    {state.serial_number}")
        click.echo(f"  Hardware Rev:     {state.hardware_rev}")
        click.echo(f"  Software Rev:     {state.software_version}")
        click.echo(f"  Operation Mode:   {state.operation_mode}")
        click.echo(f"  Uptime:           {state.uptime}")
        click.echo(f"  Operational:      {'YES' if state.is_operational else 'NO'}")
        click.echo(f"  Max Throughput:   {state.max_throughput_gbps} Gbps")

        click.echo("\n  [Network Interfaces]")
        for iface in state.interfaces:
            click.echo(f"   - {iface.name}: {iface.description} | Speed: {iface.speed_gbps}G | Oper: {iface.oper_status.upper()}")

        click.echo("\n  [Radio Sectors]")
        for sec in state.sectors:
            click.echo(f"   - Sector {sec.index}: Freq {sec.frequency_ghz} GHz ({sec.frequency_mhz} MHz) | Antenna: {sec.antenna_mode} | Temp: {sec.modem_temperature_c} C | Oper: {sec.admin_status.upper()}")
        click.echo("=" * 60 + "\n")
    except Exception as e:
        click.secho(f"[!] Error fetching device state: {e}", fg="red")
        sys.exit(1)


@main.command()
@click.option("--ip", default=None, help="Ceragon device management IP.")
@click.option("--tfs-url", default=None, help="TeraFlowSDN base URL (default: http://localhost:8088).")
@click.option("--context", default=None, help="TFS Context name (default: admin).")
@click.option("--topology", default=None, help="TFS Topology name (default: admin).")
def sync(ip, tfs_url, context, topology) -> None:
    """Synchronize live Ceragon device into TeraFlowSDN Context and Topology."""
    cfg = AdapterConfig()
    if ip: cfg.device_ip = ip
    if tfs_url: cfg.tfs_url = tfs_url.rstrip("/")
    if context: cfg.tfs_context = context
    if topology: cfg.tfs_topology = topology

    click.echo(f"[*] Connecting to Ceragon ({cfg.ceragon_base_url}) and TFS ({cfg.tfs_url})...")
    driver = TFSCeragonDriver(cfg)
    
    # Check TFS
    ok_tfs, msg_tfs = driver.registrar.test_tfs_connection()
    if not ok_tfs:
        click.secho(f"[!] TFS Connection failed: {msg_tfs}", fg="red")
        sys.exit(1)
    click.secho(f"[+] {msg_tfs}", fg="green")

    # Sync
    click.echo("[*] Fetching device state and pushing to TFS...")
    try:
        res = driver.sync_to_tfs()
        click.secho("\n[+] Synchronization SUCCESSFUL!", fg="green", bold=True)
        click.echo(f"  Device Name:        {res.get('device_name')}")
        click.echo(f"  TFS Device UUID:    {res.get('device_uuid')}")
        click.echo(f"  Endpoints Synced:   {res.get('endpoints_count')}")
        click.echo(f"  Config Rules Set:   {res.get('config_rules_count')}")
        click.echo(f"  Target Topology:    {cfg.tfs_context} / {cfg.tfs_topology}\n")
    except Exception as e:
        click.secho(f"[!] Sync failed: {e}", fg="red")
        sys.exit(1)


@main.command()
@click.option("--ip", default=None, help="Ceragon device management IP.")
@click.option("--tfs-url", default=None, help="TeraFlowSDN base URL.")
@click.option("--interval", default=None, type=int, help="Sync interval in seconds.")
def daemon(ip, tfs_url, interval) -> None:
    """Start continuous synchronization service in the foreground."""
    cfg = AdapterConfig()
    if ip: cfg.device_ip = ip
    if tfs_url: cfg.tfs_url = tfs_url.rstrip("/")
    if interval: cfg.sync_interval_seconds = interval

    service = AdapterService(cfg)
    try:
        service.start()
    except KeyboardInterrupt:
        service.stop()


@main.command()
@click.option("--ip", default=None, help="Ceragon device management IP.")
@click.option("--tfs-url", default=None, help="TeraFlowSDN base URL.")
def status(ip, tfs_url) -> None:
    """Check status of physical Ceragon device and its representation in TFS."""
    cfg = AdapterConfig()
    if ip: cfg.device_ip = ip
    if tfs_url: cfg.tfs_url = tfs_url.rstrip("/")

    driver = TFSCeragonDriver(cfg)
    click.echo("[*] Querying Ceragon hardware and TFS registry...")
    try:
        state = driver.client.get_device_state()
        from ceragon_tfs_adapter.mapper import generate_tfs_uuid
        dev_uuid = generate_tfs_uuid(f"ceragon-{state.serial_number}")
    except Exception as e:
        click.secho(f"[!] Cannot read Ceragon device: {e}", fg="red")
        sys.exit(1)

    tfs_dev = driver.registrar.get_registered_device(dev_uuid) if dev_uuid else None

    click.echo("\n--- Ceragon Hardware Status ---")
    click.echo(f"Node:        {state.node_name} ({state.model})")
    click.echo(f"IP:          {state.management_ip}:{state.management_port}")
    click.echo(f"Operational: {'YES' if state.is_operational else 'NO'}")

    click.echo("\n--- TeraFlowSDN Status ---")
    if tfs_dev:
        click.secho(f"Registered:  YES (UUID: {dev_uuid})", fg="green")
        click.echo(f"TFS Name:    {tfs_dev.get('name')}")
        click.echo(f"TFS Status:  {tfs_dev.get('device_operational_status')}")
    else:
        click.secho("Registered:  NO (Run 'ceragon-tfs-adapter sync' to register)", fg="yellow")
    click.echo("")


@main.group()
def schemas() -> None:
    """Manage and inspect Ceragon YANG data schemas."""
    pass


@schemas.command("list")
def schemas_list() -> None:
    """List all bundled Ceragon YANG schemas."""
    from ceragon_tfs_adapter.schemas import list_schemas, SCHEMAS_DIR
    mods = list_schemas()
    click.secho(f"\n[*] Bundled Ceragon YANG Schemas ({len(mods)} modules in {SCHEMAS_DIR}):", fg="cyan", bold=True)
    for m in mods:
        prefix = "  [TG] " if "tg" in m else "  [STD]"
        click.echo(f"{prefix} {m}")
    click.echo("")


@schemas.command("show")
@click.argument("module_name")
def schemas_show(module_name: str) -> None:
    """Print the contents of a specific bundled YANG module."""
    from ceragon_tfs_adapter.schemas import get_schema_content
    content = get_schema_content(module_name)
    if not content:
        click.secho(f"[!] Schema '{module_name}' not found. Run 'schemas list' to see available modules.", fg="red")
        sys.exit(1)
    click.echo(content)


@schemas.command("export")
@click.option("--output-dir", "-o", default="./yang_schemas", help="Directory to export schemas into.")
def schemas_export(output_dir: str) -> None:
    """Export all bundled YANG schema files to a specified directory."""
    import shutil
    from pathlib import Path
    from ceragon_tfs_adapter.schemas import SCHEMAS_DIR, list_schemas
    
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    mods = list_schemas()
    for m in mods:
        src = SCHEMAS_DIR / f"{m}.yang"
        if src.exists():
            shutil.copy(src, out / f"{m}.yang")
    click.secho(f"[+] Successfully exported {len(mods)} YANG schemas to: {out}", fg="green", bold=True)


if __name__ == "__main__":
    main()


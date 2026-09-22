# Ceragon TeraFlowSDN (TFS) Device Adapter

A standalone, packable REST / RESTCONF adapter connecting Ceragon wireless transport devices (MultiHaul TG / Terragraph / EtherHaul / CeraOS IP-50) to ETSI TeraFlowSDN (TFS).

---

## Features

- **Automated RESTCONF Discovery**: Probes physical Ceragon hardware, auto-negotiating datastore paths (`/restconf/ds/ietf-datastores:candidate` or `/restconf/data`).
- **TeraFlowSDN Source-of-Truth Sync**: Registers hardware inventory, network interfaces (`eth1`), radio sectors (60GHz mmWave), frequencies, and operational statuses into TFS Context and Topology.
- **Bi-Directional Intent Execution**: Translates TFS configuration rules into Ceragon RESTCONF candidate mutations and commits.
- **Packable & Distributable**: Standard Python package with `pyproject.toml`, `setup.py`, and CLI command `ceragon-tfs-adapter`.

---

## Installation

### From Source (Editable Mode)
```bash
cd c:\CER_Intent\ceragon_tfs_adapter
pip install -e .
```

### Build Wheel (.whl)
```bash
cd c:\CER_Intent\ceragon_tfs_adapter
pip install build
python -m build
# Produces dist/ceragon_tfs_adapter-1.0.0-py3-none-any.whl
```

---

## CLI Usage

### 1. Discover Connected Hardware
```bash
ceragon-tfs-adapter discover --ip 192.168.1.225
```

### 2. Synchronize to TeraFlowSDN
```bash
ceragon-tfs-adapter sync --ip 192.168.1.225 --tfs-url http://localhost:8088
```

### 3. Run Continuous Daemon
```bash
ceragon-tfs-adapter daemon --interval 15
```

### 4. Check Status
```bash
ceragon-tfs-adapter status
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CERAGON_IP` | `192.168.1.225` | Ceragon device management IP |
| `CERAGON_PORT` | `80` | Ceragon management port |
| `CERAGON_USER` | `admin` | RESTCONF username |
| `CERAGON_PASSWORD` | `admin` | RESTCONF password |
| `TERAFLOW_URL` | `http://localhost:8088` | TeraFlowSDN NBI base URL |
| `TFS_CONTEXT` | `admin` | TFS Context name |
| `TFS_TOPOLOGY` | `admin` | TFS Topology name |
| `ADAPTER_SYNC_INTERVAL_SEC` | `15` | Periodic sync interval |

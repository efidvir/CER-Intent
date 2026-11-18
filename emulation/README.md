# Emulated radio hop and end-to-end demo

Runs ETSI's "programmable connectivity" chain without radio hardware:

```
OpenSlice / curl --RFC 9543--> CER-Intent --L3SM (RFC 8299)--> TeraFlowSDN
    --gNMI--> Arista cEOS routers           (as in TeraFlowSDN's eucnc24 test)
    --RESTCONF--> Ceragon driver --> radio emulators (bridge + tc on the air link)
```

| File | What it is |
| :--- | :--- |
| `radio_emulator.py` | MultiHaul TG RESTCONF emulator: candidate datastore, commit/discard, user bridges, radio tuning, active-link figures. Optional Linux bridge between two ports and a `tc` cap on the air port at the link speed. `POST /emulator/link` changes the link (fade). |
| `radio-emulator.Dockerfile` | Image for Containerlab (`cer-intent/radio-emulator:latest`). |
| `containerlab/ceragon-xhaul.clab.yml` | dc1 – r1 – r2 – radio-a ~ air ~ radio-b – r3 – dc2. Routers and sites follow TeraFlowSDN's eucnc24 test. |
| `containerlab/tfs-topology.json` | TeraFlowSDN descriptors: routers on the gNMI OpenConfig driver, radios on the Ceragon driver (`ceragon-wireless`), links in both directions. |
| `containerlab/slice-request.json` | The slice the demo orders (CER-Intent's compact RFC 9543 form; same sites and addresses as eucnc24's L3VPN). |
| `e2e_demo.py` | Onboards the topology, orders the slice from CER-Intent, waits for the TeraFlowSDN service, reads a radio's RFC 8561 view, optionally fades the air link, deletes the slice. `--dry-run` prints the requests. |

## Running it

```bash
docker build -f emulation/radio-emulator.Dockerfile -t cer-intent/radio-emulator:latest emulation
cd emulation/containerlab && sudo containerlab deploy -t ceragon-xhaul.clab.yml && cd -
# TeraFlowSDN deployed with the fork's feat/etsi-alignment branch (Ceragon driver + handler)
# CER-Intent running with TERAFLOW_URL pointing at it and TFS_REALIZATION=ietf
python emulation/e2e_demo.py --tfs http://<tfs> --cer-intent http://<cer-intent>:5000 --fade-mbps 400
```

## Status

The emulator is tested against the Ceragon RESTCONF client (`tests/test_radio_emulator.py`) and was driven by the TeraFlowSDN fork's native driver over HTTP (discovery, one commit per request, slice deletion, RFC 8561 view, capacity KPI). The Containerlab topology, the router configs and a full run against a live TeraFlowSDN have not been run yet: Containerlab and TeraFlowSDN need a Docker/Kubernetes host.

In this topology the radios sit between two routers, and TeraFlowSDN's L3VPN leaves the router-to-router links untagged, so the radios carry the service on their default bridge and only receive the ACM setting from CER-Intent. An L2VPN, or an L3VPN with an explicit `vlan_id`, makes the Ceragon handler add a VLAN bridge on each radio.

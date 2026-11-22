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

## End-to-end flow on a laptop: intent → twin → TeraFlowSDN → radios

`dashboard/intent-flow.html` follows one intent through every component, each running its own code, and lists every HTTP exchange between them with the standard it speaks (the "API underlay" panel):

| Stage | What runs | On the wire |
| :--- | :--- | :--- |
| 1 Operator intent | CER-Intent parses the text, validates it, the architect picks the transport-slice skill | Intent API `POST /api/v1/intent` |
| 2 Slice controller | RFC 9543 request, Mapper, Technology Selector, Realizer builds the L2SM / L3SM request (not sent yet) | TFS-API topology read |
| 3 Digital twin | the twin syncs from TeraFlowSDN, builds an NS-3.45 scenario from the synced topology, the radios' inventory, the services in TeraFlowSDN and the site plan (`flow/site_plan.json`), runs it before and after the slice under the design rain, and checks the slice's SLOs; a predicted breach holds the approval (409) | Twin API, RFC 8345, TFS-API |
| 4 Apply | approval → RFC 9543 hand-over to the slice controller → L2SM / L3SM to TeraFlowSDN → the fork's Ceragon handler composes the rules → its CeragonDriver stages them on each radio and commits | RFC 9543 (in-process), RFC 8466 / RFC 8299, TFS-API, RFC 8040 |
| 5 Read-back | TeraFlowSDN service state, each radio read back through its driver (`Cache-Control: no-cache`), datastore diff, twin re-sync, intent outcome | TFS-API, RFC 8040, Twin API |

| File | What it is |
| :--- | :--- |
| `flow_stack.py` | Starts the stack (`up`), or builds it in one process on the virtual network (`inprocess()`, `check`). One slice is in service before the demo: `backhaul-ran`, VLAN 100, 200 Mbps. |
| `tfs_standin.py` | TeraFlowSDN stand-in: the IETF L2VPN / L3VPN NBI, RFC 8345 and the TFS-API calls CER-Intent and the twin use, with the fork's Ceragon service handler (`ConfigRules.py`) and `CeragonDriver` driving the radios. Labelled as a stand-in on the dashboard; point `TERAFLOW_URL` at a real TeraFlowSDN to use it instead (its southbound side is then not visible). |
| `vnet.py` | In-process HTTP between the components, for the tests and the browser copy. |
| `flow/topology.json` | region-a – radio-1 ~ air ~ radio-2 – edge (MH-T261 radios on ports 8101 / 8102). |
| `flow/record_ns3.py`, `flow/ns3_recordings.json` | NS-3.45 runs recorded for places without an ns-3 build (the twin's `NS3_TWIN_MODE=replay`): the demo's intents in every order, and a grid of slice rates. |
| `browser/build_site.py` | Builds the in-browser copy: Pyodide and the whole stack in a static site that runs any intent live in the visitor's browser (serve the folder with any static web server). |
| `browser/record_session.py`, `browser/build_replay.py` | Record a session on the live stack (every example intent from every state the demo reaches), and build a page that replays it call for call, with each call's recorded timing: the hosted copy. |

```bash
# ns-3.45 with contrib/ceragon built (see the twin repository); without it the twin replays recorded runs
CERAGON_TWIN_BINARY=<ns-3.45>/build/scratch/ns3.45-ceragon-twin python emulation/flow_stack.py up
# open http://localhost:5000/intent-flow.html
```

The three example intents show the twin at work: a 500 Mbps L2 slice passes and is applied; an 800 Mbps one would lose traffic when rain brings the hop down to MCS7 (770 Mbps), so the twin holds it and nothing reaches TeraFlowSDN; a 50 Mbps routed slice fits next to the first and is applied as an L3VPN.

On MultiHaul TG radios the Ceragon driver configures a slice as a VLAN bridge, without a per-slice queue, and the ACM range as the link distance, so the twin leaves slice traffic in the radio's default DSCP classes.

## Dashboard without a controller

The dashboard's slice-controller view (`/slice-controller.html`) runs on a laptop: CER-Intent builds the L3SM/L2SM request without sending it, the planner checks paths over this testbed's topology, and the twin answers what-ifs on the same topology.

```bash
# twin (tfs-ns3-digital-twin repository)
TWIN_PORT=9100 TWIN_DESCRIPTORS=<cer-intent>/emulation/containerlab/tfs-topology.json python src/tfs_digital_twin_api.py
# CER-Intent
ADAPTER_BACKEND=simulated TFS_REALIZATION=dry-run \
CER_INTENT_TOPOLOGY_FILE=emulation/containerlab/tfs-topology.json TWIN_URL=http://localhost:9100 python run.py
# open http://localhost:5000/slice-controller.html
```

With `TERAFLOW_URL` set and `TFS_REALIZATION=ietf`, the same view sends the request and the chain shows TeraFlowSDN's answer.

## Status

The emulator is tested against the Ceragon RESTCONF client (`tests/test_radio_emulator.py`) and was driven by the TeraFlowSDN fork's native driver over HTTP (discovery, one commit per request, slice deletion, RFC 8561 view, capacity KPI). The Containerlab topology, the router configs and a full run against a live TeraFlowSDN have not been run yet: Containerlab and TeraFlowSDN need a Docker/Kubernetes host.

In this topology the radios sit between two routers, and TeraFlowSDN's L3VPN leaves the router-to-router links untagged, so the radios carry the service on their default bridge and only receive the ACM setting from CER-Intent. An L2VPN, or an L3VPN with an explicit `vlan_id`, makes the Ceragon handler add a VLAN bridge on each radio.

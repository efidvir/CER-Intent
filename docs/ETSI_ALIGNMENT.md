# CER-Intent and the ETSI stack: alignment work

Branch `feat/etsi-alignment` in three repositories. Nothing was merged to a main branch and nothing was sent to ETSI.

## Target picture

ETSI's "Programmable Connectivity (alternative approach)":

```
OpenSlice --RFC 9543--> Network Slice Controller --L3VPN / L2VPN--> TeraFlowSDN controller --> data plane
                         (Mapper -> Technology Selector -> Realizer)
```

CER-Intent now has a slice controller with the same three stages and the same interfaces on both sides. It can take the slice controller's place, or sit in front of TeraFlowSDN's own slice controller. Ceragon radios are reached through TeraFlowSDN's standard service and device layers, with no CER-Intent side channel.

| Link in the chain | Before | Now |
| :--- | :--- | :--- |
| OpenSlice → slice controller | CER-Intent had an RFC 9543 interface, but realization did not follow the standard path | Same interface; TMF633 catalogue item and order-to-RFC 9543 conversion (`integrations/openslice`) |
| Slice controller internals | One method with lab default endpoints | `nsc/mapper.py` → `nsc/technology_selector.py` → `nsc/realizer.py`, plus a twin-backed planner check and an optional selector skill |
| Slice controller → TeraFlowSDN | Device config through the TFS API; L2SM/L3SM built but never sent | L3SM (RFC 8299) or L2SM (RFC 8466) to TFS's interfaces, or RFC 9543 to a TFS slice controller (`TFS_REALIZATION`) |
| Radio decisions (ACM, tuning) | Written to devices directly | Sent as TFS service settings; the Ceragon service handler applies them by fixed rules |
| TeraFlowSDN → radio | Native driver returned fixed lab state; endpoints in a format TFS cannot onboard; no service handler for radios | Live discovery, TFS endpoint format, batched commits, capacity KPIs, RFC 8561 view; transport service handler for L2NM and L3NM |
| Topology | TFS API only | RFC 8345 (`ietf-network`) for the twin and CER-Intent's client |
| Agents and tools | — | MCP tools for CER-Intent (advise by default) and for the twin; twin answers labelled simulated |
| Deployment | Scripts | Dockerfiles, Helm charts, CI for CER-Intent and the twin; Containerlab topology with emulated radios |

## Changes by repository

### TeraFlowSDN fork (`efidvir/teraflowsdn`)

* `src/device/service/drivers/ceragon/`: the RESTCONF client and models are shared with CER-Intent's adapter (payloads checked on hardware). Endpoints in TFS's `/endpoints/endpoint[...]` form with KPI sample types; initial config values are JSON objects (the old list values broke onboarding). One request is one transaction (commit once, discard on any failure). Deletion removes service-owned slices and leaves radio settings. SubscribeState/GetState stream byte counters and link total/used capacity. `GetConfig('/microwave-radio-link')` gives an RFC 8561 view. No lab defaults; TLS verification on by default.
* `src/service/service/service_handlers/ceragon_transport/`: registered for L2NM and L3NM on `DEVICEDRIVER_CERAGON`. Tagged services get a VLAN bridge per radio; untagged ones (e.g. an L3VPN whose access VLAN ends at the routers) ride the default bridge; whitelisted radio/ACM settings from the service settings.
* `UPSTREAM_CHECKLIST.md`: what an upstream merge request would contain and what must happen first. The fork ignores `.github/`, so CI commands are listed there instead of a workflow.

### CER-Intent (`efidvir/cer-intent`)

* Slice controller stages, `TFS_REALIZATION` (`ietf` default, `nsc`, `tfs-api`, `dry-run`), `NSC_DEFAULT_TECHNOLOGY` (L3VPN). Requests without two complete SDPs are rejected (400).
* `device/tfs_client.py`: RFC 9543, L2VPN, L3VPN, RFC 8345 and service-settings calls.
* Intent pipeline: slice intents naming two endpoints go to the shared slice controller; verified by reading the TFS service back.
* Planner no longer computes a path between other nodes when the endpoints are outside the twin topology.
* `cer_intent/mcp/`: nine tools; `python -m cer_intent.mcp`; `CER_INTENT_MCP_MODE=act` to let tools change the network; `CER_INTENT_MCP_PROXY=1` to share the API's slice datastore.
* `integrations/openslice/`, `docs/etsi/TMF921_QUESTIONS.md`, `docs/etsi/OPENCAPIF.md`.
* `Dockerfile`, `deploy/helm/cer-intent`, `.github/workflows/ci.yml`.
* `emulation/`: radio emulator, Containerlab topology, TFS descriptors, end-to-end demo script.
* Dashboard view `dashboard/slice-controller.html` ("Slice Controller" in both dashboards): the chain, an RFC 9543 request form, the pipeline result stage by stage, the VPN request and service settings, the path over the topology, slices, MCP tools and a twin what-if labelled simulated. Backed by `GET /api/v1/etsi/status` and `POST /api/v1/etsi/what-if`.
* `CER_INTENT_TOPOLOGY_FILE`: without TeraFlowSDN the planner reads a TFS descriptor file (e.g. the testbed's) instead of the built-in reference topology.

### Digital twin (`efidvir/tfs-ns3-digital-twin`)

* `src/rfc8345_import.py` and `TWIN_TOPOLOGY_SOURCE=rfc8345` (falls back to the TFS API).
* The basis of a what-if names `descriptors` when the twin's topology came from its offline descriptor file.
* What-if answers carry `"insight": "simulated"` and their basis; `POST /what-if`, `GET /healthz`.
* `src/twin_mcp.py`: twin as MCP tools; shares the HTTP twin when `TWIN_URL` is set.
* `Dockerfile`, `deploy/helm/transport-twin`, `.github/workflows/ci.yml`.

## Tests

| Repository | Result |
| :--- | :--- |
| TeraFlowSDN fork | 23 driver tests (fake RESTCONF device: MultiHaul TG and CeraOS), 8 handler tests (fake task executor). Driver also run over HTTP against the radio emulator. |
| CER-Intent | 58 tests in `tests/` (slice controller, MCP, OpenSlice, emulator, demo, dashboard view) and 51 adapter tests; on Python 3.11 with the pinned requirements and on 3.13. |
| Twin | 35 tests (10 new), on Python 3.11 (MCP SDK 1.x) and 3.13 (SDK 2.x). |

The L2SM/L3SM/RFC 9543 payloads are checked against the fields TeraFlowSDN's interface code reads; they have not been posted to a running TeraFlowSDN.

## What remains

1. **Rebase the fork on upstream TeraFlowSDN.** labs.etsi.org was not reachable from this environment. After the rebase: re-check `DEVICEDRIVER_CERAGON = 22` against upstream's enum, and add CER-Intent's tools to upstream TFS's MCP server with `cer_intent.mcp.tools.register(server)`.
2. **ETSI upstream submission.** Not started. Needs the license-header decision (Ceragon files are BSD-3-Clause, TFS is Apache 2.0) and the checklist in the fork.
3. **YANG publication.** No Ceragon YANG is published. Decide whether the upstream package drops `schemas/` or keeps only IETF/IEEE modules.
4. **Lab end-to-end test.** Driver and handler on a real radio pair; the Containerlab topology with a live TeraFlowSDN (`emulation/e2e_demo.py`).
5. **NS-3 and Containerlab together (optional).** Drive the emulated air link (`/emulator/link`) from the twin's channel model instead of by hand.
6. **RFC 8561 view.** The bundled `ietf-microwave-radio-link` module is abridged; validate the view against the published RFC 8561 modules.
7. **OpenSlice.** Confirm the catalogue import, which component forwards orders, how status is reported back, and MCP; send the TMF921 questions if wanted.
8. **OpenCAPIF.** Publish the APIs and add a token check on the RFC 9543 interface.
9. **Lab literals in demo code.** About 70 lab-specific names and addresses remain in CER-Intent's dashboard, simulation and demo data (energy records, TVR defaults, simulation runner); the slice path no longer uses them.
10. **Smaller limits.** The slice datastore is in memory (one replica). Used capacity is per device, not per radio link. On MultiHaul TG the bridge ID is derived from the VLAN unless given. `tfs_upstream_contribution/` in CER-Intent is superseded by the fork's branch.

## Settings

| Variable | Where | Meaning |
| :--- | :--- | :--- |
| `TERAFLOW_URL`, `TFS_USERNAME`, `TFS_PASSWORD` | CER-Intent, twin | TeraFlowSDN NBI and credentials for its RESTCONF interfaces |
| `TFS_REALIZATION` | CER-Intent | `ietf` (L2SM/L3SM), `nsc` (RFC 9543 to a TFS slice controller), `tfs-api` (earlier behaviour), `dry-run` |
| `NSC_DEFAULT_TECHNOLOGY`, `NSC_DEFAULT_LATENCY_MS`, `NSC_DEFAULT_MTU` | CER-Intent | Defaults the realizer records when it uses them |
| `CER_INTENT_MCP_MODE`, `CER_INTENT_MCP_PROXY`, `CER_INTENT_URL` | CER-Intent MCP | `advise`/`act`; share the API's slice datastore |
| `CER_INTENT_TOPOLOGY_FILE` | CER-Intent | TFS descriptor file the planner reads when no TeraFlowSDN is configured |
| `TWIN_TOPOLOGY_SOURCE`, `TWIN_URL`, `TWIN_PORT`, `TWIN_DESCRIPTORS` | twin | `rfc8345`/`tfs-api`; shared twin for MCP; port; offline descriptors |
| `_connect/settings`: `scheme`, `verify_tls`, `timeout`, `model` | TFS device record | Ceragon driver connection |

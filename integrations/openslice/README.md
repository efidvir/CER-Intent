# CER-Intent in the ETSI OpenSlice → TeraFlowSDN chain

ETSI's "Programmable Connectivity (alternative approach)" chain is:

```
OpenSlice --RFC 9543--> Network Slice Controller --L3VPN / L2VPN--> TeraFlowSDN controller --> data plane
```

The slice controller box is filled by TeraFlowSDN's own slice controller (Mapper → Technology Selector → Realizer). CER-Intent's slice controller has the same three stages and the same interfaces on both sides, so it can take that box, or sit in front of it:

| Option | OpenSlice talks to | CER-Intent setting | What CER-Intent adds |
| :--- | :--- | :--- | :--- |
| A. CER-Intent is the slice controller | CER-Intent's RFC 9543 interface | `TFS_REALIZATION=ietf` (default) | Twin-checked path, technology choice with a reason, radio/ACM decisions as TFS service settings, free-text intents |
| B. CER-Intent in front of the TFS slice controller | CER-Intent's RFC 9543 interface | `TFS_REALIZATION=nsc` | Same mapping and checks; the RFC 9543 request is then handed to TeraFlowSDN's slice controller |

In both cases OpenSlice uses the RFC 9543 interface it already speaks. The address is:

```
http(s)://<cer-intent>/restconf/data/ietf-network-slice-service:network-slice-services
```

## Catalogue item

`cer-intent-transport-slice.tmf633.json` is a TMF633 service specification for OpenSlice's catalogue. A customer either fills `networkSliceService` with a full RFC 9543 request, or fills the flat fields (`endpointA`, `endpointB`, `endpointAddresses`, `vlanId`, `bandwidthMbps`, `maxLatencyMs`, `realizationTechnology`, `intentText`).

`cer_intent/integrations/openslice.py` turns an order's characteristics (TMF638 list or a plain dict) into the RFC 9543 request, so an OpenSlice controller or LCM rule can forward the order:

```python
from cer_intent.integrations.openslice import characteristics_to_rfc9543
body = characteristics_to_rfc9543(service["serviceCharacteristic"])
requests.post(slice_controller_url, json=body, auth=(user, password))
```

## To confirm with the OpenSlice team

These are assumptions until checked on a running OpenSlice; nothing has been sent to ETSI.

1. **Import format.** The JSON follows OpenSlice's TMF633 flavour (`valueType` names such as `LONGTEXT`, `ENUM`; values as `{"value", "alias"}`). Check it imports through the catalogue API or UI without edits.
2. **Which component forwards the order.** Whether OpenSlice's existing RFC 9543 path can be pointed at another slice controller by configuration, or whether a Generic OSL Controller (or an LCM rule calling the conversion above) is the intended way.
3. **Status back to OpenSlice.** How the realization result (`built` / `sent` / `failed`, technology and reason) should be reported into the service inventory (`realizationStatus` characteristic, service state, or notes).
4. **MCP.** Whether OpenSlice's MCP server can call CER-Intent's MCP tools (`python -m cer_intent.mcp`) or expects the reverse.
5. **TMF921.** See `docs/etsi/TMF921_QUESTIONS.md`.

# Exposing CER-Intent through OpenCAPIF

Note. Nothing here is implemented or registered yet.

ETSI OpenCAPIF implements 3GPP CAPIF (TS 23.222, TS 29.222): API providers publish their service APIs, and API invokers onboard, discover them and get access. OpenSlice already has a CAPIF invoker controller, so publishing CER-Intent's APIs in OpenCAPIF would let OpenSlice find the slice controller by discovery instead of static configuration.

## What CER-Intent would publish

| Service API | Interface | Notes |
| :--- | :--- | :--- |
| Network slice service (RFC 9543) | `/restconf/data/ietf-network-slice-service:network-slice-services` | The interface OpenSlice uses; HTTP basic or OAuth (see below). |
| Intents | `/api/v1/intent`, `/api/v1/intents` | Free-text and structured intents. |
| Twin what-if | twin service `/what-if`, `/api/v1/dti/*` | Answers are labelled simulated. |
| MCP tools | `/mcp` (streamable HTTP) | Not a REST API in the CAPIF sense; can be described as a service API with its URI so invokers can discover it. |

## Steps

1. **Register as API provider** with the OpenCAPIF register service and onboard the provider domain functions: APF (publishes), AEF (exposes the endpoints, i.e. the CER-Intent and twin services), AMF (management).
2. **Publish** one `ServiceAPIDescription` per API through the Publish Service API. Sketch for the slice interface:

```json
{
  "apiName": "cer-intent-network-slice-service",
  "description": "RFC 9543 network slices over Ceragon wireless transport, realized on TeraFlowSDN (L2SM/L3SM)",
  "aefProfiles": [{
    "aefId": "<AEF id from onboarding>",
    "versions": [{"apiVersion": "v1", "resources": [{
      "resourceName": "network-slice-services",
      "commType": "REQUEST_RESPONSE",
      "uri": "/restconf/data/ietf-network-slice-service:network-slice-services",
      "operations": ["GET", "POST", "PUT", "DELETE"]
    }]}],
    "protocol": "HTTP_1_1",
    "dataFormat": "JSON",
    "securityMethods": ["OAUTH"],
    "interfaceDescriptions": [{"fqdn": "cer-intent.example", "port": 443, "securityMethods": ["OAUTH"]}]
  }]
}
```

3. **Security.** CAPIF hands invokers OAuth tokens (or PKI credentials) for the AEF. CER-Intent's RFC 9543 interface has no token check today; adding a bearer-token check that validates CAPIF-issued tokens is the code change this needs.
4. **Invoker side.** Confirm with the OpenSlice team how its CAPIF invoker controller selects and calls a discovered API (see `TMF921_QUESTIONS.md` for the related questions).

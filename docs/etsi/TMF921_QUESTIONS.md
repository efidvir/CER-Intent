# Questions for the OpenSlice team: intents (TMF921)

Draft. Not sent. CER-Intent takes free-text and structured intents for the transport domain and realizes them through RFC 9543 and TeraFlowSDN. Before deciding how intents should reach CER-Intent from OpenSlice, we would like to understand OpenSlice's plans for TMF921 (Intent Management API).

## Support today

1. Does OpenSlice expose TMF921 today? If so, which version (v4 or v5) and which resources (`Intent`, `IntentReport`, `IntentSpecification`)?
2. Is the intent expression format fixed (e.g. JSON-LD with the TM Forum intent ontology), or can an intent specification declare its own expression schema?
3. Is TMF921 on the OpenSlice roadmap, and in which release?

## Handing an intent to a domain

4. Can OpenSlice route a TMF921 intent to a domain intent handler (CER-Intent for the wireless transport domain), and how is that handler registered: through a controller, a catalogue entry, or a CAPIF-published API?
5. Should a domain handler expose TMF921 itself, so that OpenSlice acts as the intent owner and CER-Intent as the intent handler?
6. Can an intent and a service order be linked (an intent that results in an RFC 9543 slice ordered through the catalogue)?

## Reports and lifecycle

7. How should a handler report fulfilment and compliance back (`IntentReport`, events, or service inventory updates)?
8. How are intent conflicts or rejections reported, and is there a place for the handler's reason (CER-Intent gives one for each technology choice and each rejected request)?
9. Are there expectations on intent states, e.g. alignment with 3GPP TS 28.312 states that CER-Intent already tracks?

## Practical

10. Is there a test OpenSlice instance with TMF921 that partners can use?
11. Would an MCP tool (CER-Intent's `submit_intent`) be an acceptable interim path while TMF921 is not available?

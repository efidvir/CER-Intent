# The intent manager

`cer_intent/imf/` turns what an operator says, in words, a form, TMF921, 3GPP TS 28.312
or an agent's MCP call, into one intent record; asks for what is missing; checks it
against rules, other intents, the radio physics and the digital twin; offers
alternatives when the network cannot do it as asked; applies it through the slice
controller and TeraFlowSDN once approved; and keeps watching what has to keep holding.

The intent studio (`dashboard/intent-studio.html`) is the operator's workspace for it.

## One record for every way of asking

An intent record holds expectations. Each expectation says what it applies to
(`object`), the values it asks for (`targets`), when and where they hold (`contexts`),
and how strict it is. That is the structure of TS 28.312 (`expectationObject`,
`expectationTargets`, `expectationContexts`) and of the TM Forum intent common model,
so both standards map onto it directly (`imf/standards.py`).

Every value records where it came from:

| source | meaning |
|---|---|
| stated | the operator said it |
| resolved | matched against the network: a name, a path, a value derived from what a slice has now |
| profile | from a service profile (gold, URLLC, voice, ...) |
| policy | an operator default: the site's access port, the next free VLAN, the report cadence |
| negotiated | an alternative the operator accepted |
| model | read by the language model and not by the rules; confirmed before it changes the network |
| answer | the operator's answer to a question |

## Kinds

| kind | example |
|---|---|
| deliver | Connect region-a and edge with 300 Mbps, at most 10 ms, gold |
| change | Double the backhaul tonight 20:00-23:00, then restore it |
| lifecycle | Suspend every slice except the backhaul |
| keep | Never let the backhaul drop below 150 Mbps; take it from best effort first |
| optimise | Save energy on the hop at night when traffic is below 100 Mbps, keep MCS4 |
| guard | No changes during business hours without approval |
| observe | Alert me when the radio link drops below MCS6 |
| explore | How much more can the hop carry in heavy rain? · What if radio-1 fails? |
| ask | What runs over radio-1? · Why is the backhaul degraded? |

Requests for device features the v1 pipeline already realizes (timing, MACsec, TSN,
beam steering, multiband, O-RAN fronthaul, interference, telemetry, protection) become
a change expectation that the v1 pipeline applies when the intent is approved.

## Pipeline

1. **Understand** (`reader.py`, `llm.py`). The rule reader always runs: clauses, kinds,
   quantities and units, times and windows, conditions, relative changes ("double it",
   "+100 Mbps", "50% more"), lists ("north 400 Mbps, south 300 Mbps"), scope. A language
   model, when configured, reads the same words into the same JSON schema; the readings are
   compared, the rules' values win where they disagree, and values only the model read are
   confirmed before they act.
2. **Match** (`network.py`, `match.py`). Names are matched to the network TeraFlowSDN and
   the slice controller report (exact, operator aliases, words, spelling), with the network's
   own names: nothing about a lab is built in. Profiles and the operator's policy fill
   defaults; relative requests become absolute values.
3. **Clarify** (`clarify.py`). Unknown or ambiguous names, missing values, vague words
   ("faster"), taken VLANs become questions with choices; answers are kept on the record and
   re-applied, so a later answer never loses an earlier one.
4. **Check** (`check.py`). Guard rules (freeze windows, approval, a network-wide modulation
   floor, headroom), conflicts with other intents (a keep objective a change would break,
   overlapping windows that overfill a hop), the analytic radio screen on every hop, and the
   twin's NS-3 pre-flight, which decides whenever it runs.
5. **Negotiate** (`negotiate.py`). When the network cannot do it as asked: the most that fits
   (found on the twin by bisection when the twin ran), the bandwidth that keeps the asked
   availability, the availability the hop gives, a floor the hop holds in rain, the twin's
   measured value for a missed latency or loss, a lower-priority slice that can give way
   (checked on the twin), best effort when it fits in clear sky.
6. **Approve and act** (`manager.py`, `actions.py`). Roles decide who approves; rules can
   require an approver. Actions go through the slice controller (RFC 9543, then L2SM / L3SM
   to TeraFlowSDN), in-place service updates, suspend/resume/remove, and automatic transmit
   power control for energy. A failure undoes what the intent did before it.
7. **Keep and report** (`manager.tick`). Windows start and end (and revert); keep objectives
   are assessed from the radios' current modulation, read back through TeraFlowSDN; a keep
   objective that says so suspends best-effort slices first; alerts fire; reports follow
   TS 28.312 (`IntentReport`) and TMF921.

## Radio arithmetic

`radio.py` mirrors the twin's radio model: the 60 GHz ACM table and link-adaptation
thresholds, payload at 0.4 × the carrier rate capped at the 1 GbE port, and about 1 dB of
link-adaptation margin (measured against the twin's NS-3 runs). Rain uses ITU-R P.838-3
coefficients; availability uses ITU-R P.530-18 §2.4.1 (distance factor at most 2.5,
`A0.01 = γ(R0.01)·d·r`, `A_p/A0.01 = C1·p^-(C2 + C3·log10 p)` for 0.001 % ≤ p ≤ 1 %). The
availability of a slice on a hop is the share of the year the hop holds the modulation the
total load (or the floor) needs. `R0.01` comes from the site plan (`r001_mmh`, default
42 mm/h).

A hop that falls short is shared in proportion to what each slice asks: the radios queue
every slice in one class, as the twin models them.

## Interfaces

| interface | paths |
|---|---|
| CER-Intent API v2 | `POST /api/v2/intents`, `GET /api/v2/intents[/<id>]`, `/answers`, `/alternatives/<n>/accept`, `/approve`, `/recheck`, `/suspend`, `/resume`, `/report`, `/audit`, `DELETE /api/v2/intents/<id>` |
| conversation | `POST /api/v2/converse {session, text}`: requests, answers, "option 2", "approve", "cancel", "make it 600 Mbps" |
| reading only | `POST /api/v2/read {text}` |
| TMF921 v5 | `/tmf-api/intentManagement/v5/intent[/<id>]` (POST, GET, PATCH, DELETE), `/intent/<id>/intentReport`, `/intentSpecification` |
| 3GPP TS 28.312 | `PUT/GET/DELETE /3gpp-intent/v1/IntentHandlingFunction=1/Intent=<id>`, `.../IntentReport`, `POST/GET /3gpp-intent/v1/intents` |
| MCP | `intent_converse`, `intent_submit`, `intent_get`, `intent_answer`, `intent_accept_alternative`, `intent_approve`, `intent_withdraw`, `intent_report`, `explore_network` |

TMF921 PATCH carries `lifecycleStatus` (active, suspended, terminated), `cerAnswers` and
`cerSelectedAlternative`. A 28.312 intent with `intentAdminState: ACTIVATED` is applied when
its check passes; `cerFeasibilityCheckOnly: true` stops at the check. Names CER-Intent adds
that the standards have no word for carry a `cer` prefix.

Who acts comes from the `X-User` and `X-Role` headers (viewer, operator, approver, admin),
trusted as sent: a deployment puts the API behind its identity provider and maps claims to
these roles. Every change is in the audit log (`imf_audit.jsonl` next to the store).

## Configuration

| variable | default | |
|---|---|---|
| `CER_IMF_STORE` | `data/imf_intents.json` | `:memory:` keeps intents in memory |
| `CER_IMF_LLM` | `none` | `gemini`, `anthropic`, `openai` (any OpenAI-compatible server), `recorded` |
| `CER_IMF_TWIN` | `1` | `0` checks with the analytic screen only |
| `CER_IMF_TICK_S` | `10` | how often windows, objectives and reports are looked at; `0` turns the loop off |
| `CER_IMF_POLICY` | `data/imf_policy.json` | VLAN pool, report cadence, approval roles, profiles |
| `CER_IMF_ALIASES` | `data/imf_aliases.json` | operator names: `{"headquarters": "region-a"}` |
| `CER_SITE_PLAN` | the flow's site plan | hop distances, `r001_mmh`, design rain |
| `CER_ACM_BASELINE_FLOOR` | unset | the floor radios go back to when no slice on them asks for one |
| `CER_INTENT_NODE_ALIASES` | unset | short names for the v1 parser (`{"ctu-96": "<device name>"}`) |

## What is realized and what is answered on the twin

* Slices, their bandwidth, latency, VLAN and technology: realized through TeraFlowSDN.
* Modulation floor: carried as the slice's ACM settings. A radio holds one floor: every slice
  on it that asked for one carries the highest asked; it drops back when that slice leaves.
  On 60 GHz radios the driver applies the link-distance profile; the floor itself is
  checked on the twin.
* Energy: automatic transmit power control through the slice's radio settings, for the
  window; with no slice on the hop to carry the settings, the saving is answered on the twin.
* Availability: computed (ITU-R), never measured; a few seconds of simulation cannot show it.
* Without an NS-3 binary the twin replays recorded runs; a recorded run for another load is
  shown but does not decide.

## Measuring the reader

`tests/corpus/intents.jsonl` holds about 400 requests and what each should read as
(`python tests/corpus/build_corpus.py` rebuilds it; `python -m cer_intent.imf.corpus
--show-failures` scores it). CI holds every field above its threshold
(`tests/test_imf_corpus.py`). The corpus was written alongside the reader: its scores show
the reader still reads what it read, not how it reads words it has not seen. Operators'
own requests, collected in the studio, are the next corpus.

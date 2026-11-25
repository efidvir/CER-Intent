# Deployment settings

Mounted read-only at `/etc/cer-intent` by `compose.yaml` (the Helm chart builds the same files
from its values). Copy an example, drop `.example` from its name, and edit it; git ignores the
copies, so site details and tokens stay out of the repository.

| File | Read by | What it holds |
|---|---|---|
| `imf_policy.json` | CER-Intent (`CER_IMF_POLICY`) | operator defaults and the auto-approval guardrails |
| `tokens.yaml` | CER-Intent (`CER_AUTH_TOKENS_FILE`, with `CER_AUTH=token`) | who may sign in, and with which role |
| `site_plan.json` | CER-Intent (`CER_SITE_PLAN`) and the twin (`TWIN_SITE_PLAN`) | hop distances, design rain |
| `imf_aliases.json` | CER-Intent (`CER_IMF_ALIASES`) | the names people use for sites and devices |

A missing file means the built-in defaults: auto-approval off, no tokens (with `CER_AUTH=token`
nothing can change state until there are some), 250 m hops in 60 mm/h design rain, no aliases.

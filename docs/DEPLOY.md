# Deploying CER-Intent

Three pieces run together: **CER-Intent** (the intent manager and its studio, the RFC 9543
slice controller, the dashboards, the MCP tools), the **transport digital twin** (NS-3.45 with
the Ceragon module, from [tfs-ns3-digital-twin](https://github.com/efidvir/tfs-ns3-digital-twin)),
and **TeraFlowSDN** with the Ceragon device driver and transport service handler (the
[fork](https://github.com/efidvir/teraflowsdn)), which reaches the radios.

```
  operator ──► CER-Intent :5000 ──► TeraFlowSDN NBI ──► Ceragon driver ──► radios
                    │  ▲
                    ▼  │ pre-flight on NS-3
               twin :9100 ──► TeraFlowSDN (topology, RFC 8345)
```

| where | how | for |
|---|---|---|
| any machine with Docker | `docker compose -f compose.demo.yaml up --build` | the whole flow emulated: radios, TeraFlowSDN stand-in, twin, CER-Intent |
| a host next to TeraFlowSDN | `docker compose up -d --build` | CER-Intent and the twin against your TeraFlowSDN |
| the TeraFlowSDN cluster | `deploy/microk8s/deploy.sh`, or the Helm charts | both as Kubernetes deployments beside TeraFlowSDN |
| Windows, no Docker | `deploy\windows\run-demo.ps1` | the emulated flow as local processes (the twin replays recorded runs) |

Every way starts with the sources of the other two repositories next to this one, at the refs
this version was tested with (`deploy/sources.env`):

```bash
deploy/get-sources.sh        # ../tfs-ns3-digital-twin and ../teraflowsdn (only its Ceragon parts)
```
```powershell
powershell -ExecutionPolicy Bypass -File deploy\get-sources.ps1
```

An existing checkout is used as it is; `--update` (`-Update`) moves it to the pinned ref.

## The emulated demo (Docker)

```bash
docker compose -f compose.demo.yaml up --build
```

Open `http://localhost:5000/intent-studio.html` and `http://localhost:5000/intent-flow.html`.
The first build compiles NS-3 inside the twin's image (about 15 minutes); later builds reuse it.
One slice is in service when it starts (`backhaul-ran`, VLAN 100, 200 Mbps).

Auto-approval is on in the demo (`CER_IMF_AUTO=1`): a small slice the twin passes is applied
at once and watched; a large one waits and says which guardrail stopped it. Start with
`CER_IMF_AUTO=0` to approve everything by hand. `docker compose -f compose.demo.yaml down -v`
resets it.

## Next to your TeraFlowSDN (Docker)

```bash
cp .env.example .env                 # set TERAFLOW_URL, and TFS_USERNAME / TFS_PASSWORD if needed
deploy/get-sources.sh
docker compose up -d --build
curl -s localhost:5000/readyz        # what it reaches: TeraFlowSDN, the twin
```

`TERAFLOW_URL` is the NBI as the containers reach it: inside a container `127.0.0.1` is the
container itself, so give the TeraFlowSDN host's address (or `host.docker.internal` on Docker
Desktop). The containers always use the `teraflow` adapter, whatever a `.env` written for
running natively says.

Settings files go in `deploy/config/` (mounted at `/etc/cer-intent`); copy an example and drop
`.example` from its name:

| file | what it holds |
|---|---|
| `imf_policy.json` | operator defaults and the auto-approval guardrails |
| `site_plan.json` | hop distances and design rain, read by CER-Intent and the twin |
| `tokens.yaml` | who may sign in, with which role (with `CER_AUTH=token`) |
| `imf_aliases.json` | the names people use for sites and devices |

The MCP tools for agents: `docker compose --profile mcp up -d` (port 8765).

Intents, audit records and an admin's auto-approval changes live in the `cer-data` volume:
`docker run --rm -v cer-intent_cer-data:/d -v "$PWD":/b alpine tar czf /b/cer-data.tgz -C /d .`
backs it up.

## On the TeraFlowSDN cluster (MicroK8s, Helm)

On the host that runs TeraFlowSDN's MicroK8s:

```bash
deploy/get-sources.sh
deploy/microk8s/deploy.sh
```

It builds both images, pushes them to MicroK8s' registry (`localhost:32000`, the one
TeraFlowSDN's own deploy uses), installs the `transport-twin` and `cer-intent` charts into the
`cer` namespace, points them at TeraFlowSDN's NBI service
(`http://nbiservice.tfs.svc.cluster.local:8080`), and waits for both to be ready. `NAMESPACE`,
`TFS_NAMESPACE`, `TFS_NBI_URL`, `VALUES` (a values file for CER-Intent) and `TWIN_VALUES` change
those; `SKIP_BUILD=1` only installs the charts.

With Helm directly, the parts of `deploy/helm/cer-intent/values.yaml` most deployments set:

```yaml
image: {repository: localhost:32000/cer-intent, tag: "0.2.0"}
teraflow: {url: http://nbiservice.tfs.svc.cluster.local:8080}
twin: {url: http://twin-transport-twin:9100}
intentManager:
  sitePlan: {design_rain_mmh: 60, links: {"radio-1|radio-2": {distance_m: 250}}}
autoApproval: {enabled: true, max_bandwidth_mbps: 200, watch_s: 600}
auth: {mode: token, tokensSecret: cer-tokens, sessionSecret: cer-session}
ingress: {enabled: true, className: nginx, host: cer-intent.lab.example}
```

```bash
kubectl -n cer create secret generic cer-tokens --from-file=tokens.yaml=deploy/config/tokens.yaml
kubectl -n cer create secret generic cer-session --from-literal=CER_SECRET_KEY="$(openssl rand -hex 32)"
```

Give the twin chart the same site plan (`twin.sitePlan`). The chart runs one replica with a
`Recreate` strategy: the intent records and the slice datastore have one writer, on a
`ReadWriteOnce` volume (`persistence.size`, default 1 Gi). Probes: `/healthz` (liveness),
`/readyz` (readiness; `readiness.require: "teraflow,twin"` makes it wait for them).

## Signing in

`CER_AUTH=headers` (the default) takes `X-User` / `X-Role` as sent; keep the service behind your
own access control, or an identity-aware proxy that sets those headers and drops any a client
sends. `CER_AUTH=token` gives each person or agent a token (`tokens.yaml`; prefer
`token_sha256`): API clients send `Authorization: Bearer <token>`, people sign in once at
`/login` and every dashboard uses the session cookie. Writing needs a token; reading stays open
unless `CER_AUTH_OPEN_READ=0`. Set `CER_SECRET_KEY` so sign-ins survive restarts, and
`CER_COOKIE_SECURE=1` behind HTTPS. The MCP tools send `CER_INTENT_TOKEN`.

Roles: a **viewer** reads, asks and files intents it cannot approve; an **operator** approves
within policy; an **approver** also approves what policy reserves for approvers, and rules; an
**admin** also changes the auto-approval settings.

## Auto-approval

Auto-approval starts switched off; `autoApproval.enabled` (Helm), `auto_approve.enabled` in
`imf_policy.json`, `CER_IMF_AUTO=1`, or an admin in the studio switches it on. A checked intent
is then applied at once when every guardrail holds: allowed kind and role, every value confirmed, the check and the twin's
NS-3 run passed, within the size and headroom limits, radios at their clear-sky rate now, inside
the window and the hourly rate, reversible. Each applied intent is watched for `watch_s` and
undone if it, or an intent met before it, stops being met. See
[the intent manager](INTENT_MANAGER.md#auto-approval-inside-guardrails).

## Images

| image | built from | |
|---|---|---|
| `cer-intent` | `Dockerfile` (target `app`, the default) | the service |
| `cer-intent-demo` | `Dockerfile --target demo --build-context fork=../teraflowsdn` | plus the emulated radios and TeraFlowSDN stand-in |
| `transport-twin` | the twin's `Dockerfile` | with NS-3.45 built in (`--target replay`: without, recorded runs only) |

CI (`.github/workflows/ci.yml`) runs the tests (with the end-to-end ones, the twin and the fork
checked out beside them), lints and renders the chart, starts the image in both sign-in modes,
and deploys the emulated demo with `compose.demo.yaml` to check that a small slice is applied
automatically on a real NS-3 run. Images are published to `ghcr.io/efidvir/` only from a
version tag (`git tag v0.2.0 && git push origin v0.2.0`) or a manual run with *publish* ticked.

## Configuration

Everything is optional; see `.env.example` and the [intent manager's table](INTENT_MANAGER.md#configuration).

| variable | default in the image | |
|---|---|---|
| `TERAFLOW_URL` | `http://teraflowsdn-nbi:80` | TeraFlowSDN NBI |
| `TWIN_URL` | `http://twin:9100` | the digital twin |
| `CER_IMF_POLICY`, `CER_SITE_PLAN`, `CER_IMF_ALIASES` | under `/app/data` | compose and Helm point them at `/etc/cer-intent` |
| `CER_IMF_AUTO` | `0` | auto-approval on with the policy's guardrails |
| `CER_AUTH`, `CER_AUTH_TOKENS_FILE` | `headers` | sign-in |
| `CER_READY_REQUIRE` | unset | dependencies `/readyz` waits for |
| `CER_IMF_LLM` + key | `none` | a language model's reading beside the rules' |
| `STATE_FILE`, `AUDIT_LOG_FILE`, `CER_IMF_STORE`, `CER_IMF_AUTO_STATE` | `/app/data/...` | runtime state, on the data volume |

## Troubleshooting

* `/readyz` shows `teraflow.ok: false`: the NBI URL as the container sees it is wrong, or
  TeraFlowSDN's NBI is down. The studio stays reachable to say so (readiness waits for
  TeraFlowSDN only when `CER_READY_REQUIRE` names it).
* Changes wait with "the twin did not run": the twin is unreachable, or runs without NS-3
  (replay); `GET <twin>/api/v1/dti/ceragon/engine` says which.
* Every change waits with "runs MCSx now": a radio on the path is below its clear-sky rate;
  it is applied when the hop recovers (`/recheck`), or by a person.
* `entrypoint: /app/data is not writable`: the volume belongs to another user; the image runs
  as uid 10001 (Helm sets `fsGroup: 10001`).

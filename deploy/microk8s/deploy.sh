#!/usr/bin/env bash
# Deploy CER-Intent and the digital twin on the MicroK8s cluster that runs TeraFlowSDN.
#
# Builds both images on this host, pushes them to MicroK8s' registry (localhost:32000, the one
# TeraFlowSDN's own deploy uses), and installs the two Helm charts into one namespace.
#
#   deploy/get-sources.sh                           ../tfs-ns3-digital-twin (the twin's image is built from it)
#   deploy/microk8s/deploy.sh                       namespace cer, TeraFlowSDN in namespace tfs
#
# Environment (all optional):
#   NAMESPACE=cer  TFS_NAMESPACE=tfs  TFS_NBI_URL=http://nbiservice.<TFS_NAMESPACE>.svc.cluster.local:8080
#   REGISTRY=localhost:32000  VERSION=<git describe>  TWIN_SRC=../tfs-ns3-digital-twin
#   VALUES=<extra values file for the cer-intent chart>   (auto-approval, sign-in, site plan, ...)
#   TWIN_VALUES=<extra values file for the transport-twin chart>
#   SKIP_BUILD=1     install charts only (the images are already in the registry)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
NAMESPACE="${NAMESPACE:-cer}"
TFS_NAMESPACE="${TFS_NAMESPACE:-tfs}"
TFS_NBI_URL="${TFS_NBI_URL:-http://nbiservice.${TFS_NAMESPACE}.svc.cluster.local:8080}"
REGISTRY="${REGISTRY:-localhost:32000}"
TWIN_SRC="${TWIN_SRC:-$(dirname "$root")/tfs-ns3-digital-twin}"
VERSION="${VERSION:-$(git -C "$root" describe --tags --always --dirty 2>/dev/null || echo 0.2.0)}"
KUBECTL="${KUBECTL:-microk8s kubectl}"
if [ -z "${HELM:-}" ]; then
  if microk8s helm version >/dev/null 2>&1; then HELM="microk8s helm"; else HELM="microk8s helm3"; fi
fi

say() { printf '\n== %s\n' "$*"; }

[ -d "$TWIN_SRC" ] || { echo "the twin is not at $TWIN_SRC: run deploy/get-sources.sh (or set TWIN_SRC)"; exit 1; }
if command -v microk8s >/dev/null; then
  microk8s status --wait-ready >/dev/null
  # dns for service names, the registry the images are pushed to, storage for the data volume
  for addon in dns registry hostpath-storage; do
    microk8s status --addon "$addon" 2>/dev/null | grep -q enabled || { echo "enabling MicroK8s addon $addon"; microk8s enable "$addon"; }
  done
elif [ "$KUBECTL" = "microk8s kubectl" ]; then
  echo "microk8s not found: set KUBECTL, HELM and REGISTRY to use another cluster"; exit 1
fi

if [ "${SKIP_BUILD:-0}" != 1 ]; then
  say "building cer-intent:$VERSION"
  docker build --build-arg VERSION="$VERSION" -t "$REGISTRY/cer-intent:$VERSION" "$root"
  say "building transport-twin:$VERSION (the first build compiles NS-3.45: ~15 min)"
  docker build -t "$REGISTRY/transport-twin:$VERSION" "$TWIN_SRC"
  say "pushing to $REGISTRY"
  docker push "$REGISTRY/cer-intent:$VERSION"
  docker push "$REGISTRY/transport-twin:$VERSION"
fi

say "namespace $NAMESPACE; TeraFlowSDN NBI $TFS_NBI_URL"
$KUBECTL get namespace "$NAMESPACE" >/dev/null 2>&1 || $KUBECTL create namespace "$NAMESPACE"

say "installing the twin"
twin_args=(--set image.repository="$REGISTRY/transport-twin" --set image.tag="$VERSION" --set teraflow.url="$TFS_NBI_URL")
[ -n "${TWIN_VALUES:-}" ] && twin_args+=(-f "$TWIN_VALUES")
$HELM upgrade --install twin "$TWIN_SRC/deploy/helm/transport-twin" -n "$NAMESPACE" "${twin_args[@]}"

say "installing CER-Intent"
cer_args=(--set image.repository="$REGISTRY/cer-intent" --set image.tag="$VERSION" --set teraflow.url="$TFS_NBI_URL"
          --set twin.url="http://twin-transport-twin:9100")
[ -n "${VALUES:-}" ] && cer_args+=(-f "$VALUES")
$HELM upgrade --install cer "$root/deploy/helm/cer-intent" -n "$NAMESPACE" "${cer_args[@]}"

say "waiting for the rollouts"
$KUBECTL -n "$NAMESPACE" rollout status deploy/twin-transport-twin --timeout=300s
$KUBECTL -n "$NAMESPACE" rollout status deploy/cer-cer-intent --timeout=300s
$KUBECTL -n "$NAMESPACE" exec deploy/cer-cer-intent -c api -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/readyz').read().decode())"

cat <<EOF

CER-Intent $VERSION is up in namespace $NAMESPACE.
  studio:  $KUBECTL -n $NAMESPACE port-forward --address 0.0.0.0 svc/cer-cer-intent 5000:5000
           then http://<this host>:5000/intent-studio.html   (or enable the chart's ingress)
EOF

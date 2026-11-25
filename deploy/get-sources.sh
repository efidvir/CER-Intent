#!/usr/bin/env bash
# Clone (or update) the twin and the TeraFlowSDN fork next to this repository, at the refs in
# deploy/sources.env. Only the fork's parts the demo uses are checked out (sparse).
#
#   deploy/get-sources.sh                  ../tfs-ns3-digital-twin and ../teraflowsdn
#   deploy/get-sources.sh <dir>            into <dir>/tfs-ns3-digital-twin and <dir>/teraflowsdn
#   deploy/get-sources.sh --update [dir]   also move existing checkouts to those refs (detached)
#
# An existing checkout is left as it is (your own working clone, say) unless --update is given.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
update=0
if [ "${1:-}" = "--update" ]; then update=1; shift; fi
dest="${1:-$(dirname "$root")}"
# shellcheck disable=SC1091
source "$here/sources.env"

fetch() {   # repo ref dir [sparse paths...]
  local repo="$1" ref="$2" dir="$3"; shift 3
  if [ -d "$dir/.git" ] && [ "$update" = 0 ]; then
    echo "using $dir as it is ($(git -C "$dir" rev-parse --abbrev-ref HEAD)); --update moves it to $ref"
  elif [ -d "$dir/.git" ]; then
    echo "updating $dir to $ref"
    git -C "$dir" fetch --depth 1 origin "$ref"
    git -C "$dir" checkout -q --detach FETCH_HEAD
  else
    echo "cloning $repo ($ref) into $dir"
    if [ "$#" -gt 0 ]; then
      git clone -q --depth 1 --filter=blob:none --sparse --branch "$ref" "$repo" "$dir"
      git -C "$dir" sparse-checkout set --no-cone "$@"
    else
      git clone -q --depth 1 --branch "$ref" "$repo" "$dir"
    fi
  fi
  echo "  $dir at $(git -C "$dir" rev-parse --short HEAD)"
}

fetch "$TWIN_REPO" "$TWIN_REF" "$dest/tfs-ns3-digital-twin"
fetch "$TFS_FORK_REPO" "$TFS_FORK_REF" "$dest/teraflowsdn" \
  /src/common/ /src/device/__init__.py /src/device/service/__init__.py /src/device/service/driver_api/ \
  /src/device/service/drivers/ceragon/ /src/service/__init__.py /src/service/service/__init__.py \
  /src/service/service/service_handlers/ceragon_transport/

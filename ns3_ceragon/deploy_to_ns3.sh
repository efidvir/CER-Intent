#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Install the Ceragon functional-twin module into an ns-3 (>= 3.45) tree.
#
#   ./deploy_to_ns3.sh /home/efid/ns3-dev            # copy + build
#   ./deploy_to_ns3.sh /home/efid/ns3-dev --tests    # also run the test suite
#
# What it does
#   1. copies contrib/ceragon into <ns3>/contrib/ceragon
#   2. installs scratch/ceragon-twin.cc (generic twin driver used by CER-Intent:
#      build/scratch/ns3.45-ceragon-twin-default)
#   3. builds (re-configures only if ns-3 was never configured)
#   4. optionally runs "test-runner --suite=ceragon" (requires --enable-tests)
#
# TMPDIR is redirected to $HOME/.ceragon_tmp because the compiler needs scratch
# space and /tmp may be full on shared servers.
# ---------------------------------------------------------------------------
set -euo pipefail
NS3=${1:?usage: deploy_to_ns3.sh <ns-3 dir> [--tests]}
RUN_TESTS=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
export TMPDIR=${TMPDIR_OVERRIDE:-$HOME/.ceragon_tmp}
mkdir -p "$TMPDIR"

echo "[ceragon] installing module into $NS3/contrib/ceragon"
rm -rf "$NS3/contrib/ceragon"
cp -r "$HERE/contrib/ceragon" "$NS3/contrib/ceragon"
find "$NS3/contrib/ceragon" -type f -exec sed -i 's/\r$//' {} +

echo "[ceragon] installing scratch/ceragon-twin.cc"
cp "$NS3/contrib/ceragon/examples/ceragon-twin-from-file.cc" "$NS3/scratch/ceragon-twin.cc"

cd "$NS3"
if [ ! -f cmake-cache/build.ninja ] && [ ! -f cmake-cache/Makefile ]; then
  ./ns3 configure -d default --enable-examples
fi
cmake --build cmake-cache --target ceragon scratch_ceragon-twin -j "$(nproc)"
echo "[ceragon] twin driver: $NS3/build/scratch/ns3.45-ceragon-twin-default"
./build/scratch/ns3.45-ceragon-twin-default --listPortfolio | head -c 300; echo

if [ "$RUN_TESTS" = "--tests" ]; then
  cmake --build cmake-cache --target test-runner -j "$(nproc)"
  ./ns3 run --no-build "test-runner --suite=ceragon --verbose"
fi

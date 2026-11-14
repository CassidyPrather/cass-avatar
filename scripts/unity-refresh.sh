#!/usr/bin/env bash
# Recompiles the open editor, but only once every package type-checks.
#
#   scripts/unity-refresh.sh
#
# A compile error in the live editor stops every tool that drives it, so when
# several people or agents are editing at once it is worth waiting a moment
# for the tree to be whole rather than refreshing into someone's half-saved
# file. Gives up after five minutes and says which package is broken.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

packages=(Assets Packages/net.wirenook.cass)
for package in modules/*/Packages/net.wirenook.*; do
    packages+=("$package")
done

for attempt in $(seq 1 20); do
    if output=$(python scripts/compile-check.py "${packages[@]}" 2>&1); then
        python scripts/unity-bridge.py --quiet-logs refresh --timeout 900
        exit $?
    fi
    sleep 15
done

echo "unity-refresh: the tree still does not compile:" >&2
echo "$output" | tail -15 >&2
exit 1

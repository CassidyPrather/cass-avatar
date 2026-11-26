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

# The packages this project compiles: its own, and the ones Packages/manifest.json
# takes from modules/. A module that is a Unity project of its own (the world,
# which needs the Worlds SDK) is not this editor's to compile.
packages=(Assets Packages/net.wirenook.cass)
for package in $(python -c 'import json, os.path; print(" ".join(os.path.normpath(os.path.join("Packages", path[5:])).replace(os.sep, "/") for path in json.load(open("Packages/manifest.json", encoding="utf-8"))["dependencies"].values() if path.startswith("file:")))'); do
    # Python ends the line the Windows way; a path must not carry that along.
    packages+=("${package%$'\r'}")
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

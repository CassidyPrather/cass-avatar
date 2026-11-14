#!/usr/bin/env bash
# Validates blender/cass.blend against the Spec contracts and exports its
# Export collection to Packages/net.wirenook.cass/BlenderExports/cass.fbx,
# then reads the FBX back to confirm nothing was lost. Fails (non-zero) on any
# validation error or round-trip difference. Extra arguments go to export.py.
# Set BLENDER to use a Blender that is not on PATH.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# --factory-startup keeps user preferences and add-ons out of the result;
# --python-exit-code turns a Python failure into a failing exit status.
exec "${BLENDER:-blender}" -b --factory-startup --python-exit-code 1 \
    --python blender/scripts/export.py -- --blend blender/cass.blend "$@"

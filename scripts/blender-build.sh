#!/usr/bin/env bash
# Builds the avatar model from blender/sources/ and the modelled parts into
# blender/cass.blend (and blender/cass-lite.blend with --level lite). Refuses
# to overwrite a .blend that is not untouched generator output unless --force
# is passed. Extra arguments go to build_cass.py.
# Set BLENDER to use a Blender that is not on PATH.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

exec "${BLENDER:-blender}" -b --factory-startup --python-exit-code 1 \
    --python blender/scripts/build_cass.py -- "$@"

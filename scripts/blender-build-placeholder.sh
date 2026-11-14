#!/usr/bin/env bash
# Regenerates the placeholder character into blender/cass.blend. Refuses to
# overwrite a .blend that is not untouched generator output (hand-modelled
# work) unless --force is passed. Extra arguments go to build_placeholder.py.
# Set BLENDER to use a Blender that is not on PATH.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

exec "${BLENDER:-blender}" -b --factory-startup --python-exit-code 1 \
    --python blender/scripts/build_placeholder.py -- "$@"

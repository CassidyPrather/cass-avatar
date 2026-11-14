#!/usr/bin/env bash
# The avatar's day-to-day commands, run against the open Unity editor.
#
#   scripts/cass.sh export            Blender -> BlenderExports/cass.fbx (validated)
#   scripts/cass.sh rebuild           regenerate materials, animators, menus and prefabs
#   scripts/cass.sh verify [slug]     build a variant as an upload would and check it
#   scripts/cass.sh report [slug]     the same build, as JSON in dist/build-report/
#   scripts/cass.sh sheets [slug]     contact sheets in dist/validation/<slug>/
#   scripts/cass.sh preview [slug]    what an upload would send to VRChat
#   scripts/cass.sh upload [slug]     build and upload (SDK panel open and signed in)
#   scripts/cass.sh all               export, rebuild, then verify every variant
#
# slug defaults to "cass"; variants are listed in Packages/net.wirenook.cass/Spec/variants.json.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

unity() {
    python scripts/unity-bridge.py --quiet-logs "$@"
}

variants() {
    python -c 'import json; print(" ".join(v["slug"] for v in json.load(open("Packages/net.wirenook.cass/Spec/variants.json", encoding="utf-8"))["variants"]))'
}

command=${1:-}
slug=${2:-cass}

case "$command" in
    export)
        scripts/blender-export.sh
        scripts/unity-refresh.sh
        ;;
    rebuild)
        scripts/unity-refresh.sh
        unity invoke Wirenook.Cass.Editor.CassBuild.Rebuild
        ;;
    verify)
        unity invoke Wirenook.Cass.Editor.CassChecks.Verify "$slug" | tee /dev/stderr | grep -qx "ok"
        ;;
    report)
        unity invoke Wirenook.Cass.Editor.CassBuild.TestBuild "$slug"
        ;;
    sheets)
        unity --timeout 1800 invoke Wirenook.Validation.Editor.ContactSheets.Render "$slug"
        ;;
    preview)
        unity invoke Wirenook.Cass.Editor.CassUpload.Preview "$slug"
        ;;
    upload)
        # Uploads take as long as the build plus the network; do not give up early.
        unity --timeout 3600 invoke Wirenook.Cass.Editor.CassUpload.Upload "$slug"
        ;;
    all)
        "$0" export
        "$0" rebuild
        for variant in $(variants); do
            "$0" verify "$variant"
        done
        ;;
    *)
        sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
        exit 2
        ;;
esac

#!/usr/bin/env bash
# The avatar's day-to-day commands, run against the open Unity editor.
#
#   scripts/cass.sh build             sources and modelled parts -> blender/cass.blend and cass-lite.blend
#   scripts/cass.sh export            Blender -> BlenderExports/cass.fbx and cass-lite.fbx (validated)
#   scripts/cass.sh rebuild           regenerate materials, animators, menus and prefabs
#   scripts/cass.sh verify [slug] [platform]   build a variant as an upload would and check it
#   scripts/cass.sh report [slug] [platform]   the same build, as JSON in dist/build-report/
#   scripts/cass.sh sheets [slug] [platform]   contact sheets in dist/validation/<slug>/
#   scripts/cass.sh preview [slug]    what an upload would send to VRChat
#   scripts/cass.sh platform [name]   show, or switch, the platform the editor builds for
#   scripts/cass.sh upload [slug]     build and upload for that platform (signed in through the SDK panel)
#   scripts/cass.sh live [slug]       what VRChat holds for an uploaded variant
#   scripts/cass.sh publish [slug]    send name, description, tags and visibility only
#   scripts/cass.sh bundle            inspect the bundle the SDK built last (what VRChat got)
#   scripts/cass.sh all               export, rebuild, then verify every variant on every platform
#
# slug defaults to "cass"; variants are listed in Packages/net.wirenook.cass/Spec/variants.json.
# platform is pc, android or ios. Given to verify, report or sheets, the build
# is made as that platform's would be without switching the editor to it.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

unity() {
    python scripts/unity-bridge.py --quiet-logs "$@"
}

variants() {
    python -c 'import json; print(" ".join(v["slug"] for v in json.load(open("Packages/net.wirenook.cass/Spec/variants.json", encoding="utf-8"))["variants"]))'
}

# Runs one editor command with builds pretending to be for a platform.
as_platform() {
    local platform=$1
    shift
    if [ -z "$platform" ]; then
        "$@"
        return
    fi
    unity invoke Wirenook.Assets.Editor.WirenookPlatform.Pretend "$platform" > /dev/null
    local status=0
    "$@" || status=$?
    unity invoke Wirenook.Assets.Editor.WirenookPlatform.Pretend "" > /dev/null
    return $status
}

verify() {
    unity invoke Wirenook.Cass.Editor.CassChecks.Verify "$1" | tee /dev/stderr | grep -qx "ok"
}

command=${1:-}
slug=${2:-cass}
platform=${3:-}

case "$command" in
    build)
        scripts/blender-build.sh --level full
        scripts/blender-build.sh --level lite
        ;;
    export)
        scripts/blender-export.sh --level full
        scripts/blender-export.sh --level lite
        scripts/unity-refresh.sh
        ;;
    rebuild)
        scripts/unity-refresh.sh
        unity invoke Wirenook.Cass.Editor.CassBuild.Rebuild
        ;;
    verify)
        as_platform "$platform" verify "$slug"
        ;;
    report)
        as_platform "$platform" unity invoke Wirenook.Cass.Editor.CassBuild.TestBuild "$slug"
        ;;
    sheets)
        as_platform "$platform" unity --timeout 1800 invoke Wirenook.Validation.Editor.ContactSheets.Render "$slug"
        ;;
    platform)
        if [ -z "${2:-}" ]; then
            unity invoke Wirenook.Assets.Editor.WirenookPlatform.Show
        else
            # Unity reimports every asset for the new target and reloads
            # scripts; the first switch to a target takes minutes.
            unity --timeout 3600 invoke Wirenook.Assets.Editor.WirenookPlatform.Switch "$2"
            scripts/unity-refresh.sh
            unity invoke Wirenook.Assets.Editor.WirenookPlatform.Show
        fi
        ;;
    preview)
        unity invoke Wirenook.Cass.Editor.CassUpload.Preview "$slug"
        ;;
    upload)
        # Uploads take as long as the build plus the network; do not give up early.
        unity --timeout 3600 invoke Wirenook.Cass.Editor.CassUpload.Upload "$slug"
        ;;
    live)
        unity invoke Wirenook.Cass.Editor.CassUpload.Live "$slug"
        ;;
    publish)
        unity invoke Wirenook.Cass.Editor.CassUpload.Publish "$slug"
        ;;
    bundle)
        unity invoke Wirenook.Validation.Editor.BundleProbe.InspectLatest
        ;;
    all)
        "$0" export
        "$0" rebuild
        for variant in $(variants); do
            for target in pc android ios; do
                "$0" verify "$variant" "$target"
            done
        done
        ;;
    *)
        sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
        exit 2
        ;;
esac

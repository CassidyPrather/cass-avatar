#!/usr/bin/env python3
"""Talks to the running Unity editor through Assets/DevTools/UnityBridge.

    scripts/unity-bridge.py ping
    scripts/unity-bridge.py refresh                 # reimport + recompile, report compile errors
    scripts/unity-bridge.py menu "VRChat SDK/Show Control Panel"
    scripts/unity-bridge.py invoke Namespace.Type.Method [string args...]

Exits 0 when the editor reports success, 1 when it reports an error, and 2
when it never answers (editor closed, or still busy importing).
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time
import uuid

ROOT = pathlib.Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
        cwd=pathlib.Path(__file__).resolve().parent,
    ).stdout.strip()
)
BRIDGE = ROOT / "Temp" / "UnityBridge"


def main():
    # Editor logs carry whatever characters the tools print (arrows, Japanese
    # blendshape names); a Windows console codepage must not turn those into
    # a crash here.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["ping", "refresh", "menu", "invoke"])
    parser.add_argument("method", nargs="?", default="")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for the editor")
    parser.add_argument("--quiet-logs", action="store_true", help="print only warnings and errors from the editor log")
    options = parser.parse_args()

    if options.command in ("menu", "invoke") and not options.method:
        parser.error(f"{options.command} needs a target")

    inbox = BRIDGE / "in"
    outbox = BRIDGE / "out"
    if not (BRIDGE / "alive").exists():
        print("unity-bridge: the editor is not running this project (no Temp/UnityBridge/alive)", file=sys.stderr)
        return 2

    # Sortable ids keep requests in the order they were made.
    request_id = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}"
    request = {"command": options.command, "method": options.method, "args": options.args}
    pending = inbox / f"{request_id}.tmp"
    pending.write_text(json.dumps(request), encoding="utf-8")
    pending.rename(inbox / f"{request_id}.json")

    answer = outbox / f"{request_id}.json"
    deadline = time.monotonic() + options.timeout
    while not answer.exists():
        if time.monotonic() > deadline:
            print(f"unity-bridge: no answer after {options.timeout:.0f}s", file=sys.stderr)
            return 2
        time.sleep(0.1)

    response = json.loads(answer.read_text(encoding="utf-8"))
    answer.unlink()

    for entry in response.get("logs", []):
        if options.quiet_logs and entry["type"] == "Log":
            continue
        print(f"[{entry['type']}] {entry['message']}")
    if response.get("result"):
        print(response["result"])
    if response.get("error"):
        print(response["error"], file=sys.stderr)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

"""Probe Nova's Accessibility Service transport without running navigation."""

from __future__ import annotations

import argparse
import json
import subprocess
import time

RECEIVER = "com.infoney.nova/.NovaClickReceiver"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("scroll", "click"))
    parser.add_argument("value", help="scroll direction or semantic click target")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    if args.action == "scroll":
        command = [
            "am", "broadcast", "-n", RECEIVER,
            "-a", "com.infoney.nova.SCROLL_WINDOW",
            "--es", "direction", args.value,
        ]
    else:
        command = [
            "am", "broadcast", "-n", RECEIVER,
            "-a", "com.infoney.nova.CLICK_ELEMENT",
            "--es", "target", args.value,
        ]

    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(0.5, args.timeout),
            check=False,
        )
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        payload = {
            "action": args.action,
            "value": args.value,
            "duration_ms": duration_ms,
            "transport_returncode": result.returncode,
            "output": output,
            "accepted": result.returncode == 0 and "result=1" in output,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        payload = {
            "action": args.action,
            "value": args.value,
            "duration_ms": duration_ms,
            "transport_returncode": -1,
            "output": str(exc),
            "accepted": False,
            "timed_out": True,
        }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())

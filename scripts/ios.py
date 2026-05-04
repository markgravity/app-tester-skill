#!/usr/bin/env python3
"""
ios.py — Unified iOS Simulator Automation

Single entry point for all common iOS automation operations.
Use instead of remembering which script handles which operation.

Usage:
    python scripts/ios.py tap --text "Login"
    python scripts/ios.py tap --id "submit_button"
    python scripts/ios.py tap --coord 200,400
    python scripts/ios.py swipe --from 195,700 --to 195,200
    python scripts/ios.py swipe --from 195,700 --to 195,200 --duration 1.0
    python scripts/ios.py screenshot
    python scripts/ios.py screenshot --output .tester/screenshots/ --size half
    python scripts/ios.py logs
    python scripts/ios.py logs --app com.myapp.App --duration 5s --errors-only

All commands accept --udid (auto-detects booted simulator if omitted).
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

# Add scripts dir to path for sibling imports (navigator.py lives alongside ios.py)
sys.path.insert(0, str(Path(__file__).parent))

from common import (
    capture_screenshot,
    resolve_udid,
)
from common.screenshot_utils import generate_screenshot_name
from navigator import Navigator


def cmd_tap(args) -> int:
    """Tap by accessibility ID, fuzzy text, or raw coordinates."""
    try:
        udid = resolve_udid(args.udid)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    nav = Navigator(udid=udid)

    if args.coord:
        parts = args.coord.split(",")
        if len(parts) != 2:
            print("Error: --coord requires x,y format (e.g. 200,400)")
            return 1
        x, y = int(parts[0].strip()), int(parts[1].strip())
        if nav.tap_at(x, y):
            print(f"Tapped at ({x}, {y})")
            return 0
        print(f"Failed to tap at ({x}, {y})")
        return 1

    success, message = nav.find_and_tap(
        text=args.text,
        identifier=args.id,
    )
    print(message)
    return 0 if success else 1


def cmd_swipe(args) -> int:
    """Swipe from one coordinate to another."""
    try:
        udid = resolve_udid(args.udid)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    def parse_coord(s: str, flag: str):
        parts = s.split(",")
        if len(parts) != 2:
            print(f"Error: {flag} requires x,y format (e.g. 195,700)")
            return None
        return int(parts[0].strip()), int(parts[1].strip())

    from_xy = parse_coord(args.from_coord, "--from")
    to_xy = parse_coord(args.to_coord, "--to")
    if from_xy is None or to_xy is None:
        return 1

    x1, y1 = from_xy
    x2, y2 = to_xy

    cmd = [
        "axe", "swipe",
        "--start-x", str(x1), "--start-y", str(y1),
        "--end-x", str(x2), "--end-y", str(y2),
        "--duration", str(args.duration),
        "--udid", udid,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"Swiped from ({x1}, {y1}) to ({x2}, {y2}) in {args.duration}s")
        return 0
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        print(f"Swipe failed: {stderr.strip() or 'non-zero exit'}")
        return 1


def cmd_screenshot(args) -> int:
    """Capture a screenshot and save to the output directory."""
    try:
        udid = resolve_udid(args.udid)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / generate_screenshot_name())

    try:
        result = capture_screenshot(udid, output_path=output_path, size=args.size)
        path = result.get("file_path", output_path)
        w, h = result.get("width", 0), result.get("height", 0)
        print(f"Screenshot saved: {path} ({w}x{h})")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1


def _parse_duration(duration_str: str) -> float | None:
    """Parse duration string like '10s', '30s', '1m' into seconds."""
    match = re.match(r"^(\d+(?:\.\d+)?)(s|m)?$", duration_str)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or "s"
    return value * 60 if unit == "m" else value


def cmd_logs(args) -> int:
    """Stream simulator logs for a fixed duration and print a summary."""
    try:
        udid = resolve_udid(args.udid)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    duration_secs = _parse_duration(args.duration)
    if duration_secs is None:
        print(f"Error: invalid duration '{args.duration}' — use e.g. 10s, 30s, 1m")
        return 1

    cmd = ["xcrun", "simctl", "spawn", udid, "log", "stream", "--style", "compact"]
    if args.app:
        predicate = f'subsystem CONTAINS "{args.app}" OR process CONTAINS "{args.app}"'
        cmd += ["--predicate", predicate]

    lines: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
        deadline = time.monotonic() + duration_secs

        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.rstrip()
            if not line or line in seen:
                continue
            if args.filter and args.filter.lower() not in line.lower():
                continue

            seen.add(line)
            lines.append(line)

            lower = line.lower()
            if any(k in lower for k in ("error", "fault", "crash")):
                errors.append(line)
            elif any(k in lower for k in ("warning", "warn")):
                warnings.append(line)

        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    except Exception as e:
        print(f"Error reading logs: {e}")
        return 1

    print(f"Logs: {len(lines)} lines, {len(errors)} errors, {len(warnings)} warnings")

    if args.errors_only:
        for line in errors[:20]:
            print(f"  [error] {line}")
        for line in warnings[:10]:
            print(f"  [warn]  {line}")
    else:
        for line in lines[:30]:
            print(f"  {line}")
        if len(lines) > 30:
            print(f"  ... and {len(lines) - 30} more lines")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified iOS simulator automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/ios.py tap --text "Login"
  python scripts/ios.py tap --id "submit_button"
  python scripts/ios.py tap --coord 200,400
  python scripts/ios.py swipe --from 195,700 --to 195,200
  python scripts/ios.py screenshot --size half
  python scripts/ios.py logs --app com.myapp.App --duration 5s --errors-only
        """,
    )
    parser.add_argument(
        "--udid", help="Device UDID (auto-detects booted simulator if omitted)"
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- tap ---
    tap = subparsers.add_parser("tap", help="Tap a UI element or coordinate")
    tap_group = tap.add_mutually_exclusive_group(required=True)
    tap_group.add_argument(
        "--id", dest="id", metavar="ACCESSIBILITY_ID",
        help="Tap by accessibility identifier (exact match)"
    )
    tap_group.add_argument(
        "--text", metavar="TEXT",
        help="Tap by label/value (fuzzy match)"
    )
    tap_group.add_argument(
        "--coord", metavar="X,Y",
        help="Tap at raw coordinates"
    )

    # --- swipe ---
    swipe = subparsers.add_parser("swipe", help="Perform a swipe gesture")
    swipe.add_argument(
        "--from", dest="from_coord", required=True, metavar="X,Y",
        help="Start coordinate (e.g. 195,700)"
    )
    swipe.add_argument(
        "--to", dest="to_coord", required=True, metavar="X,Y",
        help="End coordinate (e.g. 195,200)"
    )
    swipe.add_argument(
        "--duration", type=float, default=0.5, metavar="SECS",
        help="Swipe duration in seconds (default: 0.5)"
    )

    # --- screenshot ---
    ss = subparsers.add_parser("screenshot", help="Capture a screenshot")
    ss.add_argument(
        "--output", default=".tester/screenshots/", metavar="DIR",
        help="Output directory (default: .tester/screenshots/)"
    )
    ss.add_argument(
        "--size", default="half", choices=["full", "half", "quarter", "thumb"],
        help="Size preset (default: half)"
    )

    # --- logs ---
    logs = subparsers.add_parser("logs", help="Stream and summarize simulator logs")
    logs.add_argument(
        "--app", metavar="BUNDLE_ID",
        help="Filter by app bundle ID or process name"
    )
    logs.add_argument(
        "--duration", default="10s", metavar="DURATION",
        help="How long to capture (e.g. 10s, 30s, 1m — default: 10s)"
    )
    logs.add_argument(
        "--filter", metavar="TEXT",
        help="Only show lines containing this text"
    )
    logs.add_argument(
        "--errors-only", action="store_true",
        help="Only print error and warning lines in output"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return {
        "tap": cmd_tap,
        "swipe": cmd_swipe,
        "screenshot": cmd_screenshot,
        "logs": cmd_logs,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

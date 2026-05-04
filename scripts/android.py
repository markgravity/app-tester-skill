#!/usr/bin/env python3
"""
android.py — Unified Android Automation

Single entry point for all common Android automation via ADB.
Works with both native Android and Flutter apps.

Usage:
    python scripts/android.py tap --text "Sign in with Google"
    python scripts/android.py tap --id "submit_button"
    python scripts/android.py tap --coord 540,1200
    python scripts/android.py swipe --from 540,1400 --to 540,600
    python scripts/android.py screenshot
    python scripts/android.py screenshot --output .tester/screenshots/
    python scripts/android.py logs --duration 5s --filter "[Scoreboard]"
    python scripts/android.py describe-ui
    python scripts/android.py hot-reload --pid 12345

All commands accept --serial (auto-detects connected device if omitted).
"""

import argparse
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


# ── ADB helpers ──────────────────────────────────────────────────────────────

def resolve_serial(serial: str | None) -> str:
    """Return the target device serial, auto-detecting if not provided."""
    if serial:
        return serial
    result = subprocess.run(
        ["adb", "devices"], capture_output=True, text=True
    )
    lines = [l.strip() for l in result.stdout.splitlines() if "\tdevice" in l]
    if not lines:
        raise RuntimeError("No connected Android device/emulator found. Run 'adb devices'.")
    return lines[0].split("\t")[0]


def adb(serial: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, *args],
        capture_output=True, text=True,
    )


# ── UI tree helpers ───────────────────────────────────────────────────────────

def dump_ui(serial: str) -> ET.Element:
    """Dump UI hierarchy and return parsed XML root."""
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
    result = adb(serial, "shell", "cat", "/sdcard/ui.xml")
    return ET.fromstring(result.stdout)


def find_node(root: ET.Element, text: str | None = None, identifier: str | None = None):
    """Find first node matching text (content-desc or text) or resource-id."""
    for node in root.iter():
        attrs = node.attrib
        if identifier:
            res_id = attrs.get("resource-id", "").split("/")[-1]
            if identifier == res_id or identifier in attrs.get("resource-id", ""):
                return node
        if text:
            t = attrs.get("text", "").lower()
            d = attrs.get("content-desc", "").lower()
            if text.lower() in t or text.lower() in d:
                return node
    return None


def node_center(node: ET.Element) -> tuple[int, int] | None:
    """Return the center (x, y) of a node's bounds attribute."""
    bounds = node.attrib.get("bounds", "")
    m = re.findall(r"\d+", bounds)
    if len(m) != 4:
        return None
    x1, y1, x2, y2 = map(int, m)
    return (x1 + x2) // 2, (y1 + y2) // 2


def format_tree(root: ET.Element, depth: int = 0, max_depth: int = 8) -> list[str]:
    """Format UI tree as readable lines."""
    lines = []
    if depth > max_depth:
        return lines
    attrs = root.attrib
    text = attrs.get("text", "")
    desc = attrs.get("content-desc", "")
    res = attrs.get("resource-id", "").split("/")[-1]
    bounds = attrs.get("bounds", "")
    cls = attrs.get("class", "").split(".")[-1]
    clickable = attrs.get("clickable", "false") == "true"
    if text or desc or res:
        marker = "[tap]" if clickable else ""
        lines.append(f"{'  '*depth}{cls} {marker} text={repr(text)} desc={repr(desc[:60])} id={repr(res)} {bounds}")
    for child in root:
        lines.extend(format_tree(child, depth + 1, max_depth))
    return lines


# ── Screenshot utils ──────────────────────────────────────────────────────────

def generate_screenshot_name() -> str:
    from datetime import datetime
    return f"android_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"


def capture_screenshot(serial: str, output_path: str) -> str:
    """Capture a screenshot via ADB and save to output_path."""
    result = subprocess.run(
        ["adb", "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Screenshot failed: {result.stderr.decode()}")
    Path(output_path).write_bytes(result.stdout)
    return output_path


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_tap(args) -> int:
    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    if args.coord:
        parts = args.coord.split(",")
        if len(parts) != 2:
            print("Error: --coord requires x,y format")
            return 1
        x, y = int(parts[0].strip()), int(parts[1].strip())
        adb(serial, "shell", "input", "tap", str(x), str(y))
        print(f"Tapped at ({x}, {y})")
        return 0

    try:
        root = dump_ui(serial)
    except Exception as e:
        print(f"Error dumping UI: {e}")
        return 1

    node = find_node(root, text=args.text, identifier=args.id)
    if node is None:
        label = args.text or args.id
        print(f"Element not found: {repr(label)}")
        return 1

    center = node_center(node)
    if center is None:
        print("Found element but could not determine bounds")
        return 1

    x, y = center
    adb(serial, "shell", "input", "tap", str(x), str(y))
    label = args.text or args.id
    print(f"Tapped {repr(label)} at ({x}, {y})")
    return 0


def cmd_swipe(args) -> int:
    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    def parse_coord(s, flag):
        parts = s.split(",")
        if len(parts) != 2:
            print(f"Error: {flag} requires x,y format")
            return None
        return int(parts[0].strip()), int(parts[1].strip())

    from_xy = parse_coord(args.from_coord, "--from")
    to_xy = parse_coord(args.to_coord, "--to")
    if from_xy is None or to_xy is None:
        return 1

    x1, y1 = from_xy
    x2, y2 = to_xy
    duration_ms = int(args.duration * 1000)

    adb(serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))
    print(f"Swiped from ({x1},{y1}) to ({x2},{y2}) in {args.duration}s")
    return 0


def cmd_screenshot(args) -> int:
    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / generate_screenshot_name())

    try:
        path = capture_screenshot(serial, output_path)
        size = Path(path).stat().st_size
        print(f"Screenshot saved: {path} ({size} bytes)")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1


def cmd_describe_ui(args) -> int:
    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    try:
        root = dump_ui(serial)
    except Exception as e:
        print(f"Error dumping UI: {e}")
        return 1

    lines = format_tree(root)
    for line in lines:
        print(line)
    print(f"\n{len(lines)} elements")
    return 0


def _parse_duration(s: str) -> float | None:
    m = re.match(r"^(\d+(?:\.\d+)?)(s|m)?$", s)
    if not m:
        return None
    v = float(m.group(1))
    return v * 60 if m.group(2) == "m" else v


def cmd_logs(args) -> int:
    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    duration_secs = _parse_duration(args.duration)
    if duration_secs is None:
        print(f"Error: invalid duration '{args.duration}'")
        return 1

    # Clear existing logcat buffer
    subprocess.run(["adb", "-s", serial, "logcat", "-c"], capture_output=True)

    cmd = ["adb", "-s", serial, "logcat", "-v", "time"]
    if args.tag:
        cmd += [f"{args.tag}:V", "*:S"]

    lines: list[str] = []
    errors: list[str] = []

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    deadline = time.monotonic() + duration_secs

    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.rstrip()
            if not line:
                continue
            if args.filter and args.filter.lower() not in line.lower():
                continue
            lines.append(line)
            if " E " in line or "error" in line.lower() or "exception" in line.lower():
                errors.append(line)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"Logs: {len(lines)} lines, {len(errors)} errors")
    display = errors if args.errors_only else lines
    for line in display[:40]:
        print(f"  {line}")
    if len(display) > 40:
        print(f"  ... and {len(display) - 40} more lines")

    return 0


def cmd_hot_reload(args) -> int:
    """Send SIGUSR1 to the flutter run process for a hot reload."""
    import signal
    import os

    pid = args.pid
    if pid is None:
        # Try to find flutter process automatically
        result = subprocess.run(
            ["pgrep", "-f", "flutter run"],
            capture_output=True, text=True,
        )
        pids = [int(p) for p in result.stdout.split() if p.strip()]
        if not pids:
            print("Error: no 'flutter run' process found. Pass --pid explicitly.")
            return 1
        pid = pids[0]

    try:
        os.kill(pid, signal.SIGUSR1)
        print(f"Hot reload signal sent to flutter process {pid}")
        time.sleep(2)
        print("Hot reload complete")
        return 0
    except ProcessLookupError:
        print(f"Error: process {pid} not found")
        return 1
    except PermissionError:
        print(f"Error: permission denied to signal process {pid}")
        return 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Android automation via ADB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/android.py tap --text "Sign in with Google"
  python scripts/android.py tap --coord 540,1200
  python scripts/android.py swipe --from 540,1400 --to 540,600
  python scripts/android.py screenshot --output .tester/screenshots/
  python scripts/android.py logs --duration 10s --filter "[App]"
  python scripts/android.py describe-ui
  python scripts/android.py hot-reload --pid 12345
        """,
    )
    parser.add_argument("--serial", help="ADB device serial (auto-detects if omitted)")
    subparsers = parser.add_subparsers(dest="command")

    # tap
    tap = subparsers.add_parser("tap", help="Tap a UI element or coordinate")
    tap_group = tap.add_mutually_exclusive_group(required=True)
    tap_group.add_argument("--id", dest="id", metavar="RESOURCE_ID", help="Tap by resource-id (partial match)")
    tap_group.add_argument("--text", metavar="TEXT", help="Tap by text or content-desc (fuzzy)")
    tap_group.add_argument("--coord", metavar="X,Y", help="Tap at raw coordinates")

    # swipe
    swipe = subparsers.add_parser("swipe", help="Perform a swipe gesture")
    swipe.add_argument("--from", dest="from_coord", required=True, metavar="X,Y")
    swipe.add_argument("--to", dest="to_coord", required=True, metavar="X,Y")
    swipe.add_argument("--duration", type=float, default=0.5, metavar="SECS")

    # screenshot
    ss = subparsers.add_parser("screenshot", help="Capture a screenshot")
    ss.add_argument("--output", default=".tester/screenshots/", metavar="DIR")

    # describe-ui
    subparsers.add_parser("describe-ui", help="Dump and print the UI accessibility tree")

    # logs
    logs = subparsers.add_parser("logs", help="Stream logcat for a fixed duration")
    logs.add_argument("--duration", default="10s", metavar="DURATION", help="e.g. 10s, 30s, 1m")
    logs.add_argument("--filter", metavar="TEXT", help="Only show lines containing this text")
    logs.add_argument("--tag", metavar="TAG", help="Filter by logcat tag (e.g. 'flutter')")
    logs.add_argument("--errors-only", action="store_true")

    # hot-reload
    hr = subparsers.add_parser("hot-reload", help="Send hot-reload signal to running flutter process")
    hr.add_argument("--pid", type=int, metavar="PID", help="flutter run PID (auto-detected if omitted)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return {
        "tap": cmd_tap,
        "swipe": cmd_swipe,
        "screenshot": cmd_screenshot,
        "describe-ui": cmd_describe_ui,
        "logs": cmd_logs,
        "hot-reload": cmd_hot_reload,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

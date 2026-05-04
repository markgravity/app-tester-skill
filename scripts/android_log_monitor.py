#!/usr/bin/env python3
"""
android_log_monitor.py — Android Log Monitor

Streams adb logcat and filters for app-specific lines.
Equivalent to log_monitor.py for Android.

Usage:
    python scripts/android_log_monitor.py --duration 10s --filter "[Scoreboard]"
    python scripts/android_log_monitor.py --duration 30s --tag flutter
    python scripts/android_log_monitor.py --duration 5s --errors-only
"""

import argparse
import re
import subprocess
import sys
import time


def resolve_serial(serial: str | None) -> str:
    if serial:
        return serial
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = [l.strip() for l in result.stdout.splitlines() if "\tdevice" in l]
    if not lines:
        raise RuntimeError("No connected Android device/emulator found.")
    return lines[0].split("\t")[0]


def _parse_duration(s: str) -> float | None:
    m = re.match(r"^(\d+(?:\.\d+)?)(s|m)?$", s)
    if not m:
        return None
    v = float(m.group(1))
    return v * 60 if m.group(2) == "m" else v


def stream_logs(
    serial: str,
    duration_secs: float,
    filter_text: str | None = None,
    tag: str | None = None,
    errors_only: bool = False,
) -> list[str]:
    subprocess.run(["adb", "-s", serial, "logcat", "-c"], capture_output=True)

    cmd = ["adb", "-s", serial, "logcat", "-v", "time"]
    if tag:
        cmd += [f"{tag}:V", "*:S"]

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
            if filter_text and filter_text.lower() not in line.lower():
                continue
            lines.append(line)
            if " E " in line or "exception" in line.lower() or "fatal" in line.lower():
                errors.append(line)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    return errors if errors_only else lines


def main():
    parser = argparse.ArgumentParser(description="Stream Android logcat")
    parser.add_argument("--serial", help="ADB device serial")
    parser.add_argument("--duration", default="10s", help="Capture duration (e.g. 10s, 1m)")
    parser.add_argument("--filter", metavar="TEXT", help="Only show lines containing text")
    parser.add_argument("--tag", metavar="TAG", help="Filter by logcat tag")
    parser.add_argument("--errors-only", action="store_true", help="Only print error lines")
    parser.add_argument("--grep", metavar="PATTERN", help="Regex filter on output lines")
    args = parser.parse_args()

    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    duration = _parse_duration(args.duration)
    if duration is None:
        print(f"Error: invalid duration '{args.duration}'")
        sys.exit(1)

    print(f"Streaming logcat for {args.duration}...", flush=True)
    lines = stream_logs(serial, duration, args.filter, args.tag, args.errors_only)

    if args.grep:
        pattern = re.compile(args.grep, re.IGNORECASE)
        lines = [l for l in lines if pattern.search(l)]

    print(f"\nCaptured {len(lines)} matching lines:")
    for line in lines[:50]:
        print(f"  {line}")
    if len(lines) > 50:
        print(f"  ... and {len(lines) - 50} more")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
android_launcher.py — Android App Lifecycle Control

Manages Flutter app launch on Android via ADB.
Handles install, launch, terminate, and flutter run process management.

Usage:
    python scripts/android_launcher.py --launch dev.markg.scoreboard
    python scripts/android_launcher.py --install path/to/app.apk
    python scripts/android_launcher.py --terminate dev.markg.scoreboard
    python scripts/android_launcher.py --flutter-run --project-dir ./flutter --device emulator-5554
    python scripts/android_launcher.py --find-pid   # find running flutter process PID
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ADB = "adb"
FLUTTER = os.path.expanduser("~/fvm/versions/stable/bin/flutter")


def resolve_serial(serial: str | None) -> str:
    if serial:
        return serial
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    lines = [l.strip() for l in result.stdout.splitlines() if "\tdevice" in l]
    if not lines:
        raise RuntimeError("No connected Android device/emulator found.")
    return lines[0].split("\t")[0]


def launch(serial: str, package: str, activity: str | None = None) -> bool:
    """Launch an app by package name."""
    if activity:
        component = f"{package}/{activity}"
    else:
        # Resolve main activity
        result = subprocess.run(
            [ADB, "-s", serial, "shell", "monkey", "-p", package, "-c",
             "android.intent.category.LAUNCHER", "1"],
            capture_output=True, text=True,
        )
        return result.returncode == 0

    result = subprocess.run(
        [ADB, "-s", serial, "shell", "am", "start", "-n", component],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def terminate(serial: str, package: str) -> bool:
    result = subprocess.run(
        [ADB, "-s", serial, "shell", "am", "force-stop", package],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def install(serial: str, apk_path: str) -> bool:
    result = subprocess.run(
        [ADB, "-s", serial, "install", "-r", apk_path],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def is_running(serial: str, package: str) -> bool:
    result = subprocess.run(
        [ADB, "-s", serial, "shell", "pidof", package],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def find_flutter_pid() -> int | None:
    """Find the PID of a running 'flutter run' process."""
    result = subprocess.run(["pgrep", "-f", "flutter run"], capture_output=True, text=True)
    pids = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    return int(pids[0]) if pids else None


def flutter_run(project_dir: str, device: str, log_file: str = "/tmp/flutter_android.log") -> int:
    """
    Start 'flutter run' in the background and return the PID.
    Logs are written to log_file.
    """
    flutter_bin = Path(FLUTTER)
    if not flutter_bin.exists():
        flutter_bin = Path(subprocess.run(
            ["which", "flutter"], capture_output=True, text=True
        ).stdout.strip())

    cmd = [str(flutter_bin), "run", "-d", device]
    log_fd = open(log_file, "w")

    proc = subprocess.Popen(
        cmd,
        cwd=project_dir,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"Started flutter run (PID {proc.pid}), logging to {log_file}")
    print("Waiting for app to be ready...")

    # Poll the log for readiness signal
    deadline = time.monotonic() + 120
    ready_markers = ["Syncing files to device", "Flutter run key commands", "is available at"]
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            content = Path(log_file).read_text()
            for marker in ready_markers:
                if marker in content:
                    print(f"App ready — detected: {repr(marker)}")
                    return proc.pid
        except OSError:
            pass

    print("Warning: timed out waiting for app ready signal. PID:", proc.pid)
    return proc.pid


def main():
    parser = argparse.ArgumentParser(description="Android/Flutter app lifecycle control")
    parser.add_argument("--serial", help="ADB device serial (auto-detects if omitted)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--launch", metavar="PACKAGE", help="Launch app by package name")
    group.add_argument("--terminate", metavar="PACKAGE", help="Force-stop app by package name")
    group.add_argument("--install", metavar="APK", help="Install APK")
    group.add_argument("--running", metavar="PACKAGE", help="Check if app is running")
    group.add_argument("--flutter-run", action="store_true", help="Start flutter run in background")
    group.add_argument("--find-pid", action="store_true", help="Find PID of running flutter run process")

    parser.add_argument("--project-dir", default=".", help="Flutter project directory (for --flutter-run)")
    parser.add_argument("--device", help="Flutter device ID (for --flutter-run)")
    parser.add_argument("--log-file", default="/tmp/flutter_android.log", help="Log file path")
    parser.add_argument("--activity", help="Android activity component (for --launch)")

    args = parser.parse_args()

    if args.find_pid:
        pid = find_flutter_pid()
        if pid:
            print(f"flutter run PID: {pid}")
        else:
            print("No flutter run process found")
            sys.exit(1)
        return

    if args.flutter_run:
        if not args.device:
            print("Error: --device required for --flutter-run")
            sys.exit(1)
        pid = flutter_run(args.project_dir, args.device, args.log_file)
        print(f"flutter run PID: {pid}")
        return

    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.launch:
        if launch(serial, args.launch, args.activity):
            print(f"Launched {args.launch}")
        else:
            print(f"Failed to launch {args.launch}")
            sys.exit(1)

    elif args.terminate:
        if terminate(serial, args.terminate):
            print(f"Terminated {args.terminate}")
        else:
            print(f"Failed to terminate {args.terminate}")
            sys.exit(1)

    elif args.install:
        if install(serial, args.install):
            print(f"Installed {args.install}")
        else:
            print(f"Failed to install {args.install}")
            sys.exit(1)

    elif args.running:
        state = "running" if is_running(serial, args.running) else "not running"
        print(f"{args.running}: {state}")


if __name__ == "__main__":
    main()

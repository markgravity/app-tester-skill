#!/usr/bin/env python3
"""
macOS App Launcher - App Lifecycle Control

Launches, terminates, and checks state of macOS apps.
Uses `open` for launch, `osascript quit` for graceful exit, `pkill` as fallback.

Usage:
    python3 scripts/macos_launcher.py --launch /path/to/App.app
    python3 scripts/macos_launcher.py --launch /path/to/App.app --capture-stdout /tmp/logs.txt
    python3 scripts/macos_launcher.py --terminate Messenger
    python3 scripts/macos_launcher.py --running Messenger
    python3 scripts/macos_launcher.py --find Messenger   # finds built .app in DerivedData

Log capture note:
    Swift print() goes to stdout, not the unified logging system.
    Use --capture-stdout to redirect stdout to a file when the app uses print().
    For apps using os_log/Logger, use macos_log_monitor.py instead.
"""

import argparse
import glob
import os
import subprocess
import sys
import time


def launch(app_path: str, wait_secs: float = 2.0) -> tuple[bool, str]:
    """Launch a macOS .app bundle via `open` and wait for it to appear."""
    result = subprocess.run(["open", app_path], capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"Failed: {result.stderr.strip()}"
    time.sleep(wait_secs)
    return True, f"Launched: {app_path}"


def launch_capture_stdout(app_path: str, log_file: str, wait_secs: float = 2.0) -> tuple[bool, str]:
    """Launch the app binary directly so stdout (print() output) is captured to log_file.

    Required when the app logs via Swift print() rather than os_log/Logger,
    because `open` discards stdout and `log stream` only sees unified logging.
    Uses stdbuf -oL to force line-buffered output so lines appear immediately.
    """
    binary = os.path.join(app_path, "Contents", "MacOS",
                          os.path.splitext(os.path.basename(app_path))[0])
    if not os.path.isfile(binary):
        return False, f"Binary not found: {binary}"
    with open(log_file, "w") as fout:
        subprocess.Popen(["stdbuf", "-oL", binary], stdout=fout, stderr=fout)
    time.sleep(wait_secs)
    return True, f"Launched (stdout → {log_file}): {binary}"


def terminate(app_name: str) -> tuple[bool, str]:
    """Terminate a running macOS app — graceful quit first, then pkill."""
    script = f'tell application "{app_name}" to quit'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return True, f"Quit: {app_name}"

    result = subprocess.run(["pkill", "-f", app_name], capture_output=True, text=True)
    if result.returncode == 0:
        return True, f"Killed: {app_name}"

    return False, f"Could not terminate: {app_name}"


def is_running(app_name: str) -> bool:
    """Return True if any process matching app_name is running."""
    result = subprocess.run(["pgrep", "-x", app_name], capture_output=True, text=True)
    if result.returncode == 0:
        return True
    # Fallback: broader match
    result = subprocess.run(["pgrep", "-f", app_name], capture_output=True, text=True)
    return result.returncode == 0


def find_app_path(scheme: str) -> str | None:
    """Find the most recently built .app bundle for an Xcode scheme in DerivedData."""
    derived_data = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
    pattern = f"{derived_data}/**/Build/Products/**/{scheme}.app"
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return max(matches, key=os.path.getmtime)
    return None


def main():
    parser = argparse.ArgumentParser(description="Control macOS app lifecycle")
    parser.add_argument("--launch", metavar="APP_PATH", help="Launch .app bundle path")
    parser.add_argument("--capture-stdout", metavar="LOG_FILE",
                        help="Launch binary directly and capture stdout to file (for print()-based apps)")
    parser.add_argument("--terminate", metavar="APP_NAME", help="Terminate app by process name")
    parser.add_argument("--running", metavar="APP_NAME", help="Check if app is running (exit 0=yes, 1=no)")
    parser.add_argument("--find", metavar="SCHEME", help="Find built .app for Xcode scheme")
    parser.add_argument("--wait", type=float, default=2.0, help="Seconds to wait after launch (default: 2)")
    args = parser.parse_args()

    if args.launch:
        if args.capture_stdout:
            ok, msg = launch_capture_stdout(args.launch, args.capture_stdout, wait_secs=args.wait)
        else:
            ok, msg = launch(args.launch, wait_secs=args.wait)
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.terminate:
        ok, msg = terminate(args.terminate)
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.running:
        running = is_running(args.running)
        print(f"{args.running}: {'running' if running else 'not running'}")
        sys.exit(0 if running else 1)

    elif args.find:
        path = find_app_path(args.find)
        if path:
            print(path)
        else:
            print(f"No built .app found for scheme: {args.find}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

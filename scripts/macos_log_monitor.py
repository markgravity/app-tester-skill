#!/usr/bin/env python3
"""
macOS Log Monitor - Unified Logging System Wrapper

Captures logs from a running macOS app using `log stream` (unified logging).
Filters by process name, supports duration-limited capture and grep patterns.

No external dependencies — uses built-in `log` command.

Usage:
    # Follow logs in real-time
    python scripts/macos_log_monitor.py --app Messenger --follow

    # Capture for 5 seconds then print matching lines
    python scripts/macos_log_monitor.py --app Messenger --duration 5s --grep "\\[Messenger\\]"

    # Background capture: start, do stuff, stop
    python scripts/macos_log_monitor.py --app Messenger --duration 10s > /tmp/mac_logs.txt &
    # ... perform UI actions ...
    grep "\\[Messenger\\]" /tmp/mac_logs.txt
"""

import argparse
import re
import signal
import subprocess
import sys
from datetime import datetime


def parse_duration(s: str) -> float:
    m = re.match(r"(\d+)([smh])", s.lower())
    if not m:
        raise ValueError(f"Invalid duration '{s}'. Use e.g. 5s, 2m, 1h")
    v, u = int(m.group(1)), m.group(2)
    return v * {"s": 1, "m": 60, "h": 3600}[u]


class MacOSLogMonitor:
    def __init__(self, app_name: str | None = None, predicate: str | None = None):
        self.app_name = app_name
        self.predicate = predicate or self._default_predicate()
        self.lines: list[str] = []
        self._proc: subprocess.Popen | None = None
        self._interrupted = False

    def _default_predicate(self) -> str:
        if self.app_name:
            return f'process == "{self.app_name}"'
        return "eventMessage != \"\""

    def stream(self, duration: float | None = None, follow: bool = False) -> bool:
        cmd = [
            "log", "stream",
            "--level", "debug",
            "--style", "compact",
            "--predicate", self.predicate,
        ]

        def _sigint(sig, frame):
            self._interrupted = True
            if self._proc:
                self._proc.terminate()

        signal.signal(signal.SIGINT, _sigint)

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1
            )
            start = datetime.now()

            for line in iter(self._proc.stdout.readline, ""):
                if not line:
                    break
                line = line.rstrip()
                self.lines.append(line)

                if follow:
                    print(line, flush=True)

                if duration and (datetime.now() - start).total_seconds() >= duration:
                    break
                if self._interrupted:
                    break

            self._proc.wait()
            return True

        except Exception as e:
            print(f"Error starting log stream: {e}", file=sys.stderr)
            return False
        finally:
            if self._proc:
                self._proc.terminate()

    def grep(self, pattern: str) -> list[str]:
        rx = re.compile(pattern)
        return [l for l in self.lines if rx.search(l)]

    def summary(self) -> str:
        return (
            f"Captured {len(self.lines)} lines "
            f"(predicate: {self.predicate})"
        )


def main():
    parser = argparse.ArgumentParser(description="Stream macOS app logs via unified logging")
    parser.add_argument("--app", help="App process name (e.g., Messenger)")
    parser.add_argument("--predicate", help="Custom log predicate (overrides --app)")
    parser.add_argument("--follow", action="store_true", help="Stream continuously until Ctrl-C")
    parser.add_argument("--duration", help="Capture duration then exit (e.g., 5s, 2m)")
    parser.add_argument("--grep", help="Filter output by regex pattern after capture")
    args = parser.parse_args()

    if not args.app and not args.predicate:
        print("Specify --app <AppName> or --predicate <predicate>", file=sys.stderr)
        sys.exit(1)

    monitor = MacOSLogMonitor(app_name=args.app, predicate=args.predicate)
    duration = parse_duration(args.duration) if args.duration else None

    print(f"[log stream] predicate: {monitor.predicate}", file=sys.stderr)

    monitor.stream(duration=duration, follow=args.follow or not duration)

    if args.grep and not args.follow:
        matches = monitor.grep(args.grep)
        for line in matches:
            print(line)
        print(f"\n{len(matches)} matching lines", file=sys.stderr)
    elif not args.follow:
        for line in monitor.lines[-100:]:
            print(line)
        print(monitor.summary(), file=sys.stderr)


if __name__ == "__main__":
    main()

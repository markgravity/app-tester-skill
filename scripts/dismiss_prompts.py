#!/usr/bin/env python3
"""Dismiss any visible iOS system Alert using an ordered label policy."""
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Dismiss iOS system prompts/alerts")
    parser.add_argument(
        "--policy",
        default="Don't Allow,Ask App Not to Track,Not Now,Dismiss,OK,Allow",
        help="Comma-separated list of button labels to try, in priority order",
    )
    parser.add_argument(
        "--udid",
        default=None,
        help="Device UDID (auto-detects booted simulator if not provided)",
    )
    args = parser.parse_args()

    labels = [l.strip() for l in args.policy.split(",") if l.strip()]

    # Check if any Alert is present
    base = ["python", "navigator.py", "--find-type", "Alert"]
    if args.udid:
        base += ["--udid", args.udid]

    result = subprocess.run(base, capture_output=True, text=True, cwd=__file__.rsplit("/", 1)[0])
    if result.returncode != 0:
        sys.exit(0)  # No alert present

    # Try each label in policy order
    for label in labels:
        tap_cmd = ["python", "navigator.py", "--find-text", label, "--tap"]
        if args.udid:
            tap_cmd += ["--udid", args.udid]

        r = subprocess.run(tap_cmd, capture_output=True, text=True, cwd=__file__.rsplit("/", 1)[0])
        if r.returncode == 0:
            print(f"Dismissed: tapped '{label}'")
            sys.exit(0)

    print("Alert present but no policy label matched")
    sys.exit(1)


if __name__ == "__main__":
    main()

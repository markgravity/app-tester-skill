#!/usr/bin/env python3
"""
macOS Screen Mapper - UI Element Analyzer via System Events

Reads the accessibility tree of a running macOS app using osascript/System Events.
Reports toolbar items, buttons, text fields, and window structure.

No external dependencies — uses built-in osascript.

Usage:
    python scripts/macos_screen_mapper.py --app Messenger
    python scripts/macos_screen_mapper.py --app Messenger --verbose
    python scripts/macos_screen_mapper.py --app Messenger --json

Output (default):
    App: Messenger (PID: 12345)
    Window: Messenger
    Toolbar (4 items): "Chats", "Browse", "More", "Archive"
    Buttons (2): "Facebook", "Settings"
"""

import argparse
import json
import subprocess
import sys


def run_applescript(script: str) -> tuple[bool, str]:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip()


def get_pid(app_name: str) -> int | None:
    for flag in ["-x", "-f"]:
        r = subprocess.run(["pgrep", flag, app_name], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().split("\n")[0])
    return None


def query_toolbar_items(app_name: str) -> list[dict]:
    """List every UI element in toolbar 1 of window 1."""
    script = f"""
tell application "System Events"
    if not (exists process "{app_name}") then return ""
    tell process "{app_name}"
        try
            set tb to toolbar 1 of window 1
            set out to ""
            repeat with el in (UI elements of tb)
                try
                    set r to role of el
                    set d to description of el
                    set t to title of el
                    set out to out & r & "||" & d & "||" & t & "\\n"
                end try
            end repeat
            return out
        on error
            return ""
        end try
    end tell
end tell
"""
    ok, output = run_applescript(script)
    if not ok or not output:
        return []
    items = []
    for line in output.strip().split("\n"):
        parts = line.split("||")
        if len(parts) == 3:
            items.append({"role": parts[0], "description": parts[1], "title": parts[2]})
    return items


def query_window_buttons(app_name: str) -> list[dict]:
    """List top-level buttons of window 1."""
    script = f"""
tell application "System Events"
    if not (exists process "{app_name}") then return ""
    tell process "{app_name}"
        try
            set out to ""
            repeat with btn in (every button of window 1)
                try
                    set out to out & (title of btn) & "||" & (description of btn) & "\\n"
                end try
            end repeat
            return out
        on error
            return ""
        end try
    end tell
end tell
"""
    ok, output = run_applescript(script)
    if not ok or not output:
        return []
    buttons = []
    for line in output.strip().split("\n"):
        parts = line.split("||")
        if len(parts) == 2:
            buttons.append({"title": parts[0], "description": parts[1]})
    return buttons


def query_window_title(app_name: str) -> str:
    script = f"""
tell application "System Events"
    if not (exists process "{app_name}") then return ""
    tell process "{app_name}"
        try
            return name of window 1
        on error
            return ""
        end try
    end tell
end tell
"""
    ok, output = run_applescript(script)
    return output if ok else ""


def map_screen(app_name: str) -> dict:
    pid = get_pid(app_name)
    result: dict = {
        "app": app_name,
        "running": pid is not None,
        "pid": pid,
        "window_title": "",
        "toolbar_items": [],
        "buttons": [],
    }
    if not pid:
        return result
    result["window_title"] = query_window_title(app_name)
    result["toolbar_items"] = query_toolbar_items(app_name)
    result["buttons"] = query_window_buttons(app_name)
    return result


def label_of(item: dict) -> str:
    return item.get("description") or item.get("title") or "?"


def format_summary(data: dict, verbose: bool = False) -> str:
    if not data["running"]:
        return f"App '{data['app']}' is not running"

    lines = [f"App: {data['app']} (PID: {data['pid']})"]

    if data["window_title"]:
        lines.append(f"Window: {data['window_title']}")

    toolbar = data["toolbar_items"]
    if toolbar:
        labels = ", ".join(f'"{label_of(i)}"' for i in toolbar)
        lines.append(f"Toolbar ({len(toolbar)} items): {labels}")
        if verbose:
            for i, item in enumerate(toolbar):
                lines.append(f"  [{i}] role={item['role']} desc={item['description']!r} title={item['title']!r}")
    else:
        lines.append("Toolbar: none found (app may not be fully loaded)")

    buttons = data["buttons"]
    if buttons:
        labels = ", ".join(f'"{label_of(b)}"' for b in buttons[:6])
        if len(buttons) > 6:
            labels += f" +{len(buttons) - 6} more"
        lines.append(f"Buttons ({len(buttons)}): {labels}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Map macOS app screen via System Events")
    parser.add_argument("--app", required=True, help="App process name (e.g., Messenger)")
    parser.add_argument("--verbose", action="store_true", help="Show element details")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = map_screen(args.app)

    if args.json_out:
        print(json.dumps(data, indent=2))
    else:
        print(format_summary(data, verbose=args.verbose))

    sys.exit(0 if data["running"] else 1)


if __name__ == "__main__":
    main()

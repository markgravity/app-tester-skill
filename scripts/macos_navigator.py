#!/usr/bin/env python3
"""
macOS Navigator - Find and Click UI Elements via System Events

Uses osascript to find and interact with macOS app UI elements.
No external dependencies — built-in System Events accessibility API.

Usage:
    # Click toolbar button by label (description or title)
    python scripts/macos_navigator.py --app Messenger --find-text "Chats" --in-toolbar --tap

    # Click toolbar button by 0-based index
    python scripts/macos_navigator.py --app Messenger --index 0 --in-toolbar --tap

    # Click any button by label
    python scripts/macos_navigator.py --app Messenger --find-text "Settings" --tap

    # Just find (no tap) — useful for verifying element exists
    python scripts/macos_navigator.py --app Messenger --find-text "Chats" --in-toolbar

Output:
    Tapped: "Chats" (toolbar index 0)
    Not found: text='Submit'
"""

import argparse
import subprocess
import sys


def run_applescript(script: str) -> tuple[bool, str]:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip()


def click_toolbar_by_label(app_name: str, label: str) -> tuple[bool, str]:
    """Click a toolbar button whose description or title matches label."""
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            set tb to toolbar 1 of window 1
            -- Try by description (tooltip / accessibility label)
            try
                set el to first UI element of tb whose description is "{label}"
                click el
                return "clicked:description"
            end try
            -- Try by title
            try
                set el to first button of tb whose title is "{label}"
                click el
                return "clicked:title"
            end try
            -- Try by help string (tooltip)
            try
                set el to first UI element of tb whose help is "{label}"
                click el
                return "clicked:help"
            end try
            return "not-found"
        on error e
            return "error:" & e
        end try
    end tell
end tell
"""
    ok, out = run_applescript(script)
    if ok and out.startswith("clicked:"):
        return True, f'Tapped: "{label}" (toolbar, matched by {out.split(":")[1]})'
    return False, f'Not found in toolbar: "{label}" (output: {out})'


def click_toolbar_by_index(app_name: str, index: int) -> tuple[bool, str]:
    """Click the toolbar button at 0-based index."""
    # AppleScript lists are 1-based
    as_index = index + 1
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            set tb to toolbar 1 of window 1
            set btns to every button of tb
            if (count of btns) >= {as_index} then
                click item {as_index} of btns
                set lbl to description of item {as_index} of btns
                return "clicked:" & lbl
            else
                return "out-of-range:" & (count of btns)
            end if
        on error e
            return "error:" & e
        end try
    end tell
end tell
"""
    ok, out = run_applescript(script)
    if ok and out.startswith("clicked:"):
        label = out[len("clicked:"):]
        return True, f'Tapped: "{label}" (toolbar index {index})'
    return False, f"Failed to click toolbar index {index} (output: {out})"


def find_toolbar_item(app_name: str, label: str = None, index: int = None) -> tuple[bool, str]:
    """Check existence of a toolbar item without clicking."""
    if index is not None:
        as_index = index + 1
        script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            set tb to toolbar 1 of window 1
            set btns to every button of tb
            if (count of btns) >= {as_index} then
                return "found:" & (description of item {as_index} of btns)
            else
                return "out-of-range:" & (count of btns)
            end if
        on error e
            return "error:" & e
        end try
    end tell
end tell
"""
        ok, out = run_applescript(script)
        found = ok and out.startswith("found:")
        label_found = out[len("found:"):] if found else ""
        return found, f'Found: "{label_found}" at index {index}' if found else f"Not at index {index}: {out}"

    if label:
        script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            set tb to toolbar 1 of window 1
            try
                set el to first UI element of tb whose description is "{label}"
                return "found:description"
            end try
            try
                set el to first button of tb whose title is "{label}"
                return "found:title"
            end try
            return "not-found"
        on error e
            return "error:" & e
        end try
    end tell
end tell
"""
        ok, out = run_applescript(script)
        found = ok and out.startswith("found:")
        return found, f'Found: "{label}"' if found else f'Not found: "{label}"'

    return False, "Specify --find-text or --index"


def click_button(app_name: str, label: str) -> tuple[bool, str]:
    """Click any button in the main window by title or description."""
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            click (first button of window 1 whose title is "{label}")
            return "clicked:title"
        on error
            try
                click (first button of window 1 whose description is "{label}")
                return "clicked:description"
            on error e
                return "not-found:" & e
            end try
        end try
    end tell
end tell
"""
    ok, out = run_applescript(script)
    if ok and out.startswith("clicked:"):
        return True, f'Tapped: "{label}"'
    return False, f'Not found: "{label}"'


def main():
    parser = argparse.ArgumentParser(description="Navigate macOS app UI via System Events")
    parser.add_argument("--app", required=True, help="App process name (e.g., Messenger)")
    parser.add_argument("--find-text", help="Find element by description or title")
    parser.add_argument("--index", type=int, help="0-based element index")
    parser.add_argument("--in-toolbar", action="store_true", help="Restrict search to toolbar")
    parser.add_argument("--tap", action="store_true", help="Click the found element")

    args = parser.parse_args()

    if not args.tap:
        # Find mode — just verify existence
        if args.in_toolbar:
            ok, msg = find_toolbar_item(args.app, label=args.find_text, index=args.index)
        else:
            ok, msg = (False, "Use --in-toolbar for find without --tap")
        print(msg)
        sys.exit(0 if ok else 1)

    # Tap mode
    if args.in_toolbar:
        if args.index is not None:
            ok, msg = click_toolbar_by_index(args.app, args.index)
        elif args.find_text:
            ok, msg = click_toolbar_by_label(args.app, args.find_text)
        else:
            print("Specify --find-text or --index with --in-toolbar --tap")
            sys.exit(1)
    elif args.find_text:
        ok, msg = click_button(args.app, args.find_text)
    else:
        print("Specify --find-text or (--in-toolbar with --index)")
        sys.exit(1)

    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

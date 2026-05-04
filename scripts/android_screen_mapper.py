#!/usr/bin/env python3
"""
android_screen_mapper.py — Android UI Tree Inspector

Dumps and formats the current Android UI accessibility tree using ADB uiautomator.
Equivalent to ios.py's screen_mapper functionality for Android.

Usage:
    python scripts/android_screen_mapper.py
    python scripts/android_screen_mapper.py --serial emulator-5554
    python scripts/android_screen_mapper.py --find "Sign in"
    python scripts/android_screen_mapper.py --verbose
"""

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def resolve_serial(serial: str | None) -> str:
    if serial:
        return serial
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = [l.strip() for l in result.stdout.splitlines() if "\tdevice" in l]
    if not lines:
        raise RuntimeError("No connected Android device/emulator found.")
    return lines[0].split("\t")[0]


def dump_ui(serial: str) -> ET.Element:
    subprocess.run(
        ["adb", "-s", serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml"],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "cat", "/sdcard/ui.xml"],
        capture_output=True, text=True,
    )
    if not result.stdout.strip():
        raise RuntimeError("UI dump was empty — is the screen on and unlocked?")
    return ET.fromstring(result.stdout)


def collect_interactive(root: ET.Element) -> list[dict]:
    """Collect all interactive (clickable/focusable) elements."""
    items = []
    for node in root.iter():
        attrs = node.attrib
        clickable = attrs.get("clickable") == "true"
        focusable = attrs.get("focusable") == "true"
        if not (clickable or focusable):
            continue
        text = attrs.get("text", "")
        desc = attrs.get("content-desc", "")
        res = attrs.get("resource-id", "").split("/")[-1]
        bounds = attrs.get("bounds", "")
        enabled = attrs.get("enabled") == "true"

        m = re.findall(r"\d+", bounds)
        center = None
        if len(m) == 4:
            x1, y1, x2, y2 = map(int, m)
            center = ((x1 + x2) // 2, (y1 + y2) // 2)

        items.append({
            "text": text,
            "desc": desc,
            "id": res,
            "bounds": bounds,
            "center": center,
            "enabled": enabled,
            "clickable": clickable,
        })
    return items


def find_element(root: ET.Element, query: str) -> list[ET.Element]:
    """Find elements whose text or content-desc matches the query."""
    q = query.lower()
    results = []
    for node in root.iter():
        text = node.attrib.get("text", "").lower()
        desc = node.attrib.get("content-desc", "").lower()
        res = node.attrib.get("resource-id", "").lower()
        if q in text or q in desc or q in res:
            results.append(node)
    return results


def format_element(node: ET.Element) -> str:
    attrs = node.attrib
    text = attrs.get("text", "")
    desc = attrs.get("content-desc", "")[:60]
    res = attrs.get("resource-id", "").split("/")[-1]
    cls = attrs.get("class", "").split(".")[-1]
    bounds = attrs.get("bounds", "")
    clickable = "tap" if attrs.get("clickable") == "true" else "   "
    enabled = "" if attrs.get("enabled") == "true" else " [disabled]"
    parts = [f"[{clickable}]{enabled} {cls}"]
    if text:
        parts.append(f'text="{text}"')
    if desc:
        parts.append(f'desc="{desc}"')
    if res:
        parts.append(f'id="{res}"')
    parts.append(bounds)
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Inspect Android UI accessibility tree")
    parser.add_argument("--serial", help="ADB device serial")
    parser.add_argument("--find", metavar="TEXT", help="Find elements matching text/id")
    parser.add_argument("--verbose", action="store_true", help="Show all elements, not just interactive")
    args = parser.parse_args()

    try:
        serial = resolve_serial(args.serial)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        root = dump_ui(serial)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.find:
        matches = find_element(root, args.find)
        if not matches:
            print(f"No elements found matching: {repr(args.find)}")
            sys.exit(1)
        print(f"Found {len(matches)} match(es) for {repr(args.find)}:")
        for node in matches:
            print(f"  {format_element(node)}")
        return

    if args.verbose:
        def walk(node, depth=0):
            attrs = node.attrib
            text = attrs.get("text", "")
            desc = attrs.get("content-desc", "")[:60]
            res = attrs.get("resource-id", "").split("/")[-1]
            cls = attrs.get("class", "").split(".")[-1]
            bounds = attrs.get("bounds", "")
            if text or desc or res:
                print("  " * depth + format_element(node))
            for child in node:
                walk(child, depth + 1)
        walk(root)
    else:
        items = collect_interactive(root)
        if not items:
            print("No interactive elements found")
            sys.exit(1)

        print(f"Interactive elements ({len(items)}):")
        for item in items:
            label = item["text"] or item["desc"] or item["id"] or "(unlabeled)"
            center = f"@ {item['center']}" if item["center"] else ""
            enabled = "" if item["enabled"] else " [disabled]"
            print(f"  {'[tap]' if item['clickable'] else '[   ]'}{enabled} {label!r} {center} id={item['id']!r}")


if __name__ == "__main__":
    main()

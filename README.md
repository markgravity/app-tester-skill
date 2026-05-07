# app-tester

A Claude Code skill for testing iOS, macOS, tvOS, and Android app navigation flows — without screenshots — driven by [`agent-device`](https://github.com/callstackincubator/agent-device).

Builds a persistent graph of your app's screens, instruments source files with structured logs and accessibility identifiers, then drives flows end-to-end using compact accessibility snapshots and console logs. Screenshots are only taken when a step fails.

## How it works

1. **Discovers** your app's screens by reading the navigation source (Screen enum, GoRoute, Expo Router tree, etc.)
2. **Instruments** each screen with `.accessibilityIdentifier()` / `Semantics(label:)` / `testID` and `print()` / `console.log()` lines
3. **Drives flows** via `agent-device` — `open` → `snapshot -i` → `press` / `fill` / `scroll` → `wait` → `close` — confirming each step via console logs
4. **Recovers inline** when a step breaks — reads source, fixes instrumentation or app bug, re-attaches, retries, updates the graph
5. **Persists** everything in `.tester/app-graph.yaml` (screens) and `.tester/flows/*.yaml` (one file per flow) at the project root, with staleness detection on every run

## Installation

Copy the skill into your personal Claude Code skills directory:

```bash
git clone https://github.com/markgravity/app-tester-skill ~/.claude/skills/app-tester
```

Then install `agent-device` (Node ≥22 required):

```bash
npm install -g agent-device
agent-device --version          # confirm >= 0.14.0
agent-device help workflow      # canonical session loop
```

Platform SDKs are still required for the **build** step:

- iOS / macOS / tvOS: Xcode + Command Line Tools.
- Android: Android SDK with `adb` on PATH (`$HOME/Library/Android/sdk/platform-tools`).
- Flutter: `~/fvm/versions/stable/bin/flutter` or `flutter` on PATH.
- macOS automation: grant Accessibility permission in System Settings → Privacy & Security → Accessibility.

## Usage

Invoke via slash command or let Claude trigger it automatically:

```
/app-tester
test the create game flow
test all flows
instrument screens
rebuild the graph
check that onboarding works end to end
```

## Sensitive credentials

Create a `.env` file at your project root (add to `.gitignore`):

```bash
TEST_USERNAME=your@email.com
TEST_PASSWORD=yourpassword
TEST_PERMISSIONS=camera,location,notifications
SYSTEM_PROMPT_DISMISS=Ask App Not to Track,Don't Allow,Allow Once,Not Now,Dismiss,OK,Allow
```

## Graph files

The skill stores data in `.tester/` at your project root:
- `.tester/app-graph.yaml` — app metadata and screen graph (screens, transitions, accessibility IDs)
- `.tester/flows/<flow-id>.yaml` — one file per named flow (kebab-case filename)

Each run:
- Checks if navigation source files changed since last run
- Diffs old vs new screens and marks affected flows for re-testing
- Updates `lastResult` (PASSED / FAILED / UNKNOWN) in each flow file after each run

## License

MIT

---
name: app-tester
description: >
  Build and maintain a navigable graph of any iOS or macOS app's screens. Reads the
  project's navigation source to understand flows, instruments Swift screen files with
  structured print logs and .accessibilityIdentifier() modifiers, then drives flows
  end-to-end using console logs and the accessibility tree — without requiring screenshots.
  Use when: (1) user says "test the [flow] flow", "test all flows", "instrument screens",
  "update the flow graph", "rebuild the graph", "run flow tests", or "check that [feature]
  works end to end", (2) after adding or modifying screens or navigation logic,
  (3) when debugging a broken navigation flow. Works on iOS simulator and macOS.
---

# App Tester

Tests iOS and macOS app navigation flows without relying on screenshots. Works on any SwiftUI or UIKit project.

**Strategy:**
1. Read the project's navigation source to build `.claude/app-flow-graph.json` at the project root.
2. Instrument screen files with structured `print` logs and `.accessibilityIdentifier()`.
3. Drive flows by tapping accessibility IDs and confirming transitions via console logs.
4. Take screenshots **only when a step fails**.

**Bundled scripts:**
```
~/.claude/skills/app-tester/scripts/
  iOS:
    app_launcher.py       — launch/terminate via xcrun simctl
    screen_mapper.py      — read accessibility tree via idb
    navigator.py          — tap/interact via idb
    log_monitor.py        — stream simulator logs
    privacy_manager.py    — pre-grant permissions
    dismiss_prompts.py    — dismiss system dialogs
    common/               — shared idb/simctl utils

  macOS:
    macos_launcher.py     — launch/terminate macOS .app bundles
    macos_screen_mapper.py — read window/toolbar elements via System Events
    macos_navigator.py    — click toolbar/window elements via System Events
    macos_log_monitor.py  — stream app logs via `log stream`
```

**Requirements:**
- iOS: `idb` for accessibility tree + taps, `xcrun simctl` for launch + logs.
  Install: `brew install idb-companion && pip install fb-idb`
- macOS: `osascript` (built-in) for accessibility, `log` (built-in) for logs. No extra deps.

---

## Sensitive Credentials (.env)

Some flows require authentication. Store credentials in `.env` at the project root (add to `.gitignore`):
```bash
TEST_USERNAME=your@email.com
TEST_PASSWORD=yourpassword
TEST_PERMISSIONS=camera,location,notifications   # iOS only
SYSTEM_PROMPT_DISMISS=Ask App Not to Track,Don't Allow,Allow Once,Not Now,Dismiss,OK,Allow
```

Load before testing: `export $(grep -v '^#' .env | xargs)`

---

## Step 0: Project Setup

Identify these values before any phase:

| Value | How to find it |
|---|---|
| **Platform** | `SUPPORTED_PLATFORMS` in build settings, or check deployment target — `macosx` = macOS, `iphonesimulator` = iOS |
| **Bundle ID** | `PRODUCT_BUNDLE_IDENTIFIER` in build settings or Info.plist |
| **App name** | `CFBundleDisplayName` / `CFBundleName` in Info.plist or the Xcode scheme name |
| **Screen files** | Directory containing `*View.swift` or `*ViewController.swift` |
| **Navigation source** | File with Screen/Route enum or coordinator |
| **Log prefix** | `[AppName]` — used in all instrumentation |

---

## Phase 1: App Discovery

Run when `.claude/app-flow-graph.json` does not exist, the navigation source has changed, or the user says "rebuild the graph".

### 1.1 Read the navigation source

Find files defining all screens/routes:
- **NavigationStack / FlowStacks**: A `Screen` or `Route` enum with all cases
- **Coordinators**: `navigate(to:)` calls covering all destinations
- **UIKit**: Router with `push`/`present` calls

### 1.2 Read every screen file

For each screen extract:
- Outgoing navigation calls (`push`, `present`, `NavigationLink`, etc.) — these are edges
- `.onAppear` / `viewDidAppear` — where appearance logs go
- Primary action closures — where tap logs go

### 1.3 Determine feature groupings

Group screens by directory structure, naming conventions, or functional area.

### 1.4 Write the graph

Create `.claude/app-flow-graph.json` at the project root. See **Graph Schema** below.

---

## Phase 2: Instrumentation

### 2.1 Accessibility IDs — screen roots

Add `.accessibilityIdentifier("snake_case_screen")` to the outermost container of each screen's `body`.

```swift
var body: some View {
    VStack { ... }
        .accessibilityIdentifier("game_list_screen")
        .onAppear { viewModel.load() }
}
```

### 2.2 Accessibility IDs — action elements

Tag primary navigation triggers:
- `primary_action_button`, `secondary_action_button`, `cancel_button`
- Named per feature: `create_game_button`, `invite_button`, etc.

### 2.3 Screen appearance logs

```swift
.onAppear {
    print("[AppName] [Feature] ScreenName appeared")
    // existing code
}
```

### 2.4 Action tap logs

```swift
Button("Create Game") {
    print("[AppName] [Feature] createGame tapped")
    navigator.show(screen: .createGame(group))
}
```

### 2.5 Build to verify

**iOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build
```

**macOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build
```

---

## Phase 3: Flow Testing (iOS)

> **Requirements:** `idb` + `xcrun simctl`

### 3.1 Load the graph

Read `.claude/app-flow-graph.json`. Target flow(s) by name or all `"enabled": true` flows.

### 3.2 Pre-grant permissions

```bash
python3 ~/.claude/skills/app-tester/scripts/privacy_manager.py \
  --bundle-id <bundle.id> --grant camera,location,notifications
```

### 3.2b Dismiss system prompts

Run after every launch and every tap (no-op if no dialog):
```bash
python3 ~/.claude/skills/app-tester/scripts/dismiss_prompts.py \
  --policy "$SYSTEM_PROMPT_DISMISS"
```

---

### 3.2c System Alerts Reference

Different alert types require different strategies. Choose based on the alert's source process.

#### General rule

When any unexpected dialog blocks a flow step:

1. Run `idb ui describe-all --json` and check if the dialog's buttons appear in the output.
2. **If visible** — it runs in-process. Tap the dismiss button by coordinate (see [D]).
3. **If not visible** — it runs in a separate OS process (e.g. `com.apple.AuthKitUIService`). idb cannot interact with it; use credential injection to bypass the flow entirely (see [C]).

Add recurring dismiss labels (e.g. `"Not Now"`, `"Ask App Not to Track"`) to `SYSTEM_PROMPT_DISMISS` in `.env` so `dismiss_prompts.py` handles them automatically on every launch and tap.

#### Quick decision tree

```
System alert appeared?
 ├─ Permission dialog (location, camera, contacts, notifications)?
 │   → Pre-grant via simctl privacy before launch — see [A]
 │   → Or tap via idb if dialog still appears (visible in screen tree)
 ├─ ATT (App Tracking Transparency)?
 │   → Tap via idb — visible in screen tree — see [B]
 ├─ Sign In with Apple?
 │   → Cross-process — bypass via credential injection — see [C]
 └─ Unknown / other dialog?
     → Run idb ui describe-all — if visible, tap dismiss — see [D]
     → If not visible, it's cross-process — use credential injection — see [C]
```

---

#### [A] Permission dialogs — pre-grant before launch (preferred)

Avoids the dialog entirely. Run before `app_launcher.py`:

```bash
# Grant individual permissions
xcrun simctl privacy booted grant location   dev.example.app
xcrun simctl privacy booted grant camera     dev.example.app
xcrun simctl privacy booted grant contacts   dev.example.app
xcrun simctl privacy booted grant photos     dev.example.app
xcrun simctl privacy booted grant microphone dev.example.app

# Or revoke to reset state
xcrun simctl privacy booted revoke location  dev.example.app
```

Use `privacy_manager.py` to grant multiple at once from `TEST_PERMISSIONS`:
```bash
python3 ~/.claude/skills/app-tester/scripts/privacy_manager.py \
  --bundle-id dev.example.app --grant camera,location,notifications
```

If a permission dialog still appears at runtime, find and tap its button via idb (these run in-process):
```bash
idb ui describe-all --json | python3 -c "
import json, sys
for n in json.load(sys.stdin):
    if n.get('AXLabel','') in ('Allow','Allow Once','Don\\'t Allow','OK'):
        print(n['AXLabel'], n['AXFrame'])
"
# Then tap the button's center coordinate:
idb ui tap <x> <y>
```

---

#### [B] ATT (App Tracking Transparency) — tap via idb

ATT runs **in-process** — `idb ui describe-all` can see it. It will appear as 4–5 nodes with no `AXUniqueId`.

Detection and tap pattern:
```bash
# Check if ATT is showing
idb ui describe-all --json | python3 -c "
import json, sys
nodes = json.load(sys.stdin)
for n in nodes:
    label = n.get('AXLabel', '')
    if 'track' in label.lower() or 'Ask App Not to Track' in label:
        frame = n.get('AXFrame', '')
        print(f'ATT visible — label={label!r} frame={frame}')
"

# Get the dismiss button's frame and tap its center
idb ui describe-all --json | python3 -c "
import json, sys, re
nodes = json.load(sys.stdin)
for n in nodes:
    if n.get('AXLabel','') == 'Ask App Not to Track':
        # AXFrame format: {{x, y}, {w, h}}
        nums = [float(x) for x in re.findall(r'[\d.]+', n['AXFrame'])]
        cx, cy = int(nums[0] + nums[2]/2), int(nums[1] + nums[3]/2)
        print(f'{cx} {cy}')
" | xargs idb ui tap
```

Or add `"Ask App Not to Track"` to `SYSTEM_PROMPT_DISMISS` in `.env` — `dismiss_prompts.py` handles it automatically.

---

#### [C] Sign In with Apple — cross-process, use credential injection

Sign In with Apple runs in **`com.apple.AuthKitUIService`** — a separate OS process. `idb ui describe-all` cannot see its elements. Coordinate tapping returns `ASAuthorizationError error 1000` on simulator.

**Solution: bypass the Apple sheet entirely — inject an email/password session via launch arguments**

Create a dedicated test account in your auth backend (email + password), then intercept app launch in a `#if DEBUG` guard before the normal auth flow runs.

**Step 1 — Create a test account (one-time)**

Use your auth backend's signup API to create a machine account (e.g. `test-automation@yourapp.dev`). Do not use a real Apple ID or production account.

**Step 2 — Instrument the app**

Find the earliest point in the app's auth initialization that runs before any auth check. Inject a login using the backend's email/password method:

```swift
// In your auth service's initialize() / setup() method — before any auth state checks
#if DEBUG
if ProcessInfo.processInfo.arguments.contains("-UITestInjectSession"),
   let email = ProcessInfo.processInfo.environment["TEST_EMAIL"],
   let password = ProcessInfo.processInfo.environment["TEST_PASSWORD"] {
    do {
        // Replace with your auth backend's email+password sign-in call:
        //   Firebase:   Auth.auth().signIn(withEmail: email, password: password)
        //   Supabase:   client.auth.signIn(email: email, password: password)
        //   Custom JWT: authService.signIn(email: email, password: password)
        let result = try await yourAuthBackend.signIn(email: email, password: password)

        // ⚠️ Do NOT rely on currentUser/currentSession properties immediately after sign-in.
        // Some SDKs (e.g. Supabase Swift) do not synchronously populate them.
        // Extract the user ID from the returned result object directly:
        let userId = result.user.id   // or result.uid, result.accessToken, etc.
        print("[Auth] test sign-in succeeded — userId=\(userId)")

        // Run your normal post-auth setup with the known userId, then return early
        try await setupAuthenticatedSession(userId: userId)
        return
    } catch {
        print("[Auth] test sign-in FAILED: \(error)")
        // Fall through to normal (unauthenticated) initialization
    }
}
#endif
```

> **SDK gotcha — `currentUser` nil after `signIn()`**: Some auth SDKs (notably Supabase Swift) do not synchronously update `currentUser` / `currentSession` after a `signIn()` call returns. Always read the user ID from the `Session`/`AuthResult` object that `signIn()` returns, not from a separate `currentUser` property access right after.

**Step 3 — Launch with credentials**

`SIMCTL_CHILD_` env vars are forwarded by simctl to the launched process:

```bash
SIMCTL_CHILD_TEST_EMAIL="test-automation@yourapp.dev" \
SIMCTL_CHILD_TEST_PASSWORD="YourTestPass123!" \
xcrun simctl launch --console-pty booted com.example.app \
  -UITestInjectSession
```

Store in `.env` (add to `.gitignore`):
```bash
TEST_EMAIL=test-automation@yourapp.dev
TEST_PASSWORD=YourTestPass123!
```

**Step 4 — Confirm injection worked**

Check console output for your success log line (e.g. `[Auth] test sign-in succeeded`) and that the app reaches an authenticated screen rather than the login screen.

---

#### [D] Unknown in-process dialog — general dismiss pattern

Use this when an unexpected dialog blocks a flow step and `idb ui describe-all` shows it in the accessibility tree.

**Step 1 — Identify the dismiss button and its center:**

```bash
idb ui describe-all --json | python3 -c "
import json, sys, re
nodes = json.load(sys.stdin)
for n in nodes:
    label = n.get('AXLabel', '')
    # Print all buttons/static text so you can identify the dialog
    if label:
        nums = [float(x) for x in re.findall(r'[\d.]+', n.get('AXFrame',''))]
        if len(nums) == 4:
            cx, cy = int(nums[0] + nums[2]/2), int(nums[1] + nums[3]/2)
            print(f'{label!r}: center=({cx},{cy})')
"
```

**Step 2 — Tap the dismiss button by coordinate:**

```bash
idb ui tap <cx> <cy>
```

**Step 3 — Add to `SYSTEM_PROMPT_DISMISS` so it's handled automatically:**

```bash
# .env
SYSTEM_PROMPT_DISMISS=Not Now,Ask App Not to Track,Don't Allow,Allow Once,OK,Allow
```

`dismiss_prompts.py` runs after every launch and tap and dismisses any button whose label matches.

> **Example — "Apple Account Verification" dialog** (simulator Apple ID re-verification):
> Text: *"Enter the password for \<email\> in Settings."* — Buttons: **Not Now**, **Settings**.
> This is in-process and idb-visible. Dismiss before interacting with the Sign in with Apple sheet, otherwise taps land on the dialog instead.
> `idb ui tap 127 507` (Not Now, standard iPhone simulator 402×874 pt)

---

### 3.3 Build and launch

> **IMPORTANT:** Always pass `--app-path` when launching after a build. `--launch` alone only starts the already-installed binary — the simulator will silently run the stale build if you skip this.

> **Log capture method:** Swift `print()` writes to **stdout**, not the unified logging system. `log stream` will NOT capture these. Always launch with `--console-pty` and redirect to a file so log confirmation in 3.4 works. If the app uses `os_log`/`Logger` instead, you can use `log stream` as a fallback.

```bash
# Find the built .app path
APP_PATH=$(xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' \
  -showBuildSettings 2>/dev/null | grep ' CODESIGNING_FOLDER_PATH' | awk '{print $3}')

# Build
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build

# Install then launch capturing stdout (required for print()-based log confirmation)
xcrun simctl install booted "$APP_PATH"
xcrun simctl terminate booted <bundle.id> 2>/dev/null; sleep 1
xcrun simctl launch --console-pty booted <bundle.id> > /tmp/app_logs.txt 2>&1 &
```

### 3.4 Navigate each step

**Confirm current screen:**
```bash
python3 ~/.claude/skills/app-tester/scripts/screen_mapper.py
```

**Tap by accessibility ID:**
```bash
python3 ~/.claude/skills/app-tester/scripts/navigator.py --find-id "primary_action_button" --tap
```

**Confirm via log:**
```bash
grep "\[AppName\]" /tmp/app_logs.txt | tail -5
```

**Mark step:** PASSED if log confirmed or accessibility ID found. FAILED → enter Phase 4 immediately (inline recovery). Resume Phase 3 from the current step after recovery succeeds. Only move on to the next step once the current step is confirmed PASSED.

### 3.5 Report

```
Flow: Create Game  Status: PASSED ✓
  Step 1  main → gameList       PASSED   log: [Scoreboard] [Game] GameList appeared
  Step 2  gameList → createGame PASSED   log: [Scoreboard] [Game] GameCreate appeared
```

---

## Phase 3 (macOS): Flow Testing

> **Requirements:** macOS app built for `platform=macOS`. Tools use built-in `osascript` + `log` — no extra deps.
>
> **Accessibility permission:** On first run, macOS may prompt "Terminal wants to control System Events". Grant it in System Settings → Privacy & Security → Accessibility.

### 3.1 Load the graph

Same as iOS — read `.claude/app-flow-graph.json`.

### 3.2 Build and launch

```bash
# Build
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build

# Find the built .app
APP_PATH=$(python3 ~/.claude/skills/app-tester/scripts/macos_launcher.py --find <Scheme>)
echo "App: $APP_PATH"

# Terminate any existing instance first
osascript -e 'tell application "<AppName>" to quit' 2>/dev/null; sleep 1

# Launch with stdout captured (required for print()-based log confirmation)
python3 ~/.claude/skills/app-tester/scripts/macos_launcher.py \
  --launch "$APP_PATH" --capture-stdout /tmp/macos_logs.txt
```

> **Log capture method depends on how the app logs:**
> - **`print()`** (Swift `print()` / `NSLog` to stdout): launch binary directly via `--capture-stdout`. `log stream` will NOT capture these.
> - **`os_log` / `Logger`** (unified logging): use `macos_log_monitor.py` with `log stream`.
> - **Unknown**: try `--capture-stdout` first; if empty after 5s, fall back to `macos_log_monitor.py`.

### 3.3 Confirm UI loaded

```bash
python3 ~/.claude/skills/app-tester/scripts/macos_screen_mapper.py --app <AppName>
```

Expected output shows window title and toolbar/button elements. If `not running`, wait 1–2s and retry.

### 3.4 Navigate each step

**Click toolbar item by label (tooltip / accessibility description):**
```bash
python3 ~/.claude/skills/app-tester/scripts/macos_navigator.py \
  --app <AppName> --find-text "Chats" --in-toolbar --tap
```

**Click toolbar item by 0-based index:**
```bash
python3 ~/.claude/skills/app-tester/scripts/macos_navigator.py \
  --app <AppName> --index 0 --in-toolbar --tap
```

**Click any window button by label:**
```bash
python3 ~/.claude/skills/app-tester/scripts/macos_navigator.py \
  --app <AppName> --find-text "Settings" --tap
```

**Verify element exists without clicking:**
```bash
python3 ~/.claude/skills/app-tester/scripts/macos_navigator.py \
  --app <AppName> --find-text "Archive" --in-toolbar
```

### 3.5 Confirm via log

```bash
# For print()-based apps (--capture-stdout):
grep "\[AppName\]" /tmp/macos_logs.txt

# For os_log-based apps (macos_log_monitor.py):
python3 ~/.claude/skills/app-tester/scripts/macos_log_monitor.py \
  --app <AppName> --duration 3s --grep "\[AppName\]"
```

### 3.6 Report

```
Flow: Toolbar Navigation  Status: PASSED ✓
  Step 1  Launch app         PASSED   macos_screen_mapper: 4 toolbar items found
  Step 2  Click "Chats"      PASSED   log: [Messenger][WebView] Nav section Chats result: clicked:0
  Step 3  Click "Archive"    PASSED   log: [Messenger][WebView] Nav section Archive result: clicked:3
```

---

## Phase 4: Inline Recovery (Step Failure)

Triggered immediately when a step fails during Phase 3. The goal is always to **recover and continue the flow** — not just record the failure. Only mark the flow `FAILED` if recovery is impossible.

### 4.1 Capture current state

```bash
# iOS
xcrun simctl io booted screenshot /tmp/flow_failure_step<N>.png
python3 ~/.claude/skills/app-tester/scripts/screen_mapper.py --verbose

# macOS
screencapture -x /tmp/flow_failure_step<N>.png
python3 ~/.claude/skills/app-tester/scripts/macos_screen_mapper.py --app <AppName>
```

Read the screenshot and accessibility tree together to understand exactly what's on screen.

### 4.2 Diagnose the failure

| Symptom | Likely cause | Recovery action |
|---|---|---|
| Element not found by ID | Accessibility ID mismatch or missing | Fix in Swift source → rebuild → retry |
| No log line appeared | Log statement missing | Add log to Swift source → rebuild → retry |
| Auth/login screen shown | Step requires authentication | Supply credentials from `.env`, log in, then resume from next step |
| Same screen stays visible | Button disabled / gate not met | Check source for guard conditions; satisfy prerequisite, retry |
| Unexpected screen shown | Navigation logic changed | Re-read nav source; update graph edge; find new path forward |
| Crash / blank screen | Runtime error | Read full log output; fix the crash; relaunch from step 1 |
| `not running` from screen_mapper | App crashed or hasn't launched | Relaunch app, re-navigate to step's screen |

### 4.3 Read the source file

Open the screen's `swiftFile` from the graph node:
- Is `.accessibilityIdentifier()` present and matching the graph's `accessibilityId`?
- Is the `print("[AppName] [Feature] ScreenName appeared")` in `.onAppear`?
- Is the tap log before the navigation call?
- Did the navigation call change (different screen, different transition)?

### 4.4 Fix instrumentation if missing

If accessibility ID or log is absent or wrong, add/correct it now:

```swift
// Add to outermost container
.accessibilityIdentifier("screen_name_screen")

// Add to .onAppear
print("[AppName] [Feature] ScreenName appeared")

// Add before navigation call
print("[AppName] [Feature] actionName tapped")
```

Then rebuild:
```bash
# iOS
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build

# macOS
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build
```

### 4.5 Find a way to the next step

Even if the current action element can't be found by its recorded ID, try to reach `toScreen` another way:
1. `screen_mapper.py --verbose` — list all buttons/elements currently on screen
2. Look for the target action by label text: `--find-text "<ButtonLabel>" --tap`
3. If the screen layout changed, trace the new path in source and use it
4. If an interstitial screen (e.g. login, onboarding, permission) is blocking, handle it and continue

### 4.6 Retry the step

After fixing, re-attempt the exact step:
1. Confirm current screen (accessibility ID or log)
2. Tap the action
3. Confirm transition (log line)

If it passes → continue the flow from the next step.

### 4.7 Update the graph with what was learned

After recovery (whether the step passed or the flow was fully unblocked):

```json
// Updated node (example)
{
  "accessibilityId": "corrected_screen_id",
  "transitions": [
    {
      "action": "updated_action_name",
      "actionAccessibilityId": "corrected_button_id",
      "nextScreen": "actualNextScreen",
      "logConfirmation": "[AppName] [Feature] ActualScreen appeared"
    }
  ]
}
```

Also update `updatedAt` in the graph root to the current ISO-8601 timestamp.

### 4.8 If recovery fails

If the flow cannot be unblocked after all recovery attempts:
- Set `"lastResult": "FAILED"` on the flow
- Set `"failureNote"` describing exactly which step failed and why
- Continue testing remaining flows (don't abort the full run)
- On next run, Phase 0 will flag this flow as requiring re-test after fixes

---

## Graph Schema

File: `.claude/app-flow-graph.json` at project root.

```json
{
  "version": 1,
  "updatedAt": "ISO-8601 timestamp",
  "appName": "YourAppName",
  "bundleId": "com.example.yourapp",
  "platform": "ios | macos",
  "projectRoot": "/absolute/path/to/project",
  "navSourceFiles": [
    "relative/path/to/Navigator+Screen.swift",
    "relative/path/to/NavigatorStack.swift"
  ],
  "screens": {
    "screenId": {
      "screenId": "gameList",
      "displayName": "Game List",
      "feature": "Game",
      "swiftFile": "relative/path/GameListView.swift",
      "accessibilityId": "game_list_screen",
      "notes": "optional",
      "transitions": [
        {
          "action": "create_game_button",
          "actionAccessibilityId": "primary_action_button",
          "nextScreen": "createGame",
          "transition": "presentCover",
          "logConfirmation": "[AppName] [Feature] ScreenName appeared"
        }
      ]
    }
  },
  "namedFlows": {
    "flowId": {
      "name": "Human readable name",
      "description": "What this flow validates",
      "enabled": true,
      "lastResult": "PASSED | FAILED | UNKNOWN",
      "failureNote": null,
      "steps": [
        {
          "stepId": 1,
          "fromScreen": "screenId",
          "toScreen": "screenId",
          "action": "accessibilityId or null",
          "logConfirmation": "[AppName] [Feature] ScreenName appeared",
          "prerequisites": ["plain-English required state"]
        }
      ]
    }
  }
}
```

**Field notes:**
- `platform` — `"ios"` or `"macos"`; drives which Phase 3 scripts to use
- `accessibilityId` — snake_case; set via `.accessibilityIdentifier()` in Swift
- `action` — `null` / `auto_on_*` for programmatic transitions; use `--find-text` label for macOS toolbar items
- `logConfirmation` — exact prefix to grep in console output

---

## Phase 0: Graph Staleness Check

Run this before Phase 3 every time. Determines whether to trust the existing graph or rebuild it first.

### 0.1 Check if graph exists

If `.claude/app-flow-graph.json` is missing → run Phase 1 now, then Phase 2, then Phase 3.

### 0.2 Compare navigation source against graph

Read the graph's `updatedAt` timestamp and `navSourceFiles` list (see schema). For each listed file, check its last-modified time or git log:

```bash
git log -1 --format="%ai" -- <navSourceFile>
```

If **any nav source file was modified after `updatedAt`** → the graph is stale.

### 0.3 Stale graph — what to do

| Change severity | Action |
|---|---|
| Nav source file(s) modified | Re-run Phase 1 (rebuild graph), then Phase 2 for any new/changed screens |
| Screen file(s) modified (no nav changes) | Re-run Phase 2 for those files only; update `updatedAt` in graph |
| Graph missing `navSourceFiles` | Treat as stale; run Phase 1 |

After Phase 1 runs, diff the old screens against the new:
- **New screenId** → add node + transitions; mark any flows touching it as `"lastResult": "UNKNOWN"`
- **Removed screenId** → remove node; mark affected flows as `"lastResult": "UNKNOWN"` with `failureNote: "screen removed"`
- **Changed transitions** → update edges; mark affected flows as `"lastResult": "UNKNOWN"`
- **No diff** → graph is current; proceed to Phase 3 directly

### 0.4 Mark stale flows before testing

Any flow with `"lastResult": "UNKNOWN"` must be re-tested to get a fresh result. Flows with `"PASSED"` that touch no changed screens can be skipped or run for confidence.

---

## When to Update the Graph

- Before every test run: run Phase 0 to detect nav source drift automatically
- New screen added to navigation source → Phase 1 rebuild
- Navigation call added, removed, or transition type changed → Phase 1 rebuild
- Accessibility ID changed in Swift source → update node's `accessibilityId`, re-instrument
- Flow prerequisite changes (permission gate, auth requirement) → update `prerequisites` in affected steps
- Phase 4 identifies a failure root cause → targeted edge/node fix + set `lastResult: "FAILED"` then re-run to confirm

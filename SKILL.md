---
name: app-tester
description: >
  Build and maintain a navigable graph of any iOS, macOS, tvOS, or Android app's screens.
  Reads the project's navigation source to understand flows, instruments screen files with
  structured print logs and accessibility identifiers, then drives flows end-to-end via the
  `agent-device` CLI — using compact accessibility snapshots (no screenshots needed unless a
  step fails).
  Use when: (1) user says "test this", "test it", "test [feature/screen/flow]",
  "test the [flow] flow", "test all flows", "instrument screens", "update the flow graph",
  "rebuild the graph", "run flow tests", or "check that [feature] works end to end",
  (2) after adding or modifying screens or navigation logic,
  (3) when debugging a broken navigation flow.
  Works on iOS simulator + device, Android emulator + device, macOS, tvOS, and Android TV
  through a single CLI surface. SwiftUI / UIKit / Flutter / Expo / React Native are all
  supported — only the build + instrumentation step is platform-specific; UI driving is unified.
---

# App Tester

Tests app navigation flows by driving the device with `agent-device`, a unified CLI for iOS,
Android, macOS, tvOS, and Android TV (real devices and simulators).

**Strategy**

1. Read the project's navigation source to build `.tester/app-graph.yaml` and
   `.tester/flows/*.yaml` at the project root.
2. Instrument screen files with structured print/console.log lines and accessibility
   identifiers (`testID` / `Semantics` / `.accessibilityIdentifier()`).
3. Drive flows by `open` → `snapshot -i` → `press`/`fill`/`scroll` → confirm via console
   logs → `close` — all via `agent-device`.
4. Take screenshots **only when a step fails**.

## Requirements

- **`agent-device`** — the only runtime dependency. `npm install -g agent-device` (Node ≥22).
- Platform SDKs for the **build** step only:
  - iOS / macOS / tvOS: Xcode + Command Line Tools.
  - Android: Android SDK + ADB on PATH (`$HOME/Library/Android/sdk/platform-tools`).
  - Flutter: `~/fvm/versions/stable/bin/flutter` or `flutter` on PATH.
  - Expo / React Native: Node + the project's package manager.
- macOS Accessibility permission for desktop automation (System Settings → Privacy &
  Security → Accessibility, on first run).

## Routing into agent-device help

`agent-device` is the source of truth for command syntax — it ships versioned help that this
skill is intentionally not duplicating. Whenever you need exact flags or new commands, run:

```bash
agent-device --version
agent-device help workflow      # canonical session loop + selectors
agent-device help debugging     # logs, network, performance, react-devtools
agent-device help macos         # macOS-specific notes
agent-device help remote        # device farms / cloud
```

If `agent-device --version` reports `< 0.14.0`, upgrade before using this skill — older CLIs
lack the help topics above.

## Canonical session loop

```text
open <app>  →  snapshot -i  →  get / is / find  →  press / fill / scroll / wait  →  verify  →  close
```

Snapshots assign refs (`@e1`, `@e2`, …) to current-screen elements. Refs from the most recent
snapshot are immediately actionable. If a target appears only in an off-screen summary, use
`scroll <direction>` and re-snapshot until it's visible.

A minimal flow step:

```bash
agent-device open com.example.YourApp --platform ios
agent-device snapshot -i                                 # find @e for the action
agent-device press --label "Create Game"                 # or: press @e3
# verify via app logs (see "Log confirmation" below)
agent-device close
```

> Always look up exact selectors and flags via `agent-device help workflow` rather than guessing.

---

## Sensitive Credentials (.env)

Some flows require authentication. Store credentials in `.env` at the project root (add to
`.gitignore`):

```bash
TEST_USERNAME=your@email.com
TEST_PASSWORD=yourpassword
TEST_PERMISSIONS=camera,location,notifications      # iOS only
SYSTEM_PROMPT_DISMISS=Ask App Not to Track,Don't Allow,Allow Once,Not Now,Dismiss,OK,Allow
```

Load before testing: `export $(grep -v '^#' .env | xargs)`

---

## Step 0: Project Setup

Identify these values once before any phase.

**iOS / macOS / tvOS (SwiftUI / UIKit):**

| Value | How to find it |
|---|---|
| **Platform** | `SUPPORTED_PLATFORMS` in build settings — `macosx`, `iphonesimulator`, `appletvsimulator` |
| **Bundle ID** | `PRODUCT_BUNDLE_IDENTIFIER` in build settings or Info.plist |
| **App name** | `CFBundleDisplayName` / `CFBundleName` in Info.plist or Xcode scheme name |
| **Screen files** | Directory containing `*View.swift` or `*ViewController.swift` |
| **Navigation source** | File with Screen/Route enum or coordinator |
| **Log prefix** | `[AppName]` — used in all instrumentation |

**Android / Flutter:**

| Value | How to find it |
|---|---|
| **Platform** | Presence of `android/`. Flutter = `pubspec.yaml` present |
| **Package ID** | `applicationId` in `android/app/build.gradle(.kts)` |
| **App name** | `android:label` in `AndroidManifest.xml` |
| **Screen files** | Flutter: `lib/features/*/screens/` or `lib/screens/` (`*Screen.dart` / `*Page.dart`) |
| **Navigation source** | Flutter: GoRouter config, or files with `GoRoute` / `Navigator.push` calls |
| **Device serial** | `adb devices` — e.g. `emulator-5554` |
| **Log prefix** | `[AppName]` — used in `print()` calls |

**Expo / React Native (iOS + Android):**

Identify by `package.json` containing `expo` or `react-native`. Expo Router projects also have
an `app/` directory with file-based routes.

| Value | How to find it |
|---|---|
| **Platform** | `package.json` has `expo` → Expo. `react-native` only → bare RN |
| **Bundle ID (iOS)** | `app.json` → `expo.ios.bundleIdentifier`, or `ios/<App>/Info.plist` |
| **Package ID (Android)** | `app.json` → `expo.android.package`, or Android `applicationId` |
| **App name** | `app.json` → `expo.name`, or `app.config.{js,ts}` |
| **Router type** | `app/` directory exists → **Expo Router** (file-based). Otherwise `@react-navigation/*` |
| **Screen files** | Expo Router: `app/**/*.tsx` + `src/features/*/screens/*.tsx`. Bare RN: `src/screens/` |
| **Navigation source** | Expo Router: the `app/` tree. Bare RN: `NavigationContainer` + `Stack.Navigator` config |
| **Log prefix** | `[AppName]` — used in `console.log()` |

---

## Phase 1: App Discovery

Run when `.tester/app-graph.yaml` does not exist, the navigation source has changed, or the
user says "rebuild the graph".

### 1.1 Read the navigation source

Find files defining all screens / routes:
- **NavigationStack / FlowStacks**: a `Screen` or `Route` enum with all cases
- **Coordinators**: `navigate(to:)` calls covering all destinations
- **UIKit**: router with `push` / `present` calls
- **Flutter / GoRouter**: files with `GoRoute` definitions or `context.go()` / `context.push()`
- **Flutter / Navigator**: `Navigator.push()` / `Navigator.pushNamed()` call sites
- **Expo Router**: the `app/` tree — each `.tsx` file is a route

### 1.2 Read every screen file

For each screen extract:
- Outgoing navigation calls (`push`, `present`, `NavigationLink`, `router.push(...)`, etc.) — these are edges
- `.onAppear` / `viewDidAppear` / `useEffect` / `initState` — where appearance logs go
- Primary action handlers — where tap logs go

### 1.3 Determine feature groupings

Group screens by directory structure, naming conventions, or functional area.

### 1.4 Write the graph

Create `.tester/app-graph.yaml` (screens + metadata). For each named flow create a separate
`.tester/flows/<flow-id>.yaml` using the kebab-case flow name (`create-game.yaml`,
`edit-profile.yaml`). See **Graph Schema** below.

---

## Phase 2: Instrumentation

The same naming convention is used across platforms — `<feature>_screen`,
`<intent>_button`, `<field>_input`, `<tab>_tab` — so flows can reference one identifier set.

### 2.1 SwiftUI / UIKit (iOS, macOS, tvOS)

**Screen root identifier:**
```swift
var body: some View {
    VStack { ... }
        .accessibilityIdentifier("game_list_screen")
        .onAppear {
            print("[AppName] [Feature] GameList appeared")
        }
}
```

**Action element + tap log:**
```swift
Button("Create Game") {
    print("[AppName] [Feature] createGame tapped")
    navigator.show(screen: .createGame(group))
}
.accessibilityIdentifier("primary_action_button")
```

### 2.2 Flutter

```dart
@override
void initState() {
  super.initState();
  print('[AppName] [Feature] GameList appeared');
}

Semantics(
  label: 'primary_action_button',
  child: GestureDetector(
    onTap: () {
      print('[AppName] [Feature] createGame tapped');
      context.go('/create-game');
    },
    child: ...,
  ),
)
```

> Flutter aggregates Semantics labels into the platform accessibility tree, which is what
> `agent-device snapshot` reads. Visible text and child descriptions are also surfaced.

### 2.3 Expo / React Native

Always set **both** `testID` and `accessibilityLabel` to the same `snake_case` value so the
identifier is visible to agent-device on both iOS and Android.

```tsx
useEffect(() => {
  console.log('[AppName] [Home] HomeScreen appeared');
}, []);

return (
  <SafeAreaView testID="home_screen" accessibilityLabel="home_screen">
    <Pressable
      testID="primary_action_button"
      accessibilityLabel="primary_action_button"
      onPress={() => {
        console.log('[AppName] [Home] primaryAction tapped');
        router.push('/listing/123');
      }}
    >
      <Text>Continue</Text>
    </Pressable>
  </SafeAreaView>
);
```

### 2.4 Naming conventions

- Screens: `<feature>_screen` — e.g. `home_screen`, `login_screen`
- Buttons: `<intent>_button` — e.g. `submit_button`, `chat_now_button`
- Text inputs: `<field>_input` — e.g. `phone_input`, `otp_input`
- Tab items: `<tab>_tab` — e.g. `home_tab`, `search_tab`

### 2.5 Build to verify

**iOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build
```

**macOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build
```

**tvOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=tvOS Simulator,name=<Device>' build
```

**Flutter (Android):**
```bash
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"
cd <flutter-project-dir>
~/fvm/versions/stable/bin/flutter run -d <device-serial> > /tmp/flutter.log 2>&1 &
# Subsequent edits: send SIGUSR1 to that flutter process for hot reload (preserves state)
# or SIGUSR2 for hot restart.
```

**Expo / React Native:**
```bash
# First-time iOS run — generates ios/, builds, launches sim
npx expo run:ios > /tmp/expo_ios.log 2>&1 &
# First-time Android run
npx expo run:android > /tmp/expo_android.log 2>&1 &
# JS-only iterations afterwards — keep Metro running:
npx expo start > /tmp/expo_metro.log 2>&1 &
# Force a full rebuild after a native dep change:
npx expo prebuild --clean && npx expo run:ios
```

---

## Phase 3: Flow Testing

A single agent-device-driven loop covers all platforms. The only platform-specific parts are
the **build / install** step (above) and any **system-alert** handling that runs in a separate
OS process (Sign in with Apple — see 3.6).

### 3.1 Load the graph

Read `.tester/app-graph.yaml` for screen data. Read flow files from `.tester/flows/` — target
by name or all files with `enabled: true`.

### 3.2 Pre-grant permissions (iOS)

agent-device drives in-app interaction; OS-level permission state is set before launch.

```bash
xcrun simctl privacy booted grant location   <bundle.id>
xcrun simctl privacy booted grant camera     <bundle.id>
xcrun simctl privacy booted grant contacts   <bundle.id>
xcrun simctl privacy booted grant photos     <bundle.id>
xcrun simctl privacy booted grant microphone <bundle.id>
# Or revoke to reset state:
xcrun simctl privacy booted revoke location  <bundle.id>
```

If a permission dialog still appears at runtime, snapshot it and tap the Allow button — see
3.6 [A].

### 3.3 Build, install, open

Build via the platform's normal toolchain (Phase 2.5), then start an agent-device session:

```bash
agent-device apps --platform <ios|macos|android>      # confirm the app is installed
agent-device open <bundle-id> --platform <ios|macos|android>
```

For first-run installs, agent-device's `install` / `install-from-source` / `reinstall` can
deploy a freshly built `.app` / `.apk` — check `agent-device help workflow` for syntax.

### 3.4 Drive each step

The default action loop, repeated per flow step:

```bash
# 1. Confirm current screen
agent-device snapshot -i                       # interactive elements with @e refs

# 2. Locate target element (any one of these)
#    - by label/text:    agent-device press --label "Create Game"
#    - by snapshot ref:  agent-device press @e3
#    - by id:            agent-device press --id primary_action_button
#    - by predicate:     agent-device find / get / is

# 3. Perform action
agent-device press --label "Create Game"
# or: fill, type, focus, scroll, long-press, back, home, rotate, app-switcher, …

# 4. Wait for transition (preferred over arbitrary sleeps)
agent-device wait <selector-or-predicate>

# 5. Confirm via app log (see "Log confirmation" below)
```

If a target only appears in the off-screen summary of a snapshot, run `agent-device scroll
<direction>` and re-snapshot until it's visible.

For exact selector syntax, predicates available to `find` / `get` / `is` / `wait`, and the
canonical action surface, run `agent-device help workflow`.

### 3.5 Log confirmation

Console logs from the app are how steps are confirmed PASSED — not screenshots. agent-device
captures them; the equivalent platform fallback works too.

| Platform | Where logs appear |
|---|---|
| iOS Swift `print()` | App stdout — capture by launching with `xcrun simctl launch --console-pty booted <bundle.id> > /tmp/app.log 2>&1 &` if running outside agent-device, or use `agent-device help debugging` for the in-session log API |
| iOS `os_log` / `Logger` | `xcrun simctl spawn booted log stream --predicate 'eventMessage CONTAINS "[AppName]"'` |
| macOS Swift `print()` | App stdout — launch the binary directly to capture |
| macOS `os_log` / `Logger` | `log stream --predicate 'eventMessage CONTAINS "[AppName]"'` |
| Flutter `print()` | `flutter run` stdout AND `adb logcat -s flutter` |
| Expo / RN `console.log` | Metro stdout, plus iOS unified log + `adb logcat -s ReactNativeJS:V` |

Then mark the step:

- **PASSED** if the expected log line appeared **or** the next screen's accessibility ID is
  visible in the next snapshot.
- **FAILED** → enter Phase 4 immediately (inline recovery). Resume the step after recovery.
  Only move on once the current step is confirmed PASSED.

### 3.6 System alerts

agent-device's snapshot surfaces dialogs that run **in-process**. Cross-process system sheets
(Sign in with Apple, the iOS account picker) are invisible to the accessibility API on the
simulator and require a different strategy.

#### Quick decision tree

```
System alert appeared?
 ├─ Permission dialog (location, camera, contacts, notifications)?
 │   → Pre-grant via simctl privacy before launch — see [A]
 │   → Or tap via agent-device if it still appears (visible in snapshot)
 ├─ ATT (App Tracking Transparency)?
 │   → Tap via agent-device — visible in snapshot — see [B]
 ├─ Sign in with Apple?
 │   → Cross-process — bypass via credential injection — see [C]
 └─ Unknown / other dialog?
     → agent-device snapshot — if visible, tap dismiss — see [D]
     → If not visible, it's cross-process — use credential injection — see [C]
```

Add recurring labels (`"Not Now"`, `"Ask App Not to Track"`, etc.) to `SYSTEM_PROMPT_DISMISS`
in `.env`, then wrap each `agent-device open` and each tap with a small dismiss sweep that
iterates the labels and calls `agent-device press --label "$label" || true`.

#### [A] Permission dialogs — pre-grant before launch (preferred)

Use `xcrun simctl privacy booted grant ...` from 3.2. Avoids the dialog entirely.

If the dialog still appears at runtime, it runs in-process and is visible to agent-device:

```bash
agent-device snapshot -i                   # locate Allow / Don't Allow buttons
agent-device press --label "Allow"
```

#### [B] ATT (App Tracking Transparency)

ATT runs **in-process** — `agent-device snapshot` sees it.

```bash
agent-device press --label "Ask App Not to Track"
```

Or add `"Ask App Not to Track"` to `SYSTEM_PROMPT_DISMISS`.

#### [C] Sign in with Apple — cross-process, use credential injection

The Apple sheet runs in `com.apple.AuthKitUIService` — a separate OS process invisible to any
accessibility-based driver including agent-device. Bypass it by injecting an email/password
session via launch arguments before normal auth runs.

**Step 1 — Create a test account (one-time)**

Use your auth backend's signup API to create a machine account
(e.g. `test-automation@yourapp.dev`). Do not use a real Apple ID or production account.

**Step 2 — Instrument the app**

```swift
// In your auth service's initialize() / setup() — before any auth state checks
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
        let userId = result.user.id
        print("[Auth] test sign-in succeeded — userId=\(userId)")

        try await setupAuthenticatedSession(userId: userId)
        return
    } catch {
        print("[Auth] test sign-in FAILED: \(error)")
    }
}
#endif
```

**Step 3 — Launch with credentials**

`SIMCTL_CHILD_` env vars are forwarded by simctl to the launched process:

```bash
SIMCTL_CHILD_TEST_EMAIL="test-automation@yourapp.dev" \
SIMCTL_CHILD_TEST_PASSWORD="YourTestPass123!" \
xcrun simctl launch --console-pty booted com.example.app \
  -UITestInjectSession
```

Then attach with `agent-device open` to drive the rest of the flow. Store credentials in
`.env`.

**Step 4 — Confirm injection worked**

Look for the success log line and check that the next snapshot shows the authenticated screen
(its `home_screen` / `<feature>_screen` ID), not the login screen.

#### [D] Unknown in-process dialog — general dismiss pattern

When an unexpected dialog blocks a step and `agent-device snapshot -i` shows it:

```bash
agent-device snapshot -i                   # find the dismiss-button label
agent-device press --label "<button label>"
```

Add the label to `SYSTEM_PROMPT_DISMISS` so the dismiss sweep handles it on subsequent runs.

> **Example — "Apple Account Verification" dialog** (simulator Apple ID re-verification):
> Text: *"Enter the password for \<email\> in Settings."* — Buttons: **Not Now**, **Settings**.
> In-process and visible to agent-device. Dismiss before interacting with Sign in with Apple,
> otherwise taps land on the dialog instead.
> `agent-device press --label "Not Now"`

### 3.7 Google Sign In on Android

The Google account picker on Android shows a native sheet that's in the same accessibility
tree as the app — `agent-device snapshot` can see it.

1. Tap the "Sign in with Google" button.
2. `agent-device wait --label "<test-account-email>"` (or just snapshot until visible).
3. `agent-device press --label "test@gmail.com"`.
4. Confirm auth success via the app log.

For fully automated flows, prefer credential injection in Dart (same shape as Apple's, via
`--dart-define`):

```dart
// In AuthService.init() — before any auth state check
if (const bool.fromEnvironment('INJECT_AUTH')) {
  final email = const String.fromEnvironment('TEST_EMAIL');
  final password = const String.fromEnvironment('TEST_PASSWORD');
  await signInWithEmailAndPassword(email, password);
  return;
}
```

Launch with:

```bash
~/fvm/versions/stable/bin/flutter run -d <serial> \
  --dart-define=INJECT_AUTH=true \
  --dart-define=TEST_EMAIL=test@example.com \
  --dart-define=TEST_PASSWORD=secret123
```

### 3.8 Close the session and report

```bash
agent-device close
```

```text
Flow: Create Game  Status: PASSED ✓
  Step 1  main → gameList       PASSED   log: [Scoreboard] [Game] GameList appeared
  Step 2  gameList → createGame PASSED   log: [Scoreboard] [Game] GameCreate appeared
```

---

## Phase 4: Inline Recovery (Step Failure)

Triggered immediately when a step fails during Phase 3. The goal is always to **recover and
continue the flow** — not just record the failure. Only mark the flow `FAILED` if recovery is
impossible.

### 4.1 Capture current state

```bash
agent-device screenshot /tmp/flow_failure_step<N>.png
agent-device snapshot --verbose > /tmp/flow_failure_step<N>.snapshot.txt
```

Read both together to understand exactly what's on screen.

### 4.2 Diagnose: app bug vs test infra issue

Classify the failure before acting — the recovery path differs.

| Symptom | Type | Likely cause | Recovery path |
|---|---|---|---|
| Element not found by ID/label | Test infra | Identifier missing or mismatched | → 4.4 |
| No log line appeared | Test infra | `print()` / `console.log` absent | → 4.4 |
| Wrong identifier in graph | Test infra | Graph out of sync with source | → 4.4 |
| Auth/login screen shown | Test infra | Missing credentials / session | Supply credentials; log in; resume |
| Tap succeeds but wrong screen appears | **App bug** | Navigation logic routes incorrectly | → 4.3 |
| Tap succeeds but no transition happens | **App bug** | Guard condition blocks nav, or handler missing | → 4.3 |
| Button not visible when it should be | **App bug** | Conditional render logic incorrect | → 4.3 |
| Crash / blank screen | **App bug** | Runtime error in source | → 4.3 |
| `agent-device open` fails or app exits immediately | **App bug** | App crashed at launch | → 4.3 |
| Same screen stays visible | Either | Button disabled by guard, OR press missed element | Check source; if guard logic wrong → 4.3; if ID wrong → 4.4 |
| Unexpected screen shown | Either | Navigation logic changed, OR graph stale | Re-read nav source; update graph if stale; if logic wrong → 4.3 |

> **Rule of thumb:** if the app ran the code but produced the wrong result, it's an app bug.
> If the test couldn't drive the app correctly (wrong ID, missing log, wrong credentials),
> it's a test infra issue.

### 4.3 App Bug Fix Loop

Loop until the step PASSES or is declared unresolvable.

#### Step A — Identify the buggy file

From the graph node's source file pointer (`swiftFile` / `dartFile` / `tsxFile`), the related
view-model, or the crash log, identify which file contains the defect.

```bash
# Recent crash or error in logs
grep -E "error|crash|fatal|Exception" /tmp/app.log | tail -20
# or read the screen source directly via Read
```

#### Step B — Fix the bug

Apply a targeted fix. Common patterns:

| Bug pattern | What to look for |
|---|---|
| Wrong screen navigated to | Navigation call has wrong route / case / params |
| Navigation never fires | Missing call in action handler, or async work not awaited |
| Button not shown | `if` / `guard` condition using wrong state variable |
| Crash on tap | Force-unwrap / null deref / index out of bounds / missing guard |
| State not updated | Observable property not mutated before navigation |

Edit the source. Keep changes minimal and targeted.

#### Step C — Rebuild and reattach

Rebuild via the platform's normal toolchain (Phase 2.5), then re-open the agent-device
session. For Flutter, prefer hot reload (SIGUSR1) over a full rebuild when state preservation
is acceptable; use hot restart (SIGUSR2) for routing/state changes.

If the build fails — read the error, fix it, and rebuild before continuing.

#### Step D — Re-navigate to the failing step

Drive from the launch screen back to the step that previously failed. Use the flow's steps
list as your guide — re-execute each prior step in order via the agent-device loop.

#### Step E — Retry the failing step

1. Confirm you're on the correct screen (snapshot ID or log).
2. Perform the action.
3. Confirm the transition (log line or snapshot ID).

**If PASSED** → continue the flow from the next step. Record the fix in the graph (4.7).

**If still FAILED** → diagnose again from Step A. The fix may have been incomplete or
revealed a second bug.

#### When to stop looping

Declare the step **unresolvable** (→ 4.8) only when:
- Root cause requires infrastructure changes outside the app code (backend down, missing
  test data that can't be created programmatically).
- The fix requires significant feature work that can't be done inline.
- Three full fix-and-retry cycles have failed with no progress.

### 4.4 Fix missing instrumentation (test infra)

Open the screen's source file from the graph node:

- Is the screen-root identifier present and matching the graph's `accessibilityId`?
- Is the appearance log in `.onAppear` / `useEffect` / `initState`?
- Is the tap log before the navigation call?
- Did the navigation call change (different screen, different transition)?

Add or correct as needed (Phase 2 patterns), then rebuild and reattach (4.3 Step C).

### 4.5 Find a way to the next step

Even if the recorded identifier can't be matched, try to reach `toScreen` another way:

1. `agent-device snapshot --verbose` — list everything currently on screen.
2. Look for the target action by visible label: `press --label "<ButtonLabel>"`.
3. If the screen layout changed, trace the new path in source and use it.
4. If an interstitial screen (login, onboarding, permission) is blocking, handle it and
   continue.

### 4.6 Retry the step

After fixing, re-attempt:
1. Confirm current screen.
2. Press / fill / scroll.
3. Confirm transition.

If PASSED → continue from the next step.

### 4.7 Update the graph with what was learned

```yaml
# .tester/app-graph.yaml — corrected node
accessibilityId: corrected_screen_id
transitions:
  - action: updated_action_name
    actionAccessibilityId: corrected_button_id
    nextScreen: actualNextScreen
    logConfirmation: "[AppName] [Feature] ActualScreen appeared"
```

Update `updatedAt` to the current ISO-8601 timestamp. If `lastResult` changes, update it in
the relevant `.tester/flows/<flow-id>.yaml`.

### 4.8 If recovery fails

- Set `lastResult: FAILED` on the flow.
- Set `failureNote` describing exactly which step failed, the root cause, and why it's
  unresolvable inline.
- Continue testing remaining flows — don't abort the full run.
- On next run, Phase 0 will flag this flow as requiring re-test after fixes.

---

## Graph Schema

### `.tester/app-graph.yaml` — app metadata + screens

```yaml
version: 1
updatedAt: "2024-01-15T10:30:00Z"
appName: YourAppName
bundleId: com.example.yourapp
platform: ios            # ios | macos | tvos | android
projectRoot: /absolute/path/to/project
navSourceFiles:
  # iOS / macOS / tvOS: Swift navigator files
  - relative/path/to/Navigator+Screen.swift
  # Flutter / Android: GoRouter config or routing files
  # - flutter/lib/config/router/app_router.dart
  # Expo Router: the app/ directory tree
  # - app/

screens:
  gameList:
    screenId: gameList
    displayName: Game List
    feature: Game
    # One of:
    swiftFile: relative/path/GameListView.swift
    # dartFile: flutter/lib/features/game/screens/game_list_screen.dart
    # tsxFile: app/game/index.tsx
    accessibilityId: game_list_screen
    notes: optional
    transitions:
      - action: create_game_button
        actionAccessibilityId: primary_action_button
        nextScreen: createGame
        transition: presentCover    # iOS: push/presentCover/etc; Flutter: go/push/pushNamed
        logConfirmation: "[AppName] [Feature] CreateGame appeared"
```

### `.tester/flows/<flow-id>.yaml` — one file per named flow

Filename is the kebab-case flow ID (`create-game.yaml`, `edit-profile.yaml`).

```yaml
name: Human readable name
description: What this flow validates
enabled: true
lastResult: PASSED          # PASSED | FAILED | UNKNOWN
failureNote: null
steps:
  - stepId: 1
    fromScreen: gameList
    toScreen: createGame
    action: primary_action_button   # accessibilityId, or null for auto/programmatic transitions
    logConfirmation: "[AppName] [Feature] CreateGame appeared"
    prerequisites:
      - plain-English required state
```

**Field notes:**

- `platform` — `ios`, `macos`, `tvos`, or `android`; drives the build/install commands and
  any cross-process alert handling. UI driving is the same agent-device loop on all of them.
- `accessibilityId` — set in source via `.accessibilityIdentifier()` (Swift), `Semantics(label:)`
  (Flutter), or `testID` + `accessibilityLabel` (RN). Surfaced in `agent-device snapshot`.
- `swiftFile` / `dartFile` / `tsxFile` — the screen's source file.
- `action` — `null` / `auto_on_*` for programmatic transitions; otherwise the identifier or
  visible label that agent-device should target.
- `logConfirmation` — exact prefix to grep in console / Metro / logcat output.

---

## Phase 0: Graph Staleness Check

Run before Phase 3 every time. Determines whether to trust the existing graph or rebuild it
first.

### 0.1 Check if graph exists

If `.tester/app-graph.yaml` is missing → run Phase 1 now, then Phase 2, then Phase 3.

### 0.2 Compare navigation source against graph

Read the graph's `updatedAt` and `navSourceFiles`. For each listed file, check its
last-modified time:

```bash
git log -1 --format="%ai" -- <navSourceFile>
```

If **any** nav source file was modified after `updatedAt` → the graph is stale.

### 0.3 Stale graph — what to do

| Change severity | Action |
|---|---|
| Nav source file(s) modified | Re-run Phase 1, then Phase 2 for any new/changed screens |
| Screen file(s) modified (no nav changes) | Re-run Phase 2 for those files only; update `updatedAt` |
| Graph missing `navSourceFiles` | Treat as stale; run Phase 1 |

After Phase 1 runs, diff old screens against new:

- **New screenId** → add node + transitions; mark any flows touching it as `lastResult: UNKNOWN`.
- **Removed screenId** → remove node; mark affected flows as `lastResult: UNKNOWN` with
  `failureNote: "screen removed"`.
- **Changed transitions** → update edges; mark affected flows as `lastResult: UNKNOWN`.
- **No diff** → graph is current; proceed to Phase 3 directly.

### 0.4 Mark stale flows before testing

Any flow with `lastResult: UNKNOWN` must be re-tested. Flows still `PASSED` that touch no
changed screens can be skipped or re-run for confidence.

---

## When to Update the Graph

- Before every test run: run Phase 0 to detect nav source drift automatically.
- New screen added to navigation source → Phase 1 rebuild.
- Navigation call added, removed, or transition type changed → Phase 1 rebuild.
- Accessibility ID changed in source → update node's `accessibilityId`, re-instrument.
- Flow prerequisite changes (permission gate, auth requirement) → update `prerequisites` in
  affected steps.
- Phase 4 identifies a failure root cause → targeted edge/node fix + set
  `lastResult: FAILED`, then re-run to confirm.

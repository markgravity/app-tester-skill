---
name: app-tester
description: >
  Build and maintain a navigable graph of any iOS, macOS, or Android app's screens. Reads the
  project's navigation source to understand flows, instruments screen files with structured print
  logs and accessibility identifiers, then drives flows end-to-end using console logs and the
  accessibility tree — without requiring screenshots.
  Use when: (1) user says "test this", "test it", "test [feature/screen/flow]",
  "test the [flow] flow", "test all flows", "instrument screens", "update the flow graph",
  "rebuild the graph", "run flow tests", or "check that [feature] works end to end",
  (2) after adding or modifying screens or navigation logic,
  (3) when debugging a broken navigation flow. Works on iOS simulator, macOS, and Android emulator/device.
  For Flutter Android apps: uses ADB + uiautomator for UI inspection, flutter run + SIGUSR1 for hot reload.
  For Expo / React Native apps: uses AXe on iOS and ADB + uiautomator on Android for UI inspection,
  with `console.log` + Metro logs for confirmation and `testID` / `accessibilityLabel` for instrumentation.
---

# App Tester

Tests iOS, macOS, and Android app navigation flows without relying on screenshots. Works on SwiftUI, UIKit, Flutter, and Expo / React Native projects.

**Strategy:**
1. Read the project's navigation source to build `.tester/app-graph.yaml` and `.tester/flows/*.yaml` at the project root.
2. Instrument screen files with structured `print` logs and accessibility identifiers.
3. Drive flows by tapping elements and confirming transitions via console logs.
4. Take screenshots **only when a step fails**.

**Bundled scripts:**
```
~/.claude/skills/app-tester/scripts/
  iOS:
    ios.py                — unified entry point: tap, swipe, screenshot, logs
    app_launcher.py       — launch/terminate via xcrun simctl
    screen_mapper.py      — read accessibility tree via idb
    navigator.py          — tap/interact via idb (used by ios.py)
    log_monitor.py        — stream simulator logs
    privacy_manager.py    — pre-grant permissions
    dismiss_prompts.py    — dismiss system dialogs
    common/               — shared idb/simctl utils

  macOS:
    macos_launcher.py     — launch/terminate macOS .app bundles
    macos_screen_mapper.py — read window/toolbar elements via System Events
    macos_navigator.py    — click toolbar/window elements via System Events
    macos_log_monitor.py  — stream app logs via `log stream`

  Android:
    android.py            — unified entry point: tap, swipe, screenshot, logs, hot-reload
    android_launcher.py   — launch/terminate/install via ADB; flutter run management
    android_screen_mapper.py — read UI tree via adb uiautomator dump
    android_log_monitor.py — stream adb logcat
```

**Requirements:**
- iOS: `axe` for accessibility tree + taps, `xcrun simctl` for launch + logs.
  Install: `brew tap cameroncooke/axe && brew install axe`
- macOS: `osascript` (built-in) for accessibility, `log` (built-in) for logs. No extra deps.
- Android: `adb` (Android SDK platform-tools). Ensure `$HOME/Library/Android/sdk/platform-tools` is on PATH.
  Flutter apps: `~/fvm/versions/stable/bin/flutter` (or `flutter` on PATH).

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

**iOS / macOS (SwiftUI/UIKit):**

| Value | How to find it |
|---|---|
| **Platform** | `SUPPORTED_PLATFORMS` in build settings — `macosx` = macOS, `iphonesimulator` = iOS |
| **Bundle ID** | `PRODUCT_BUNDLE_IDENTIFIER` in build settings or Info.plist |
| **App name** | `CFBundleDisplayName` / `CFBundleName` in Info.plist or the Xcode scheme name |
| **Screen files** | Directory containing `*View.swift` or `*ViewController.swift` |
| **Navigation source** | File with Screen/Route enum or coordinator |
| **Log prefix** | `[AppName]` — used in all instrumentation |

**Android / Flutter:**

| Value | How to find it |
|---|---|
| **Platform** | Presence of `android/` directory; Flutter = `pubspec.yaml` present |
| **Package ID** | `applicationId` in `android/app/build.gradle` or `build.gradle.kts` |
| **App name** | `CFBundleDisplayName` in iOS `Info.plist` or `android:label` in `AndroidManifest.xml` |
| **Screen files** | Flutter: `lib/features/*/screens/` or `lib/screens/` — `*Screen.dart` or `*Page.dart` |
| **Navigation source** | Flutter: GoRouter config file, or files with `GoRoute`/`Navigator.push` calls |
| **Device serial** | `adb devices` — use emulator serial (e.g. `emulator-5554`) |
| **Log prefix** | `[AppName]` — used in `print()` calls throughout Flutter code |

**Expo / React Native (iOS + Android):**

Identify by `package.json` containing `expo` or `react-native` dependency. Expo Router projects also have an `app/` directory with file-based routes.

| Value | How to find it |
|---|---|
| **Platform** | `package.json` has `expo` → Expo. `react-native` only → bare RN. Both iOS and Android are typically supported |
| **Bundle ID (iOS)** | `app.json` → `expo.ios.bundleIdentifier`, or `ios/<App>/Info.plist` for prebuild projects |
| **Package ID (Android)** | `app.json` → `expo.android.package`, or `android/app/build.gradle` `applicationId` |
| **App name** | `app.json` → `expo.name`, or `app.config.{js,ts}` |
| **Router type** | `app/` directory exists → **Expo Router** (file-based). Otherwise look for `@react-navigation/*` config |
| **Screen files** | Expo Router: `app/**/*.tsx` (route files) and `src/features/*/screens/*.tsx` (feature screens). Bare RN: `src/screens/`, `screens/` |
| **Navigation source** | Expo Router: the `app/` tree IS the route graph (each `.tsx` file = a route). Bare RN: the `NavigationContainer` + `Stack.Navigator` config file |
| **Log prefix** | `[AppName]` — used in `console.log()` calls (visible in Metro / `npx expo start` console and via `xcrun simctl spawn booted log stream` on iOS / `adb logcat` on Android) |

---

## Phase 1: App Discovery

Run when `.tester/app-graph.yaml` does not exist, the navigation source has changed, or the user says "rebuild the graph".

### 1.1 Read the navigation source

Find files defining all screens/routes:
- **NavigationStack / FlowStacks**: A `Screen` or `Route` enum with all cases
- **Coordinators**: `navigate(to:)` calls covering all destinations
- **UIKit**: Router with `push`/`present` calls
- **Flutter/GoRouter**: Files with `GoRoute` definitions or `context.go()`/`context.push()` calls
- **Flutter/Navigator**: `Navigator.push()`/`Navigator.pushNamed()` call sites

### 1.2 Read every screen file

For each screen extract:
- Outgoing navigation calls (`push`, `present`, `NavigationLink`, etc.) — these are edges
- `.onAppear` / `viewDidAppear` — where appearance logs go
- Primary action closures — where tap logs go

### 1.3 Determine feature groupings

Group screens by directory structure, naming conventions, or functional area.

### 1.4 Write the graph

Create `.tester/app-graph.yaml` at the project root (screens + metadata). For each named flow, create a separate `.tester/flows/<flow-id>.yaml` file using the kebab-case flow name (e.g. `create-game.yaml`, `edit-profile.yaml`). See **Graph Schema** below.

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

### 2.5 Flutter instrumentation (Android)

Flutter apps use `print()` for log confirmation and `Semantics` widgets for UI identification.

**Screen appearance logs** — add to each screen's `initState` or `build`:
```dart
@override
void initState() {
  super.initState();
  print('[AppName] [Feature] ScreenName appeared');
}
```

**Button tap logs** — add before navigation calls:
```dart
GestureDetector(
  onTap: () {
    print('[AppName] [Feature] primaryButton tapped');
    context.go('/next-screen');
  },
  child: ...,
)
```

**Semantic labels** for UI identification (used by `android_screen_mapper.py --find`):
```dart
Semantics(
  label: 'sign_in_google_button',
  child: GestureDetector(onTap: ..., child: ...),
)
```

> Flutter's content-desc in ADB uiautomator dump aggregates all Semantics labels in the widget tree. If a widget has no explicit `Semantics`, its visible text and child descriptions are used automatically.

### 2.6 Expo / React Native instrumentation (iOS + Android)

React Native apps use `console.log()` for log confirmation and `testID` + `accessibilityLabel` props for UI identification. The same instrumentation works on both iOS and Android — `testID` becomes `accessibilityIdentifier` on iOS and `resource-id` (last segment) / `content-desc` on Android.

**Screen appearance logs** — add a `useEffect` in each screen component:

```tsx
import { useEffect } from 'react';

export default function HomeScreen() {
  useEffect(() => {
    console.log('[GameCu] [Home] HomeScreen appeared');
  }, []);
  // ...
}
```

**Screen root identifier** — wrap the outermost return value:

```tsx
return (
  <SafeAreaView testID="home_screen" accessibilityLabel="home_screen">
    {/* ... */}
  </SafeAreaView>
);
```

> Always set **both** `testID` and `accessibilityLabel` to the same `snake_case` value — `testID` is iOS-only on some component variants, while Android's uiautomator reads `accessibilityLabel` via content-desc. Pairing them gives you one identifier that works across both platforms.

**Action tap logs** — add inside the `onPress` handler:

```tsx
<Pressable
  testID="primary_action_button"
  accessibilityLabel="primary_action_button"
  onPress={() => {
    console.log('[GameCu] [Home] primaryAction tapped');
    router.push('/listing/123');
  }}
>
  <Text>Continue</Text>
</Pressable>
```

**Naming conventions** (mirror the iOS section):
- Screens: `<feature>_screen` — e.g. `home_screen`, `login_screen`, `listing_detail_screen`
- Buttons: `<intent>_button` — e.g. `submit_button`, `chat_now_button`, `buy_now_button`
- Text inputs: `<field>_input` — e.g. `phone_input`, `otp_input`, `price_input`
- Tab items: `<tab>_tab` — e.g. `home_tab`, `search_tab`

**Reading logs** — Metro/Expo writes `console.log` to its own console plus the device system log:
- iOS Simulator: `xcrun simctl spawn booted log stream --predicate 'eventMessage CONTAINS "[GameCu]"'`
- Android emulator: `adb logcat -s ReactNativeJS:V | grep '\[GameCu\]'`
- Or directly from the Metro terminal where `npx expo start` is running.

### 2.7 Build to verify

**iOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build
```

**macOS:**
```bash
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build
```

**Android / Flutter:**
```bash
# Hot reload if flutter run is already active (fastest)
python3 ~/.claude/skills/app-tester/scripts/android.py hot-reload

# Full rebuild + deploy
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"
cd <flutter-project-dir>
~/fvm/versions/stable/bin/flutter run -d <device-serial> > /tmp/flutter_android.log 2>&1 &
```

**Expo / React Native:**

Most code changes (screens, stores, components) hot-reload automatically through Metro — no manual rebuild needed. A native rebuild is only required when adding/removing native modules, changing `app.json` plugins, or modifying iOS/Android folders directly.

```bash
# First-time iOS run — generates ios/ folder + builds + launches simulator
cd <expo-project>
npx expo run:ios > /tmp/expo_ios.log 2>&1 &

# First-time Android run — generates android/ folder + builds + launches emulator
npx expo run:android > /tmp/expo_android.log 2>&1 &

# Subsequent JS-only iterations — just keep Metro running:
npx expo start > /tmp/expo_metro.log 2>&1 &

# Force a full rebuild after a native dep change:
npx expo prebuild --clean && npx expo run:ios
```

> If `expo run:ios` fails with `xcrun simctl` errors, ensure `xcode-select -p` points to a full Xcode install (not just CLT). For SDK 52+, also confirm the `newArchEnabled: true` flag in `app.json` matches the device's RN architecture.

---

## Phase 3: Flow Testing (iOS)

> **Requirements:** `axe` + `xcrun simctl`

### 3.1 Load the graph

Read `.tester/app-graph.yaml` for screen data. Read flow files from `.tester/flows/` — target by name or all files with `enabled: true`.

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

1. Run `axe describe-ui --udid <udid>` and check if the dialog's buttons appear in the output.
2. **If visible** — it runs in-process. Tap the dismiss button by coordinate (see [D]).
3. **If not visible** — it runs in a separate OS process (e.g. `com.apple.AuthKitUIService`). AXe cannot interact with it; use credential injection to bypass the flow entirely (see [C]).

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

If a permission dialog still appears at runtime, find and tap its button via AXe (these run in-process):
```bash
axe describe-ui --udid <udid> | python3 -c "
import json, sys
data = json.load(sys.stdin)
nodes = data if isinstance(data, list) else [data]
def walk(n):
    if n.get('AXLabel','') in ('Allow','Allow Once',\"Don't Allow\",'OK'):
        print(n['AXLabel'], n.get('frame'))
    for c in n.get('children', []): walk(c)
for n in nodes: walk(n)
"
# Then tap the button's center coordinate:
axe tap -x <x> -y <y> --udid <udid>
```

---

#### [B] ATT (App Tracking Transparency) — tap via AXe

ATT runs **in-process** — `axe describe-ui` can see it. It will appear as 4–5 nodes with no `AXUniqueId`.

Detection and tap pattern:
```bash
# Tap the ATT dismiss button directly by label
axe tap --label "Ask App Not to Track" --udid <udid>
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

**Step 1 — Identify the dismiss button:**

```bash
axe describe-ui --udid <udid>
# Review the JSON to find the button label
```

**Step 2 — Tap the dismiss button by label:**

```bash
axe tap --label "<button label>" --udid <udid>
# Or by coordinate if label is ambiguous:
axe tap -x <cx> -y <cy> --udid <udid>
```

**Step 3 — Add to `SYSTEM_PROMPT_DISMISS` so it's handled automatically:**

```bash
# .env
SYSTEM_PROMPT_DISMISS=Not Now,Ask App Not to Track,Don't Allow,Allow Once,OK,Allow
```

`dismiss_prompts.py` runs after every launch and tap and dismisses any button whose label matches.

> **Example — "Apple Account Verification" dialog** (simulator Apple ID re-verification):
> Text: *"Enter the password for \<email\> in Settings."* — Buttons: **Not Now**, **Settings**.
> This is in-process and AXe-visible. Dismiss before interacting with the Sign in with Apple sheet, otherwise taps land on the dialog instead.
> `axe tap --label "Not Now" --udid <udid>` (or by coord: `axe tap -x 127 -y 507 --udid <udid>`)

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
python3 ~/.claude/skills/app-tester/scripts/ios.py tap --id "primary_action_button"
```

**Tap by label (fuzzy):**
```bash
python3 ~/.claude/skills/app-tester/scripts/ios.py tap --text "Create Game"
```

**Swipe:**
```bash
python3 ~/.claude/skills/app-tester/scripts/ios.py swipe --from 195,700 --to 195,200
```

**Screenshot on failure:**
```bash
python3 ~/.claude/skills/app-tester/scripts/ios.py screenshot --size half
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

Same as iOS — read `.tester/app-graph.yaml` and flow files from `.tester/flows/`.

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

## Phase 3 (Android / Flutter): Flow Testing

> **Requirements:** `adb` on PATH. Flutter apps: `~/fvm/versions/stable/bin/flutter` or `flutter` on PATH.
>
> **PATH setup:** `export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"`

### 3.1 Load the graph

Same as iOS — read `.tester/app-graph.yaml` and flow files from `.tester/flows/`.

### 3.2 Deploy the app

**If `flutter run` is not already running** — start it in the background:
```bash
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"
cd <flutter-project-dir>
~/fvm/versions/stable/bin/flutter run -d <serial> > /tmp/flutter_android.log 2>&1 &
FLUTTER_PID=$!
echo "Flutter PID: $FLUTTER_PID"

# Wait for ready signal in log
until grep -q "Syncing files\|Flutter run key\|is available at" /tmp/flutter_android.log 2>/dev/null; do sleep 2; done
echo "App ready"
```

**If `flutter run` is already active** — hot reload after code changes:
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py hot-reload
# Or with explicit PID:
python3 ~/.claude/skills/app-tester/scripts/android.py hot-reload --pid $FLUTTER_PID
```

> **Hot reload vs hot restart:** SIGUSR1 = hot reload (preserves state, fast). SIGUSR2 = hot restart (resets state). Use hot reload for UI-only changes; hot restart for state/logic changes.

### 3.3 Confirm UI loaded

```bash
python3 ~/.claude/skills/app-tester/scripts/android_screen_mapper.py
```

Expected: list of interactive elements on the current screen. If empty, the screen may be all-Semantics Flutter widgets — use `--find` to search by text.

### 3.4 Navigate each step

**Find elements by text/content-desc:**
```bash
python3 ~/.claude/skills/app-tester/scripts/android_screen_mapper.py --find "Sign in"
```

**Tap by text (fuzzy):**
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py tap --text "Sign in with Google"
```

**Tap by resource-id:**
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py tap --id "submit_button"
```

**Tap by coordinate:**
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py tap --coord 540,1900
```

**Swipe:**
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py swipe --from 540,1400 --to 540,400
```

**Screenshot on failure:**
```bash
python3 ~/.claude/skills/app-tester/scripts/android.py screenshot --output .tester/screenshots/
```

**Confirm via log (Flutter print statements → logcat):**
```bash
python3 ~/.claude/skills/app-tester/scripts/android_log_monitor.py \
  --duration 5s --tag flutter --filter "[AppName]"
# Or from the flutter_android.log file:
grep "\[AppName\]" /tmp/flutter_android.log | tail -10
```

> **Flutter log routing:** Flutter `print()` output appears in both the `flutter run` stdout log file AND `adb logcat` under the `flutter` tag. Prefer grepping the log file if `flutter run` is active; use logcat when only the APK is installed.

**Mark step:** PASSED if log confirmed or element found. FAILED → enter Phase 4 immediately.

### 3.5 Google Sign In on Android

Sign In with Google on Android shows a native account picker sheet. ADB uiautomator **can** see this sheet since it runs in the same process space as the app (unlike Apple's cross-process sheet on iOS).

To handle it in flows:
1. Tap the "Sign in with Google" button
2. Wait 1–2s for the picker to appear
3. Tap the target account by its visible email text:
   ```bash
   python3 ~/.claude/skills/app-tester/scripts/android.py tap --text "test@gmail.com"
   ```
4. Confirm auth success via log

For automated flows without user interaction, use email/password auth injection instead (same pattern as iOS credential injection in Section 3.2c[C], but in Dart):

```dart
// In AuthService.init() or similar — before auth state check
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

### 3.6 Report

```
Flow: Auth — Sign in with Google  Status: PASSED ✓
  Step 1  launch → authScreen   PASSED   desc: "Sign in with Google" found in UI tree
  Step 2  authScreen → main      PASSED   log: [Scoreboard] [Auth] AuthScreen appeared
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

### 4.2 Diagnose: app bug vs test infra issue

Classify the failure before acting — the recovery path differs.

| Symptom | Type | Likely cause | Recovery path |
|---|---|---|---|
| Element not found by ID | Test infra | Accessibility ID missing or mismatched | → Section 4.4 |
| No log line appeared | Test infra | `print()` statement absent | → Section 4.4 |
| Wrong accessibility ID in graph | Test infra | Graph out of sync with source | → Section 4.4 |
| Auth/login screen shown | Test infra | Missing credentials / session | Supply credentials; log in; resume |
| Tap succeeds but wrong screen appears | **App bug** | Navigation logic routes incorrectly | → Section 4.3 |
| Tap succeeds but no transition happens | **App bug** | Guard condition blocks nav, or handler missing | → Section 4.3 |
| Button not visible when it should be | **App bug** | Conditional render logic incorrect | → Section 4.3 |
| Crash / blank screen | **App bug** | Runtime error in Swift source | → Section 4.3 |
| `not running` from screen_mapper | **App bug** | App crashed at launch or during step | → Section 4.3 |
| Same screen stays visible | Either | Button disabled by guard, OR tap missed element | Check source; if guard logic wrong → 4.3; if ID wrong → 4.4 |
| Unexpected screen shown | Either | Navigation logic changed, OR graph stale | Re-read nav source; update graph if stale; if logic wrong → 4.3 |

> **Rule of thumb:** If the app ran the code but produced the wrong result, it's an app bug. If the test couldn't drive the app correctly (wrong ID, missing log, wrong credentials), it's a test infra issue.

---

### 4.3 App Bug Fix Loop

Use when the failure is an **app bug** — incorrect Swift logic, not a test setup problem.

**Loop until the step PASSES or is declared unresolvable:**

#### Step A — Identify the buggy file

From the graph node's `swiftFile`, the related ViewModel, or the crash log, identify which Swift file(s) contain the defect. Read them:

```bash
# Check recent crash or error in logs
grep -E "error|crash|fatal|Exception" /tmp/app_logs.txt | tail -20

# Or read the screen source directly
# Use the Read tool on the swiftFile path from the graph node
```

#### Step B — Fix the bug

Read the Swift source and apply a targeted fix. Common bug patterns:

| Bug pattern | What to look for |
|---|---|
| Wrong screen navigated to | Navigation call has wrong `Screen` case or params |
| Navigation never fires | Missing call in action closure, or async `Task {}` not awaited |
| Button not shown | `if`/`guard` condition using wrong state variable |
| Crash on tap | Force-unwrap (`!`) on nil, index out of bounds, or missing guard |
| State not updated | `@Observable` property not mutated before navigation |

Fix the source using the Edit tool. Keep changes minimal and targeted.

#### Step C — Rebuild and reinstall

```bash
# iOS
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' build 2>&1 | tail -20

APP_PATH=$(xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>' \
  -showBuildSettings 2>/dev/null | grep ' CODESIGNING_FOLDER_PATH' | awk '{print $3}')

xcrun simctl terminate booted <bundle.id> 2>/dev/null; sleep 1
xcrun simctl install booted "$APP_PATH"
xcrun simctl launch --console-pty booted <bundle.id> > /tmp/app_logs.txt 2>&1 &

# macOS
xcodebuild -scheme <Scheme> -destination 'platform=macOS' build 2>&1 | tail -20
osascript -e 'tell application "<AppName>" to quit' 2>/dev/null; sleep 1
python3 ~/.claude/skills/app-tester/scripts/macos_launcher.py --launch "$APP_PATH" --capture-stdout /tmp/macos_logs.txt
```

If the build fails — read the error, fix it, and rebuild before continuing.

#### Step D — Re-navigate to the failing step

Navigate from the app's launch screen back to the step that previously failed. Use the flow's steps list as your guide — re-execute each prior step in order.

#### Step E — Retry the failing step

Attempt the exact action that failed:
1. Confirm you're on the correct screen (accessibility ID or log)
2. Perform the tap/action
3. Confirm the transition (log line or screen ID)

**If PASSED** → continue the flow from the next step. Record the fix in the graph (see 4.7).

**If still FAILED** → diagnose again from Step A. The fix may have been incomplete or revealed a second bug. Loop back and repeat.

#### When to stop looping

Declare the step **unresolvable** (→ Section 4.8) only when:
- The root cause requires infrastructure changes outside the app code (e.g. backend not running, missing test data that can't be created programmatically)
- The fix requires significant feature work that can't be done inline
- Three full fix-and-retry cycles have failed with no progress

---

### 4.4 Fix Missing Instrumentation (Test Infra)

Use when the failure is a **test infra issue** — missing accessibility ID, missing log, or wrong ID in graph.

Open the screen's `swiftFile` from the graph node:
- Is `.accessibilityIdentifier()` present and matching the graph's `accessibilityId`?
- Is the `print("[AppName] [Feature] ScreenName appeared")` in `.onAppear`?
- Is the tap log before the navigation call?
- Did the navigation call change (different screen, different transition)?

If accessibility ID or log is absent or wrong, add/correct it:

```swift
// Add to outermost container
.accessibilityIdentifier("screen_name_screen")

// Add to .onAppear
print("[AppName] [Feature] ScreenName appeared")

// Add before navigation call
print("[AppName] [Feature] actionName tapped")
```

Then rebuild and reinstall (same commands as Section 4.3 Step C).

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

```yaml
# Updated node (example) — edit .tester/app-graph.yaml
accessibilityId: corrected_screen_id
transitions:
  - action: updated_action_name
    actionAccessibilityId: corrected_button_id
    nextScreen: actualNextScreen
    logConfirmation: "[AppName] [Feature] ActualScreen appeared"
```

Also update `updatedAt` in `.tester/app-graph.yaml` to the current ISO-8601 timestamp.
If `lastResult` changes, update it in the relevant `.tester/flows/<flow-id>.yaml`.

### 4.8 If recovery fails

If the flow cannot be unblocked after all recovery attempts:
- Set `"lastResult": "FAILED"` on the flow
- Set `"failureNote"` describing exactly which step failed, the root cause, and why it's unresolvable inline
- Continue testing remaining flows (don't abort the full run)
- On next run, Phase 0 will flag this flow as requiring re-test after fixes

---

## Graph Schema

### `.tester/app-graph.yaml` — app metadata + screens

```yaml
version: 1
updatedAt: "2024-01-15T10:30:00Z"
appName: YourAppName
bundleId: com.example.yourapp
platform: ios  # ios | macos | android
projectRoot: /absolute/path/to/project
navSourceFiles:
  # iOS/macOS: Swift navigator files
  - relative/path/to/Navigator+Screen.swift
  # Flutter/Android: GoRouter config or routing files
  - flutter/lib/config/router/app_router.dart

screens:
  gameList:
    screenId: gameList
    displayName: Game List
    feature: Game
    # iOS/macOS: Swift file path
    swiftFile: relative/path/GameListView.swift
    # Flutter/Android: Dart file path (use instead of swiftFile)
    # dartFile: flutter/lib/features/game/screens/game_list_screen.dart
    accessibilityId: game_list_screen  # iOS: .accessibilityIdentifier(); Android: Semantics label
    notes: optional
    transitions:
      - action: create_game_button
        actionAccessibilityId: primary_action_button  # iOS: element ID; Android: content-desc or text
        nextScreen: createGame
        transition: presentCover  # iOS: push/presentCover/etc; Flutter: go/push/pushNamed
        logConfirmation: "[AppName] [Feature] ScreenName appeared"
```

### `.tester/flows/<flow-id>.yaml` — one file per named flow

Filename is the kebab-case flow ID (e.g. `create-game.yaml`, `edit-profile.yaml`).

```yaml
name: Human readable name
description: What this flow validates
enabled: true
lastResult: PASSED  # PASSED | FAILED | UNKNOWN
failureNote: null
steps:
  - stepId: 1
    fromScreen: gameList
    toScreen: createGame
    action: primary_action_button  # accessibilityId or null
    logConfirmation: "[AppName] [Feature] ScreenName appeared"
    prerequisites:
      - plain-English required state
```

**Field notes:**
- `platform` — `ios`, `macos`, or `android`; drives which Phase 3 scripts to use
- `accessibilityId` — iOS/macOS: set via `.accessibilityIdentifier()` in Swift; Android/Flutter: `Semantics(label:)` or visible text matched by `android.py tap --text`
- `swiftFile` / `dartFile` — the screen's source file; use `dartFile` for Flutter screens
- `action` — `null` / `auto_on_*` for programmatic transitions; use `--find-text` label for macOS toolbar items; use text/content-desc for Android
- `logConfirmation` — exact prefix to grep in console output or logcat

---

## Phase 0: Graph Staleness Check

Run this before Phase 3 every time. Determines whether to trust the existing graph or rebuild it first.

### 0.1 Check if graph exists

If `.tester/app-graph.yaml` is missing → run Phase 1 now, then Phase 2, then Phase 3.

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

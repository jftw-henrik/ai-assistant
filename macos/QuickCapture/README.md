# Quick Capture (macOS)

Native SwiftUI menu bar app for [Henrik Assistant](../../README.md). Capture tasks and ideas with a global hotkey — similar to Spotlight or Raycast.

## Features

- Menu bar icon (bolt)
- **Global hotkey:** `Ctrl+Option+Space`
- Floating translucent popup, dark mode, centered on screen
- **Submit:** `Enter` or `Cmd+Enter` (`Shift+Enter` for newline)
- **Close:** `Esc`
- POSTs to Henrik Assistant `/capture` on Railway
- Remembers window position and size
- Clears input after successful capture

## Requirements

- macOS 14.0 (Sonoma) or later
- Xcode 15 or later

## Open in Xcode

1. Open the project:

```bash
open macos/QuickCapture/QuickCapture.xcodeproj
```

2. Select the **QuickCapture** scheme and **My Mac** as destination.

3. In **Signing & Capabilities**, choose your **Team** (required to run locally).

4. Press **⌘R** to build and run.

The app runs as a menu bar utility (no Dock icon). Look for the bolt icon in the menu bar.

## Usage

| Action | Shortcut |
|--------|----------|
| Open / toggle popup | `Ctrl+Option+Space` |
| Submit | `Enter` or `Cmd+Enter` |
| New line | `Shift+Enter` |
| Close popup | `Esc` |
| Menu bar → Quick Capture | — |
| Quit | Menu bar → Quit |

Type one or many items in a single message (comma-separated), e.g.:

```
Ring Skatteverket imorgon, fixa Cubase buggen, köp mjölk
```

The server response appears in the status line below the text field.

## API endpoint

Configured in `QuickCapture/Services/CaptureAPI.swift`:

```
POST https://ai-assistant-production-45e5.up.railway.app/capture
Content-Type: application/json

{ "text": "your capture text" }
```

To point at a local server during development, change `CaptureAPI.endpoint` to e.g. `http://127.0.0.1:8000/capture`.

## Project layout

```
macos/QuickCapture/
  QuickCapture.xcodeproj
  QuickCapture/
    QuickCaptureApp.swift       # Menu bar app entry
    AppDelegate.swift           # Hotkey + panel lifecycle
    CapturePanelController.swift
    Services/
      CaptureAPI.swift          # Railway capture client
      HotKeyManager.swift       # Ctrl+Option+Space (Carbon)
      WindowStateStore.swift    # Position/size persistence
    Views/
      CapturePanelView.swift    # Main UI
      CaptureTextView.swift     # Multi-line editor + key handling
      VisualEffectBackground.swift
    Assets.xcassets
    Info.plist
    QuickCapture.entitlements
```

## Build from Terminal

```bash
cd macos/QuickCapture
xcodebuild -scheme QuickCapture -configuration Release -derivedDataPath build build
open build/Build/Products/Release/QuickCapture.app
```

## Auto-launch at login (optional)

1. Build the Release app (see above).
2. Move `QuickCapture.app` to `/Applications`.
3. **System Settings → General → Login Items →** add QuickCapture.

## Troubleshooting

**Hotkey does not work**

- Ensure QuickCapture is running (menu bar bolt visible).
- Another app may already use `Ctrl+Option+Space` — quit conflicting apps or change the hotkey in `HotKeyManager.swift`.

**Network errors**

- Confirm Railway URL is reachable: `curl -X POST https://ai-assistant-production-45e5.up.railway.app/health`
- For local dev, use `http://127.0.0.1:8000` and disable App Sandbox or allow outgoing network in entitlements.

**Code signing**

- Set your Apple Development Team in Xcode target settings before running on device.

## License

Part of the Henrik Assistant project.

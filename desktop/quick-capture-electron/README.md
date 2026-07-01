# Quick Capture (Electron)

Menu bar quick capture for [Henrik Assistant](../../README.md). No Xcode required.

## Requirements

- Node.js 18+
- npm

## Install & run

```bash
cd desktop/quick-capture-electron
npm install
npm start
```

The app runs in the menu bar (tray). Use the bolt icon or the global hotkey.

## Usage

| Action | Shortcut |
|--------|----------|
| Toggle popup | `Ctrl+Option+Space` |
| Submit | `Enter` or `Cmd+Enter` |
| New line | `Shift+Enter` |
| Close | `Esc` |
| Quit | Tray menu → Quit |

## API

Fire-and-forget capture (returns immediately; processing runs on the server):

```
POST https://ai-assistant-production-45e5.up.railway.app/capture/async
Content-Type: application/json

{ "text": "your capture text" }
```

Response: `Accepted` (plain text). The Electron app hides as soon as this returns.

Synchronous capture (waits for full AI/Trello/Calendar result):

```
POST https://ai-assistant-production-45e5.up.railway.app/capture
```

To use a local server, change `CAPTURE_URL` in `main.js`.

## Project layout

```
desktop/quick-capture-electron/
  package.json
  main.js           # Tray, hotkey, window
  preload.js
  renderer/
    index.html
    style.css
    app.js
  assets/
    trayTemplate.png
```

Window position and size are saved in Electron `userData`.

## Auto-launch (optional)

Use **System Settings → Login Items** and add the built app, or a tool like `launchctl` with a packaged `.app` from `electron-builder` (not included by default).

## Legacy Swift app

The previous Xcode/Swift version was removed. Use this Electron app instead.

const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  globalShortcut,
  screen,
  nativeImage,
  ipcMain,
} = require("electron");
const fs = require("fs");
const path = require("path");

const CAPTURE_URL =
  "https://ai-assistant-production-45e5.up.railway.app/capture/async";
const WINDOW_STATE_FILE = "window-state.json";
const DEFAULT_BOUNDS = { width: 560, height: 220 };

let tray = null;
let mainWindow = null;
let isQuitting = false;

function statePath() {
  return path.join(app.getPath("userData"), WINDOW_STATE_FILE);
}

function loadWindowState() {
  try {
    const raw = fs.readFileSync(statePath(), "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveWindowState(bounds) {
  try {
    fs.writeFileSync(statePath(), JSON.stringify(bounds, null, 2), "utf8");
  } catch (err) {
    console.error("Failed to save window state:", err);
  }
}

function centeredBounds(size) {
  const display = screen.getPrimaryDisplay();
  const { width, height } = display.workAreaSize;
  const { x: workX, y: workY } = display.workArea;
  return {
    x: Math.round(workX + (width - size.width) / 2),
    y: Math.round(workY + (height - size.height) / 2),
    width: size.width,
    height: size.height,
  };
}

function resolveBounds() {
  const stored = loadWindowState();
  if (stored && stored.width && stored.height) {
    return stored;
  }
  return centeredBounds(DEFAULT_BOUNDS);
}

function createTrayIcon() {
  const iconPath = path.join(__dirname, "assets", "trayTemplate.png");
  let image = nativeImage.createFromPath(iconPath);
  if (image.isEmpty()) {
    image = nativeImage.createEmpty();
  }
  image.setTemplateImage(true);
  return image;
}

function createWindow() {
  const bounds = resolveBounds();

  mainWindow = new BrowserWindow({
    ...bounds,
    show: false,
    frame: false,
    transparent: true,
    resizable: true,
    movable: true,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: true,
    vibrancy: "hud",
    visualEffectState: "active",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      hideWindow();
    }
  });

  mainWindow.on("moved", () => persistBounds());
  mainWindow.on("resized", () => persistBounds());
}

function persistBounds() {
  if (!mainWindow) return;
  saveWindowState(mainWindow.getBounds());
}

function showWindow() {
  if (!mainWindow) createWindow();

  const bounds = resolveBounds();
  mainWindow.setBounds(bounds);
  mainWindow.show();
  mainWindow.focus();
  mainWindow.webContents.send("panel-shown");
}

function hideWindow() {
  if (!mainWindow) return;
  persistBounds();
  mainWindow.hide();
}

function toggleWindow() {
  if (mainWindow && mainWindow.isVisible()) {
    hideWindow();
  } else {
    showWindow();
  }
}

function registerShortcuts() {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register("Control+Alt+Space", toggleWindow);
  if (!ok) {
    console.error("Failed to register global shortcut Control+Alt+Space");
  }
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    {
      label: "Quick Capture",
      click: () => showWindow(),
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
}

app.whenReady().then(() => {
  if (process.platform === "darwin") {
    app.dock.hide();
  }

  createWindow();
  tray = new Tray(createTrayIcon());
  tray.setToolTip("Quick Capture");
  tray.setContextMenu(buildTrayMenu());
  tray.on("click", toggleWindow);

  registerShortcuts();

  ipcMain.on("hide-panel", () => hideWindow());
  ipcMain.handle("get-capture-url", () => CAPTURE_URL);
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", (event) => {
  event.preventDefault();
});

app.on("activate", () => {
  showWindow();
});

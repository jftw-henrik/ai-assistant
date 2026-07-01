const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("quickCapture", {
  hidePanel: () => ipcRenderer.send("hide-panel"),
  onPanelShown: (callback) => {
    ipcRenderer.on("panel-shown", () => callback());
  },
  getCaptureUrl: () => ipcRenderer.invoke("get-capture-url"),
});

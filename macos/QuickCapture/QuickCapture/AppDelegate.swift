import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let panelController = CapturePanelController()
    private let hotKeyManager = HotKeyManager()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        hotKeyManager.onHotKey = { [weak self] in
            self?.togglePanel()
        }
        hotKeyManager.register()
    }

    func togglePanel() {
        panelController.toggle()
    }

    func showPanel() {
        panelController.show()
    }
}

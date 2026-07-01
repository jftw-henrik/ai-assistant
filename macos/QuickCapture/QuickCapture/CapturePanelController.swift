import AppKit
import SwiftUI

final class CapturePanelController {
    private var panel: NSPanel?
    private var isVisible = false

    func toggle() {
        if isVisible {
            hide()
        } else {
            show()
        }
    }

    func show() {
        if panel == nil {
            panel = makePanel()
        }
        guard let panel else { return }

        let stored = WindowStateStore.load()
        let frame = WindowStateStore.resolvedFrame(stored: stored)
        panel.setFrame(frame, display: true)

        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        panel.orderFrontRegardless()
        isVisible = true
        NotificationCenter.default.post(name: .quickCaptureFocus, object: nil)
    }

    func hide() {
        guard let panel else { return }
        WindowStateStore.save(WindowState(frame: panel.frame))
        panel.orderOut(nil)
        isVisible = false
    }

    private func makePanel() -> NSPanel {
        let stored = WindowStateStore.load()
        let frame = WindowStateStore.resolvedFrame(stored: stored)

        let panel = NSPanel(
            contentRect: frame,
            styleMask: [.nonactivatingPanel, .fullSizeContentView, .borderless],
            backing: .buffered,
            defer: false
        )

        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.titlebarAppearsTransparent = true
        panel.titleVisibility = .hidden
        panel.animationBehavior = .utilityWindow
        panel.becomesKeyOnlyIfNeeded = false

        let rootView = CapturePanelView(onClose: { [weak self] in self?.hide() })
        let hosting = NSHostingView(rootView: rootView)
        hosting.frame = CGRect(origin: .zero, size: frame.size)
        panel.contentView = hosting

        NotificationCenter.default.addObserver(
            forName: NSWindow.didMoveNotification,
            object: panel,
            queue: .main
        ) { notification in
            guard let window = notification.object as? NSWindow else { return }
            WindowStateStore.save(WindowState(frame: window.frame))
        }

        NotificationCenter.default.addObserver(
            forName: NSWindow.didResizeNotification,
            object: panel,
            queue: .main
        ) { notification in
            guard let window = notification.object as? NSWindow else { return }
            WindowStateStore.save(WindowState(frame: window.frame))
        }

        return panel
    }
}

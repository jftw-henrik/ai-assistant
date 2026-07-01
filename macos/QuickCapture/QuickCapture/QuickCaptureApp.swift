import SwiftUI

@main
struct QuickCaptureApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        MenuBarExtra {
            Button("Quick Capture") {
                appDelegate.togglePanel()
            }
            .keyboardShortcut("k", modifiers: [.command, .shift])

            Divider()

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        } label: {
            Image(systemName: "bolt.fill")
        }
        .menuBarExtraStyle(.menu)
    }
}

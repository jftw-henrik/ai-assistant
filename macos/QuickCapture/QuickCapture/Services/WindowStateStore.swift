import AppKit
import CoreGraphics

struct WindowState: Codable, Equatable {
    var x: Double
    var y: Double
    var width: Double
    var height: Double

    static let `default` = WindowState(x: 0, y: 0, width: 560, height: 220)

    var frame: CGRect {
        CGRect(x: x, y: y, width: width, height: height)
    }

    init(frame: CGRect) {
        x = frame.origin.x
        y = frame.origin.y
        width = frame.size.width
        height = frame.size.height
    }

    init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}

enum WindowStateStore {
    private static let key = "quickCapture.windowState"

    static func load() -> WindowState {
        guard
            let data = UserDefaults.standard.data(forKey: key),
            let state = try? JSONDecoder().decode(WindowState.self, from: data)
        else {
            return .default
        }
        return state
    }

    static func save(_ state: WindowState) {
        guard let data = try? JSONEncoder().encode(state) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    static func centeredFrame(size: CGSize, on screen: NSScreen? = NSScreen.main) -> CGRect {
        let screen = screen ?? NSScreen.main ?? NSScreen.screens.first!
        let visible = screen.visibleFrame
        let origin = CGPoint(
            x: visible.midX - size.width / 2,
            y: visible.midY - size.height / 2
        )
        return CGRect(origin: origin, size: size)
    }

    static func resolvedFrame(stored: WindowState, on screen: NSScreen? = NSScreen.main) -> CGRect {
        let screen = screen ?? NSScreen.main ?? NSScreen.screens.first!
        let visible = screen.visibleFrame
        var frame = stored.frame

        if stored.x == 0, stored.y == 0, stored.width == WindowState.default.width {
            return centeredFrame(size: frame.size, on: screen)
        }

        frame.size.width = min(max(frame.size.width, 420), visible.width - 40)
        frame.size.height = min(max(frame.size.height, 160), visible.height - 40)
        frame.origin.x = min(max(frame.origin.x, visible.minX), visible.maxX - frame.size.width)
        frame.origin.y = min(max(frame.origin.y, visible.minY), visible.maxY - frame.size.height)
        return frame
    }
}

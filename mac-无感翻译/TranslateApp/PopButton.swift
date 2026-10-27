import AppKit

/// 划词小图标：选中文字后在附近浮一个 36pt 的小「译」圆钮，点一下才出翻译悬浮窗。
/// 不自动弹窗，比选中即译更无感；和 ⌥D 快捷键划词并存。
final class PopButtonWindow: NSPanel {
    var onClick: ((String) -> Void)?

    private var text = ""
    private var hideWorkItem: DispatchWorkItem?

    init() {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 36, height: 36),
                   styleMask: [.nonactivatingPanel, .borderless],
                   backing: .buffered, defer: false)
        isFloatingPanel = true
        level = .floating
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        isReleasedWhenClosed = false
        hidesOnDeactivate = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        let button = NSButton(title: "译", target: self, action: #selector(clicked))
        button.bezelStyle = .circular
        button.font = .systemFont(ofSize: 14, weight: .semibold)
        button.toolTip = "点击翻译选中文字"
        button.translatesAutoresizingMaskIntoConstraints = false
        button.wantsLayer = true
        button.layer?.backgroundColor = NSColor.controlAccentColor.cgColor
        button.contentTintColor = .white
        NSLayoutConstraint.activate([
            button.widthAnchor.constraint(equalToConstant: 32),
            button.heightAnchor.constraint(equalToConstant: 32),
        ])

        let effect = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: 36, height: 36))
        effect.material = .hudWindow
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.wantsLayer = true
        effect.layer?.cornerRadius = 18
        effect.layer?.masksToBounds = true
        effect.addSubview(button)
        NSLayoutConstraint.activate([
            button.centerXAnchor.constraint(equalTo: effect.centerXAnchor),
            button.centerYAnchor.constraint(equalTo: effect.centerYAnchor),
        ])
        contentView = effect
    }

    @objc private func clicked() {
        hide()
        onClick?(text)
    }

    /// 在鼠标附近显示，4 秒无操作自动消失
    func show(text: String, near point: NSPoint) {
        self.text = text
        hideWorkItem?.cancel()
        var origin = NSPoint(x: point.x + 8, y: point.y - frame.height - 6)
        if let screen = NSScreen.main {
            let visible = screen.visibleFrame
            if origin.x + frame.width > visible.maxX { origin.x = point.x - frame.width - 8 }
            if origin.y < visible.minY { origin.y = point.y + 8 }
        }
        setFrameOrigin(origin)
        alphaValue = 0
        orderFrontRegardless()
        animator().alphaValue = 1

        let item = DispatchWorkItem { [weak self] in self?.hide() }
        hideWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 4, execute: item)
    }

    func hide() {
        hideWorkItem?.cancel()
        hideWorkItem = nil
        orderOut(nil)
    }
}

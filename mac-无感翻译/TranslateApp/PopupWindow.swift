import AppKit
import AVFoundation

/// 悬浮翻译窗：按 Apple HIG 做的无边框毛玻璃浮窗
/// - 毛玻璃材质（hudWindow）、16pt 圆角、阴影，不抢焦点
/// - 顶部：翻译图标 + 名字 + 引擎名 + 关闭；中间原文 / 译文；底部 SF Symbols 圆形按钮
final class PopupWindow: NSPanel {
    private let originalLabel = NSTextField(labelWithString: "")
    private let resultLabel = NSTextField(labelWithString: "")
    private let engineLabel = NSTextField(labelWithString: "")
    private let spinner = NSProgressIndicator()
    var currentTranslation = ""
    private var pinned = false
    /// 多引擎对照区：主结果之外的其他引擎译文，纵向排列
    private let alternatesStack = NSStackView()
    private let synthesizer = AVSpeechSynthesizer()
    private var pinButton: NSButton!
    /// 主纵向容器（存下来，后面按实际内容量它的高度来调窗口）
    private let contentStack = NSStackView()
    /// Esc 全局监听：弹窗不抢焦点所以收不到按键，用全局监听在 Esc 时关窗
    private var escMonitor: Any?

    init() {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 380, height: 150),
                   styleMask: [.nonactivatingPanel, .fullSizeContentView],
                   backing: .buffered, defer: false)
        isFloatingPanel = true
        level = .floating
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        isReleasedWhenClosed = false
        hidesOnDeactivate = false
        isMovableByWindowBackground = true
        titlebarAppearsTransparent = true
        titleVisibility = .hidden
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        // 毛玻璃底
        let effect = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: 380, height: 150))
        effect.material = .hudWindow
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.wantsLayer = true
        effect.layer?.cornerRadius = 16
        effect.layer?.masksToBounds = true
        contentView = effect

        func makeLabel(_ label: NSTextField, font: NSFont, color: NSColor) {
            label.font = font
            label.textColor = color
            label.lineBreakMode = .byWordWrapping
            label.usesSingleLineMode = false
            label.cell?.wraps = true
            // 告诉 Auto Layout 这行最多 348pt 宽（窗口 380 － 左右各 16 边距），否则它按单行不换行量高度，译文就横着冲出屏幕
            label.preferredMaxLayoutWidth = 348
            label.isSelectable = true
            label.isEditable = false
            label.backgroundColor = .clear
            label.isBordered = false
            label.translatesAutoresizingMaskIntoConstraints = false
        }
        makeLabel(originalLabel, font: .systemFont(ofSize: 12.5), color: .secondaryLabelColor)
        makeLabel(resultLabel, font: .systemFont(ofSize: 16), color: .labelColor)
        makeLabel(engineLabel, font: .systemFont(ofSize: 11), color: .tertiaryLabelColor)

        // 顶部：图标 + 名字 + 引擎 + 关闭
        let iconView = NSImageView(image: NSImage(systemSymbolName: "translate", accessibilityDescription: "翻译") ?? NSImage())
        iconView.symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 15, weight: .semibold)
        iconView.contentTintColor = .controlAccentColor
        iconView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            iconView.widthAnchor.constraint(equalToConstant: 18),
            iconView.heightAnchor.constraint(equalToConstant: 18),
        ])
        let titleLabel = NSTextField(labelWithString: "无感翻译")
        titleLabel.font = .systemFont(ofSize: 13, weight: .semibold)
        titleLabel.textColor = .labelColor
        titleLabel.translatesAutoresizingMaskIntoConstraints = false

        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.isDisplayedWhenStopped = false

        let closeButton = iconButton(symbol: "xmark", tooltip: "关闭（Esc）", action: #selector(closePopup))
        let header = NSStackView(views: [iconView, titleLabel, engineLabel, spinner, closeButton])
        header.orientation = .horizontal
        header.alignment = .centerY
        header.spacing = 6
        header.setCustomSpacing(4, after: iconView)
        header.translatesAutoresizingMaskIntoConstraints = false
        // 把引擎名推到右边：用一个伸缩 spacer
        header.setHuggingPriority(.defaultLow, for: .horizontal)

        let divider = NSBox()
        divider.boxType = .separator
        divider.translatesAutoresizingMaskIntoConstraints = false

        // 底部操作：圆形 SF Symbols 按钮
        let copyButton = iconButton(symbol: "doc.on.doc", tooltip: "复制译文", action: #selector(copyTranslation))
        let speakButton = iconButton(symbol: "speaker.wave.2.fill", tooltip: "朗读译文", action: #selector(speakTranslation))
        pinButton = iconButton(symbol: "pin", tooltip: "固定窗口", action: #selector(togglePin))
        let hintLabel = NSTextField(labelWithString: "Esc 关闭")
        hintLabel.font = .systemFont(ofSize: 11)
        hintLabel.textColor = .tertiaryLabelColor
        hintLabel.translatesAutoresizingMaskIntoConstraints = false
        let actions = NSStackView(views: [copyButton, speakButton, pinButton, hintLabel])
        actions.orientation = .horizontal
        actions.alignment = .centerY
        actions.spacing = 8
        actions.translatesAutoresizingMaskIntoConstraints = false

        alternatesStack.orientation = .vertical
        alternatesStack.alignment = .leading
        alternatesStack.spacing = 6
        alternatesStack.isHidden = true
        alternatesStack.translatesAutoresizingMaskIntoConstraints = false

        contentStack.orientation = .vertical
        contentStack.alignment = .leading
        contentStack.spacing = 8
        contentStack.translatesAutoresizingMaskIntoConstraints = false
        [header, divider, originalLabel, resultLabel, alternatesStack, actions].forEach { contentStack.addArrangedSubview($0) }
        contentStack.setCustomSpacing(4, after: header)
        contentStack.setCustomSpacing(4, after: divider)
        contentStack.setCustomSpacing(10, after: resultLabel)
        contentStack.setCustomSpacing(10, after: alternatesStack)
        effect.addSubview(contentStack)
        NSLayoutConstraint.activate([
            contentStack.topAnchor.constraint(equalTo: effect.topAnchor, constant: 12),
            contentStack.leadingAnchor.constraint(equalTo: effect.leadingAnchor, constant: 16),
            contentStack.trailingAnchor.constraint(equalTo: effect.trailingAnchor, constant: -16),
            contentStack.bottomAnchor.constraint(equalTo: effect.bottomAnchor, constant: -12),
            divider.widthAnchor.constraint(equalTo: contentStack.widthAnchor),
            originalLabel.widthAnchor.constraint(equalTo: contentStack.widthAnchor),
            resultLabel.widthAnchor.constraint(equalTo: contentStack.widthAnchor),
            alternatesStack.widthAnchor.constraint(equalTo: contentStack.widthAnchor),
        ])
        // Esc 全局监听：弹窗不抢焦点，Esc 按键不会送到它这里；全局监听到 Esc 且弹窗可见时关窗
        escMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self = self, self.isVisible, event.keyCode == 53 else { return }
            self.orderOut(nil)
        }
    }

    private func iconButton(symbol: String, tooltip: String, action: Selector) -> NSButton {
        let b = NSButton(image: NSImage(systemSymbolName: symbol, accessibilityDescription: tooltip) ?? NSImage(),
                         target: self, action: action)
        b.bezelStyle = .circular
        b.controlSize = .small
        b.toolTip = tooltip
        b.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            b.widthAnchor.constraint(equalToConstant: 26),
            b.heightAnchor.constraint(equalToConstant: 26),
        ])
        return b
    }

    @objc private func copyTranslation() {
        guard !currentTranslation.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(currentTranslation, forType: .string)
        engineLabel.stringValue = "已复制 ✓"
    }
    @objc private func speakTranslation() {
        guard !currentTranslation.isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)
        let utter = AVSpeechUtterance(string: currentTranslation)
        let target = TranslateSettings.shared.fixedTarget
        utter.voice = AVSpeechSynthesisVoice(language: target == "en" ? "en-US" : "zh-CN")
        utter.rate = 0.5
        synthesizer.speak(utter)
    }
    @objc private func togglePin() {
        pinned.toggle()
        pinButton.image = NSImage(systemSymbolName: pinned ? "pin.fill" : "pin",
                                  accessibilityDescription: "固定窗口")
        pinButton.contentTintColor = pinned ? .controlAccentColor : nil
    }
    @objc private func closePopup() { orderOut(nil) }

    override func cancelOperation(_ sender: Any?) { orderOut(nil) }

    func show(original: String, near mouse: NSPoint) {
        currentTranslation = ""
        alternatesStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        alternatesStack.isHidden = true
        originalLabel.stringValue = TranslateSettings.shared.showOriginal ? original : ""
        originalLabel.isHidden = !TranslateSettings.shared.showOriginal
        resultLabel.stringValue = "正在翻译…"
        engineLabel.stringValue = TranslateSettings.shared.engine.displayName
        spinner.startAnimation(nil)

        var frame = self.frame
        frame.size.width = 380
        frame.size.height = 160
        var origin = NSPoint(x: mouse.x + 12, y: mouse.y - frame.height - 8)
        if let screen = NSScreen.main {
            let visible = screen.visibleFrame
            if origin.x + frame.width > visible.maxX { origin.x = mouse.x - frame.width - 12 }
            if origin.y < visible.minY { origin.y = mouse.y + 12 }
        }
        alphaValue = 0
        setFrame(NSRect(origin: origin, size: frame.size), display: true)
        orderFrontRegardless()
        // 让弹窗成为 key 窗口（不激活 App），Esc 直接送到它这里走 cancelOperation 关窗，不依赖全局监听的授权时机
        makeKey()
        animator().alphaValue = 1
    }

    func showResult(_ text: String) {
        showResult(text, engineName: TranslateSettings.shared.engine.displayName)
    }

    /// 带引擎名的结果（润色模式、多引擎对照时用）
    func showResult(_ text: String, engineName: String) {
        currentTranslation = text
        spinner.stopAnimation(nil)
        resultLabel.stringValue = text
        engineLabel.stringValue = engineName
        // 新一次翻译先清掉上次的对照区
        alternatesStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        alternatesStack.isHidden = true
        // 按实际内容量窗口高：先布局，再取容器拟合高度（短译文窗口矮、长译文窗口高）
        contentView?.layoutSubtreeIfNeeded()
        let contentH = contentStack.fittingSize.height + 24 // 上下各 12pt 边距
        var h = min(500, max(120, contentH))
        // 用窗口所在的屏幕算可见区（不要只用 NSScreen.main）
        let visible = (self.screen ?? NSScreen.main)?.visibleFrame ?? .zero
        // 内容比可见区还高：窗口占满可见区高
        if h > visible.height, visible.height > 0 {
            h = visible.height
        }
        var f = frame
        f.size.height = h
        // 顶边先按原来（贴着鼠标）
        f.origin.y = frame.origin.y + frame.height - h
        // 底边低于 Dock 时，整个窗口往上挪到底边贴 Dock，而不是把内容截掉
        if f.origin.y < visible.minY {
            f.origin.y = visible.minY
        }
        // 顶边冲出屏幕顶时，把窗口往下挪到顶边贴屏幕顶
        if f.origin.y + h > visible.maxY {
            f.origin.y = visible.maxY - h
        }
        setFrame(f, display: true, animate: true)
    }

    /// 多引擎对照：主结果之外的引擎译文纵向排列在主结果下方
    func showAlternates(_ items: [(title: String, text: String)]) {
        guard !items.isEmpty else { return }
        alternatesStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for item in items {
            let label = NSTextField(labelWithString: "\(item.title)：\(item.text)")
            label.font = .systemFont(ofSize: 12.5)
            label.textColor = .secondaryLabelColor
            label.lineBreakMode = .byWordWrapping
            label.usesSingleLineMode = false
            label.cell?.wraps = true
            label.preferredMaxLayoutWidth = 348
            label.isSelectable = true
            label.isEditable = false
            label.backgroundColor = .clear
            label.isBordered = false
            label.translatesAutoresizingMaskIntoConstraints = false
            alternatesStack.addArrangedSubview(label)
            label.widthAnchor.constraint(equalTo: alternatesStack.widthAnchor).isActive = true
        }
        alternatesStack.isHidden = false
        contentView?.layoutSubtreeIfNeeded()
        let extra = min(200, alternatesStack.fittingSize.height + 8)
        var f = frame
        f.size.height += extra
        f.origin.y -= extra
        setFrame(f, display: true, animate: true)
    }

    func showError(_ message: String) {
        spinner.stopAnimation(nil)
        resultLabel.stringValue = "翻译失败，请检查网络或 API Key 设置"
        engineLabel.stringValue = message
    }
}

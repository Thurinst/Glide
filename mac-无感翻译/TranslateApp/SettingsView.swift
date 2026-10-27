import AppKit
import ServiceManagement

/// 快捷键录制按钮：点一下进入录制，再按任意组合键即保存（Esc 取消）
private final class HotkeyRecordButton: NSButton {
    var hotkeyAction: HotkeyAction = .selection
    private var monitor: Any?
    private var recording = false

    func configure(action: HotkeyAction) {
        hotkeyAction = action
        target = self
        self.action = #selector(startRecording)
        bezelStyle = .rounded
        updateTitle()
    }

    func updateTitle() {
        title = TranslateSettings.shared.hotkeyDescription(for: hotkeyAction)
    }

    @objc private func startRecording() {
        if recording { cancelRecording(); return }
        recording = true
        title = "按下快捷键…（Esc 取消）"
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self = self else { return event }
            if event.keyCode == 53 { // Esc
                self.cancelRecording()
                return nil
            }
            // 纯修饰键（Cmd/Shift/Option/Ctrl/Fn）不算快捷键
            let ignored: Set<UInt16> = [54, 55, 56, 57, 58, 59, 60, 61, 62, 63]
            if ignored.contains(event.keyCode) { return nil }
            let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            TranslateSettings.shared.setHotkey(event.keyCode, modifiers: mods, for: self.hotkeyAction)
            HotkeyManager.shared.reload()
            self.stopRecording()
            return nil
        }
    }

    private func stopRecording() {
        recording = false
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        updateTitle()
    }

    private func cancelRecording() {
        recording = false
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        updateTitle()
    }
}

/// 设置窗口：Apple HIG 风格，分四个标签页：通用 / 翻译服务 / 快捷键 / 关于
final class SettingsWindowController: NSWindowController {
    // MARK: 通用
    private let launchCheck = NSButton(checkboxWithTitle: "开机自启", target: nil, action: nil)
    private let autoCheck = NSButton(checkboxWithTitle: "划词后自动翻译（鼠标松开即弹）", target: nil, action: nil)
    private let popButtonCheck = NSButton(checkboxWithTitle: "划词后先显示小「译」图标，点一下才翻译", target: nil, action: nil)
    private let clipboardWatchCheck = NSButton(checkboxWithTitle: "剪贴板监听：复制文字后自动翻译出悬浮窗", target: nil, action: nil)
    private let autoSpeakCheck = NSButton(checkboxWithTitle: "翻译完成后自动朗读译文", target: nil, action: nil)
    private let showOriginalCheck = NSButton(checkboxWithTitle: "弹窗里同时显示原文", target: nil, action: nil)
    private let clipboardCheck = NSButton(checkboxWithTitle: "辅助功能读不到时，用 Cmd+C 兜底（推荐开）", target: nil, action: nil)

    // MARK: 翻译服务
    private let enginePopup = NSPopUpButton()
    private let googleCheck = NSButton(checkboxWithTitle: "Google 免费机翻（无需 Key）", target: nil, action: nil)
    private let deepLCheck = NSButton(checkboxWithTitle: "DeepL API", target: nil, action: nil)
    private let aiCheck = NSButton(checkboxWithTitle: "AI 大模型（OpenAI 兼容接口）", target: nil, action: nil)
    private let apiBaseField = NSTextField(string: "")
    private let apiKeyField = NSSecureTextField(string: "")
    private let modelField = NSTextField(string: "")
    private let deepLKeyField = NSSecureTextField(string: "")
    private let targetPopup = NSPopUpButton()

    // MARK: 快捷键
    private var hotkeyButtons: [HotkeyRecordButton] = []

    convenience init() {
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 560),
                           styleMask: [.titled, .closable], backing: .buffered, defer: false)
        win.title = "无感翻译 — 设置"
        win.center()
        self.init(window: win)
        buildUI()
        loadValues()
    }

    // MARK: UI 搭建

    private func sectionHeader(_ title: String) -> NSView {
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 13, weight: .semibold)
        label.textColor = .labelColor
        let divider = NSBox()
        divider.boxType = .separator
        divider.translatesAutoresizingMaskIntoConstraints = false
        let stack = NSStackView(views: [label, divider])
        stack.orientation = .vertical
        stack.spacing = 4
        stack.translatesAutoresizingMaskIntoConstraints = false
        divider.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        return stack
    }

    private func hint(_ s: String) -> NSTextField {
        let l = NSTextField(labelWithString: s)
        l.font = .systemFont(ofSize: 11)
        l.textColor = .secondaryLabelColor
        l.lineBreakMode = .byWordWrapping
        l.usesSingleLineMode = false
        l.cell?.wraps = true
        return l
    }

    private func row(_ title: String, _ view: NSView) -> NSView {
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 13)
        let r = NSStackView(views: [label, view])
        r.orientation = .horizontal
        r.spacing = 8
        r.alignment = .centerY
        return r
    }

    private func tabView(label: String, views: [NSView]) -> NSTabViewItem {
        let container = NSView()
        let stack = NSStackView(views: views)
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: 16),
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
        ])
        let item = NSTabViewItem(identifier: label)
        item.label = label
        item.view = container
        return item
    }

    private func buildUI() {
        guard let content = window?.contentView else { return }

        // ---- 通用 ----
        for check in [launchCheck, autoCheck, popButtonCheck, clipboardWatchCheck, autoSpeakCheck, showOriginalCheck, clipboardCheck] {
            check.target = self
            check.action = #selector(saveAll)
        }
        let generalTab = tabView(label: "通用", views: [
            sectionHeader("启动与行为"),
            launchCheck,
            autoCheck,
            popButtonCheck,
            clipboardWatchCheck,
            sectionHeader("显示与发音"),
            autoSpeakCheck,
            showOriginalCheck,
            clipboardCheck,
            hint("划词翻译需要辅助功能权限：系统设置 → 隐私与安全性 → 辅助功能，勾选「无感翻译」。"),
        ])

        // ---- 翻译服务 ----
        enginePopup.addItems(withTitles: TranslateEngine.allCases.map { $0.displayName })
        enginePopup.target = self
        enginePopup.action = #selector(engineChanged)
        for check in [googleCheck, deepLCheck, aiCheck] {
            check.target = self
            check.action = #selector(engineChanged)
        }
        apiBaseField.widthAnchor.constraint(equalToConstant: 340).isActive = true
        apiKeyField.widthAnchor.constraint(equalToConstant: 340).isActive = true
        modelField.widthAnchor.constraint(equalToConstant: 200).isActive = true
        deepLKeyField.widthAnchor.constraint(equalToConstant: 340).isActive = true
        targetPopup.addItems(withTitles: ["自动（有中文→英文，否则→中文）", "固定译成中文", "固定译成英文"])
        targetPopup.target = self
        targetPopup.action = #selector(saveAll)
        let serviceTab = tabView(label: "翻译服务", views: [
            sectionHeader("主引擎"),
            row("主翻译引擎：", enginePopup),
            hint("主引擎的结果显示在悬浮窗最上方；其他已填 Key 的引擎会并行查询，结果对照显示在下方。"),
            sectionHeader("参与对照的引擎"),
            googleCheck,
            deepLCheck,
            row("DeepL Key：", deepLKeyField),
            hint("DeepL Free Key 以 :fx 结尾，自动走免费接口。"),
            aiCheck,
            row("AI 接口地址：", apiBaseField),
            hint("OpenAI: https://api.openai.com/v1  DeepSeek: https://api.deepseek.com/v1  通义: https://dashscope.aliyuncs.com/compatible-mode/v1"),
            row("AI API Key：", apiKeyField),
            row("AI 模型：", modelField),
            hint("如 gpt-4o-mini、deepseek-chat、qwen-plus。源语言与目标语言相同时自动用 AI 润色。"),
            sectionHeader("目标语言"),
            row("目标语言：", targetPopup),
        ])

        // ---- 快捷键 ----
        var hotkeyViews: [NSView] = [sectionHeader("全局快捷键"), hint("点一下按钮，再按你想要的组合键即可修改，立即生效。全局快捷键不需要辅助功能权限。")]
        for action in HotkeyAction.allCases {
            let button = HotkeyRecordButton()
            button.configure(action: action)
            hotkeyButtons.append(button)
            hotkeyViews.append(row(action.title + "：", button))
        }
        let hotkeyTab = tabView(label: "快捷键", views: hotkeyViews)

        // ---- 关于 ----
        let versionLabel = NSTextField(labelWithString: "无感翻译  \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")")
        versionLabel.font = .systemFont(ofSize: 16, weight: .semibold)
        let authorLabel = NSTextField(labelWithString: "作者：Pudding")
        authorLabel.font = .systemFont(ofSize: 13)
        authorLabel.textColor = .secondaryLabelColor
        let permBtn = NSButton(title: "检查辅助功能权限…", target: self, action: #selector(checkPermission))
        permBtn.bezelStyle = .rounded
        let aboutTab = tabView(label: "关于", views: [
            sectionHeader("关于"),
            versionLabel,
            authorLabel,
            hint("菜单栏划词翻译：选中文字自动翻译，截图 OCR 离线识别，历史记录与生词本一键导出 Anki。"),
            permBtn,
        ])

        let tabView = NSTabView()
        tabView.addTabViewItem(generalTab)
        tabView.addTabViewItem(serviceTab)
        tabView.addTabViewItem(hotkeyTab)
        tabView.addTabViewItem(aboutTab)
        tabView.translatesAutoresizingMaskIntoConstraints = false

        let saveBtn = NSButton(title: "保存", target: self, action: #selector(saveAll))
        saveBtn.bezelStyle = .rounded
        saveBtn.keyEquivalent = "\r"
        let buttonRow = NSStackView(views: [saveBtn])
        buttonRow.orientation = .horizontal
        buttonRow.translatesAutoresizingMaskIntoConstraints = false

        let root = NSStackView(views: [tabView, buttonRow])
        root.orientation = .vertical
        root.alignment = .trailing
        root.spacing = 12
        root.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(root)
        NSLayoutConstraint.activate([
            root.topAnchor.constraint(equalTo: content.topAnchor, constant: 12),
            root.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 12),
            root.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -12),
            root.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
            tabView.widthAnchor.constraint(equalTo: root.widthAnchor),
        ])
    }

    // MARK: 读写

    private func loadValues() {
        let s = TranslateSettings.shared
        enginePopup.selectItem(at: TranslateEngine.allCases.firstIndex(of: s.engine) ?? 0)
        apiBaseField.stringValue = s.apiBaseURL
        apiKeyField.stringValue = s.apiKey
        modelField.stringValue = s.model
        deepLKeyField.stringValue = s.deepLKey
        targetPopup.selectItem(at: s.fixedTarget == "auto" ? 0 : (s.fixedTarget == "zh-CN" ? 1 : 2))
        launchCheck.state = s.launchAtLogin ? .on : .off
        autoCheck.state = s.autoTranslateOnSelect ? .on : .off
        popButtonCheck.state = s.showPopButton ? .on : .off
        clipboardWatchCheck.state = s.clipboardWatch ? .on : .off
        autoSpeakCheck.state = s.autoSpeak ? .on : .off
        showOriginalCheck.state = s.showOriginal ? .on : .off
        clipboardCheck.state = (UserDefaults.standard.object(forKey: "clipboardFallback") as? Bool ?? true) ? .on : .off
        googleCheck.state = s.isEngineEnabled(.googleFree) ? .on : .off
        deepLCheck.state = s.isEngineEnabled(.deepL) ? .on : .off
        aiCheck.state = s.isEngineEnabled(.openAI) ? .on : .off
        for b in hotkeyButtons { b.updateTitle() }
        updateFieldVisibility()
    }

    private func updateFieldVisibility() {
        apiBaseField.isEnabled = aiCheck.state == .on
        apiKeyField.isEnabled = aiCheck.state == .on
        modelField.isEnabled = aiCheck.state == .on
        deepLKeyField.isEnabled = deepLCheck.state == .on
    }

    @objc private func engineChanged() { updateFieldVisibility(); saveAll() }

    @objc private func checkPermission() {
        let ok = SelectionMonitor.checkAccessibilityPermission()
        let alert = NSAlert()
        alert.messageText = ok ? "辅助功能权限已开启 ✓" : "请在 系统设置 → 隐私与安全性 → 辅助功能 里勾选本 App"
        alert.runModal()
    }

    @objc private func saveAll() {
        let s = TranslateSettings.shared
        s.engine = TranslateEngine.allCases[enginePopup.indexOfSelectedItem]
        s.apiBaseURL = apiBaseField.stringValue.trimmingCharacters(in: .whitespaces)
        s.apiKey = apiKeyField.stringValue.trimmingCharacters(in: .whitespaces)
        s.model = modelField.stringValue.trimmingCharacters(in: .whitespaces)
        s.deepLKey = deepLKeyField.stringValue.trimmingCharacters(in: .whitespaces)
        s.fixedTarget = targetPopup.indexOfSelectedItem == 0 ? "auto" : (targetPopup.indexOfSelectedItem == 1 ? "zh-CN" : "en")
        s.launchAtLogin = launchCheck.state == .on
        s.autoTranslateOnSelect = autoCheck.state == .on
        s.showPopButton = popButtonCheck.state == .on
        s.clipboardWatch = clipboardWatchCheck.state == .on
        s.autoSpeak = autoSpeakCheck.state == .on
        s.showOriginal = showOriginalCheck.state == .on
        s.setEngineEnabled(googleCheck.state == .on, for: .googleFree)
        s.setEngineEnabled(deepLCheck.state == .on, for: .deepL)
        s.setEngineEnabled(aiCheck.state == .on, for: .openAI)
        UserDefaults.standard.set(clipboardCheck.state == .on, forKey: "clipboardFallback")
        updateFieldVisibility()
        applyLaunchAtLogin()
    }

    /// 开机自启：macOS 13+ SMAppService；未签名/临时签名可能注册失败，失败只忽略
    private func applyLaunchAtLogin() {
        if #available(macOS 13, *) {
            do {
                if TranslateSettings.shared.launchAtLogin {
                    try SMAppService.mainApp.register()
                } else {
                    try SMAppService.mainApp.unregister()
                }
            } catch {
                // 忽略：通常是临时签名导致无法注册，不影响主功能
            }
        }
    }
}

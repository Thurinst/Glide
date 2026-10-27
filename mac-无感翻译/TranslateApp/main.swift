import AppKit
import AVFoundation

/// 菜单栏 App 入口 v2.0.0：无 Dock 图标，常驻右上角。
/// 划词 -> 小「译」图标（点一下才翻译）或直接悬浮窗；⌥A 主窗口、⌥S 截图 OCR、⌥⇧S 静默 OCR。
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let monitor = SelectionMonitor()
    private let popup = PopupWindow()
    private let popButton = PopButtonWindow()
    private var settingsWC: SettingsWindowController?
    private var mainWC: MainWindowController?
    private var translateTask: Task<Void, Never>?
    private let synthesizer = AVSpeechSynthesizer()

    // 剪贴板监听防重：上次处理过的剪贴板内容、以及我们自己复制出去的译文不重复触发
    private var lastClipboardChangeCount = 0
    private var lastClipboardHandled = ""
    private var lastTranslatedResult = ""

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 单实例保证：不许一个 App 开两次
        if !ensureSingleInstance() {
            NSApp.terminate(nil)
            return
        }
        NSApp.setActivationPolicy(.accessory) // 不占 Dock

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let image = NSImage(systemSymbolName: "translate", accessibilityDescription: "无感翻译") {
            image.isTemplate = true
            statusItem.button?.image = image
        } else {
            statusItem.button?.title = "译"
        }
        statusItem.button?.toolTip = "无感翻译：选中文字自动翻译"
        buildMenu()

        monitor.onSelectedText = { [weak self] text, point in
            self?.handleSelection(text, at: point)
        }
        monitor.start()

        popButton.onClick = { [weak self] text in
            self?.translateText(text, at: NSEvent.mouseLocation)
        }

        // 全局快捷键：⌥D 划词、⌥A 输入、⌥S 截图、⌥⇧S 静默 OCR（设置里可改）
        HotkeyManager.shared.onAction = { [weak self] action in
            guard let self = self else { return }
            switch action {
            case .selection: self.monitor.translateClipboardOrSelection()
            case .input: self.openMainWindow()
            case .screenshot: ScreenshotOCR.shared.start(silent: false)
            case .silentOCR: ScreenshotOCR.shared.start(silent: true)
            }
        }
        HotkeyManager.shared.start()

        // 截图 OCR 回调
        ScreenshotOCR.shared.onTextRecognized = { [weak self] text, rect in
            self?.translateText(text, at: NSPoint(x: rect.midX, y: rect.midY))
        }
        ScreenshotOCR.shared.onSilentText = { text in
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        }
        ScreenshotOCR.shared.onError = { [weak self] message in
            guard let self = self else { return }
            self.popup.show(original: "截图 OCR", near: NSEvent.mouseLocation)
            self.popup.showError(message)
        }

        startClipboardWatcher()

        // 首次启动提醒开辅助功能权限（只弹一次）
        if !UserDefaults.standard.bool(forKey: "permissionPrompted") {
            UserDefaults.standard.set(true, forKey: "permissionPrompted")
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                _ = SelectionMonitor.checkAccessibilityPermission()
            }
        }
    }

    // MARK: 单实例

    /// 单实例保证：同一个 App 不许开两次。
    /// - 同版本已在跑：激活它，本进程直接退出。
    /// - 旧版本在跑：请它退出，等它走后本进程继续启动（升级接管）。
    /// - 新版本在跑：激活它，本进程退出（不降级覆盖）。
    /// 返回 true 表示本进程继续启动，false 表示已移交，本进程应退出。
    private func ensureSingleInstance() -> Bool {
        let myID = Bundle.main.bundleIdentifier ?? ""
        guard !myID.isEmpty else { return true }
        let me = ProcessInfo.processInfo.processIdentifier
        let others = NSWorkspace.shared.runningApplications.filter {
            $0.bundleIdentifier == myID && $0.processIdentifier != me
        }
        guard let other = others.first else { return true }
        let myVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
        let otherVersion = other.bundleURL
            .flatMap { Bundle(url: $0)?.infoDictionary?["CFBundleShortVersionString"] as? String } ?? ""
        if !otherVersion.isEmpty, !myVersion.isEmpty,
           compareVersion(otherVersion, myVersion) == .orderedAscending {
            // 旧版本在跑：请它退出，等它走
            other.terminate()
            let deadline = Date(timeIntervalSinceNow: 3)
            while Date() < deadline {
                if !NSWorkspace.shared.runningApplications.contains(where: { $0.processIdentifier == other.processIdentifier }) {
                    return true
                }
                RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.1))
            }
            return false // 旧进程 3 秒还没退：宁可不启动，也不双开
        }
        other.activate(options: [.activateAllWindows])
        return false
    }

    /// 版本号按段比较，如 2.0.1 > 2.0.0
    private func compareVersion(_ a: String, _ b: String) -> ComparisonResult {
        let pa = a.split(separator: ".").compactMap { Int($0) }
        let pb = b.split(separator: ".").compactMap { Int($0) }
        for i in 0..<max(pa.count, pb.count) {
            let x = i < pa.count ? pa[i] : 0
            let y = i < pb.count ? pb[i] : 0
            if x < y { return .orderedAscending }
            if x > y { return .orderedDescending }
        }
        return .orderedSame
    }

    /// 已在跑时用户又双击/打开本 App：直接打开主窗口
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openMainWindow()
        return true
    }

    // MARK: 菜单栏

    private func buildMenu() {
        let menu = NSMenu()
        let openItem = NSMenuItem(title: "打开主窗口  ⌥A", action: #selector(openMainWindow), keyEquivalent: "")
        let selectionItem = NSMenuItem(title: "划词翻译  ⌥D", action: #selector(translateNow), keyEquivalent: "")
        let screenshotItem = NSMenuItem(title: "截图翻译  ⌥S", action: #selector(screenshotTranslate), keyEquivalent: "")
        let silentItem = NSMenuItem(title: "静默 OCR  ⌥⇧S", action: #selector(silentOCRTranslate), keyEquivalent: "")
        let settingsItem = NSMenuItem(title: "设置…", action: #selector(openSettings), keyEquivalent: ",")
        let permItem = NSMenuItem(title: "检查辅助功能权限…", action: #selector(checkPermission), keyEquivalent: "")
        let quitItem = NSMenuItem(title: "退出", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quitItem.target = NSApp
        menu.addItem(openItem)
        menu.addItem(selectionItem)
        menu.addItem(screenshotItem)
        menu.addItem(silentItem)
        menu.addItem(.separator())
        menu.addItem(settingsItem)
        menu.addItem(permItem)
        menu.addItem(.separator())
        menu.addItem(quitItem)
        for item in menu.items where item !== quitItem { item.target = self }
        statusItem.menu = menu
    }

    @objc private func translateNow() { monitor.translateClipboardOrSelection() }
    @objc private func screenshotTranslate() { ScreenshotOCR.shared.start(silent: false) }
    @objc private func silentOCRTranslate() { ScreenshotOCR.shared.start(silent: true) }

    @objc private func openMainWindow() {
        if mainWC == nil { mainWC = MainWindowController() }
        mainWC?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openSettings() {
        if settingsWC == nil { settingsWC = SettingsWindowController() }
        settingsWC?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func checkPermission() {
        let ok = SelectionMonitor.checkAccessibilityPermission()
        let alert = NSAlert()
        alert.messageText = ok ? "辅助功能权限已开启 ✓" : "请在 系统设置 → 隐私与安全性 → 辅助功能 里勾选本 App"
        alert.runModal()
    }

    // MARK: 翻译编排

    private func handleSelection(_ text: String, at point: NSPoint) {
        if TranslateSettings.shared.showPopButton {
            popButton.show(text: text, near: point)
        } else {
            translateText(text, at: point)
        }
    }

    private func translateText(_ text: String, at point: NSPoint) {
        popButton.hide()
        translateTask?.cancel()
        popup.show(original: text, near: point)
        let target = TranslationService.shared.targetLanguage(for: text)
        let normalizedTarget = target == "zh-CN" ? "zh" : target
        let detected = TranslationService.shared.detectLanguage(of: text)
        translateTask = Task { [weak self] in
            guard let self = self else { return }
            // 润色模式：源语言与目标语言相同，且已填 AI Key
            if normalizedTarget == detected, !TranslateSettings.shared.apiKey.isEmpty {
                do {
                    let polished = try await TranslationService.shared.polish(text)
                    if Task.isCancelled { return }
                    await MainActor.run {
                        self.popup.showResult(polished, engineName: "AI 润色")
                        HistoryStore.shared.add(source: text, translation: polished, engine: "AI 润色")
                        self.lastTranslatedResult = polished
                        if TranslateSettings.shared.autoSpeak { self.speak(text: polished, target: target) }
                    }
                } catch {
                    if Task.isCancelled { return }
                    await MainActor.run { self.popup.showError(error.localizedDescription) }
                }
                return
            }
            // 多引擎并行对照
            let results = await TranslationService.shared.translateAllEngines(text, source: "auto", target: target)
            if Task.isCancelled { return }
            await MainActor.run {
                guard let primary = TranslationService.pickPrimary(from: results, preferred: TranslateSettings.shared.engine) else {
                    self.popup.showError("没有可用的翻译引擎")
                    return
                }
                switch primary.result {
                case .success(let translated):
                    self.popup.showResult(translated, engineName: primary.engine.displayName)
                    HistoryStore.shared.add(source: text, translation: translated, engine: primary.engine.displayName)
                    self.lastTranslatedResult = translated
                    let alternates: [(title: String, text: String)] = results.filter { $0.engine != primary.engine }.compactMap { item in
                        if case .success(let value) = item.result { return (item.engine.displayName, value) }
                        return nil
                    }
                    if !alternates.isEmpty { self.popup.showAlternates(alternates) }
                    if TranslateSettings.shared.autoSpeak { self.speak(text: translated, target: target) }
                case .failure(let error):
                    self.popup.showError(error.localizedDescription)
                }
            }
        }
    }

    private func speak(text: String, target: String) {
        synthesizer.stopSpeaking(at: .immediate)
        let utter = AVSpeechUtterance(string: text)
        utter.voice = AVSpeechSynthesisVoice(language: target == "en" ? "en-US" : "zh-CN")
        utter.rate = 0.5
        synthesizer.speak(utter)
    }

    // MARK: 剪贴板监听

    private func startClipboardWatcher() {
        lastClipboardChangeCount = NSPasteboard.general.changeCount
        Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.checkClipboard()
        }
    }

    private func checkClipboard() {
        guard TranslateSettings.shared.clipboardWatch else { return }
        let pb = NSPasteboard.general
        guard pb.changeCount != lastClipboardChangeCount else { return }
        lastClipboardChangeCount = pb.changeCount
        guard let s = pb.string(forType: .string) else { return }
        let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 1, trimmed.count <= 5000 else { return }
        // 自己复制出去的译文、以及刚处理过的同一段文字不再重复触发
        guard trimmed != lastClipboardHandled, trimmed != lastTranslatedResult else { return }
        lastClipboardHandled = trimmed
        translateText(trimmed, at: NSEvent.mouseLocation)
    }
}

let delegate = AppDelegate()
NSApplication.shared.delegate = delegate
NSApplication.shared.run()

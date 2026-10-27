import AppKit
import ApplicationServices

/// 监听划词：鼠标松开后 0.15s 读当前 App 的选中文本。
/// 优先走 Accessibility（不碰剪贴板），拿不到时再用 Cmd+C 兜底。
final class SelectionMonitor {
    var onSelectedText: ((String, NSPoint) -> Void)?
    private var mouseMonitor: Any?
    private var lastText = ""
    private var lastTime: Date = .distantPast

    func start() {
        // 全局鼠标松开监听（需要辅助功能权限，否则拿不到选中文本）
        mouseMonitor = NSEvent.addGlobalMonitorForEvents(matching: .leftMouseUp) { [weak self] _ in
            self?.handleMouseUp()
        }
        // 也监听本 App 内的松开，方便在设置窗口里测试
        NSEvent.addLocalMonitorForEvents(matching: .leftMouseUp) { [weak self] event in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                self?.fetchSelectedText()
            }
            return event
        }
    }

    func stop() {
        if let m = mouseMonitor { NSEvent.removeMonitor(m) }
        mouseMonitor = nil
    }

    private func handleMouseUp() {
        guard TranslateSettings.shared.autoTranslateOnSelect else { return }
        // 防抖：300ms 内重复触发只算一次
        if Date().timeIntervalSince(lastTime) < 0.3 { return }
        lastTime = Date()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            self?.fetchSelectedText()
        }
    }

    /// 手动触发：翻译剪贴板 / 当前选中（快捷键用）
    func translateClipboardOrSelection() {
        fetchSelectedText(forceClipboardFallback: true)
    }

    private func fetchSelectedText(forceClipboardFallback: Bool = false) {
        let mouse = NSEvent.mouseLocation
        if let text = axSelectedText(), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            deliver(text, at: mouse)
            return
        }
        if forceClipboardFallback || shouldUseClipboardFallback() {
            clipboardFallback(at: mouse)
        }
    }

    private func deliver(_ text: String, at point: NSPoint) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count >= 1, t.count <= 5000 else { return }
        // 同一段文本重复选中不重复弹窗
        if t == lastText { return }
        lastText = t
        onSelectedText?(t, point)
    }

    // MARK: Accessibility 读取选中文本
    private func axSelectedText() -> String? {
        let systemWide = AXUIElementCreateSystemWide()
        var focusedApp: CFTypeRef?
        guard AXUIElementCopyAttributeValue(systemWide, kAXFocusedApplicationAttribute as CFString, &focusedApp) == .success,
              let app = focusedApp else { return nil }
        let appElement = app as! AXUIElement
        var focusedUI: CFTypeRef?
        guard AXUIElementCopyAttributeValue(appElement, kAXFocusedUIElementAttribute as CFString, &focusedUI) == .success,
              let ui = focusedUI else { return nil }
        let element = ui as! AXUIElement
        // 先直接读选中文本
        var value: CFTypeRef?
        if AXUIElementCopyAttributeValue(element, kAXSelectedTextAttribute as CFString, &value) == .success,
           let s = value as? String, !s.isEmpty {
            return s
        }
        // 有些 App（浏览器地址栏等）选中文本在 value 里带 range，退而读 selectedTextRange + value
        var rangeValue: CFTypeRef?
        var fullValue: CFTypeRef?
        if AXUIElementCopyAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, &rangeValue) == .success,
           AXUIElementCopyAttributeValue(element, kAXValueAttribute as CFString, &fullValue) == .success,
           let full = fullValue as? String,
           let rangeValue {
            let range = unsafeBitCast(rangeValue, to: AXValue.self)
            var cfRange = CFRange()
            if AXValueGetValue(range, .cfRange, &cfRange) {
                let start = full.index(full.startIndex, offsetBy: min(cfRange.location, full.count))
                let end = full.index(start, offsetBy: min(cfRange.length, full.count - cfRange.location))
                let s = String(full[start..<end])
                if !s.isEmpty { return s }
            }
        }
        return nil
    }

    // MARK: 剪贴板兜底：保存旧剪贴板 -> 模拟 Cmd+C -> 读新剪贴板 -> 恢复旧剪贴板
    private var clipboardFallbackInFlight = false
    private func shouldUseClipboardFallback() -> Bool {
        // 默认开启兜底：很多 App（Chrome、Word、PDF 阅读器）AX 读不到选中文本
        return UserDefaults.standard.object(forKey: "clipboardFallback") as? Bool ?? true
    }

    private func clipboardFallback(at point: NSPoint) {
        guard !clipboardFallbackInFlight else { return }
        clipboardFallbackInFlight = true
        let pb = NSPasteboard.general
        let oldItems = pb.pasteboardItems?.compactMap { $0.string(forType: .string) }
        let oldChangeCount = pb.changeCount
        pb.clearContents()
        // 模拟 Cmd+C
        let src = CGEventSource(stateID: .hidSystemState)
        let keyDown = CGEvent(keyboardEventSource: src, virtualKey: 0x08, keyDown: true) // C
        keyDown?.flags = .maskCommand
        let keyUp = CGEvent(keyboardEventSource: src, virtualKey: 0x08, keyDown: false)
        keyUp?.flags = .maskCommand
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            defer { self?.clipboardFallbackInFlight = false }
            guard pb.changeCount != oldChangeCount,
                  let s = pb.string(forType: .string),
                  !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                // 没复制到新内容，把旧剪贴板恢复
                if let old = oldItems?.first {
                    pb.clearContents()
                    pb.setString(old, forType: .string)
                }
                return
            }
            // 复制成功：剪贴板就留着新内容（用户刚按了复制，符合直觉），直接翻译
            self?.deliver(s, at: point)
        }
    }

    static func checkAccessibilityPermission() -> Bool {
        // AXIsProcessTrustedWithOptions 会弹系统授权框
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        return AXIsProcessTrustedWithOptions(options)
    }
}

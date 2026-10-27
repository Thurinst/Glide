import AppKit
import Carbon

/// 全局快捷键动作。keyCode 是 macOS 虚拟键码：A=0、S=1、D=2。
enum HotkeyAction: String, CaseIterable {
    case selection    // 划词翻译
    case input        // 输入翻译（打开主窗口）
    case screenshot   // 截图翻译
    case silentOCR    // 静默 OCR（框选识别进剪贴板）

    var title: String {
        switch self {
        case .selection: return "划词翻译"
        case .input: return "输入翻译（主窗口）"
        case .screenshot: return "截图翻译"
        case .silentOCR: return "静默 OCR"
        }
    }

    var defaultKeyCode: UInt16 {
        switch self {
        case .selection: return 2   // D
        case .input: return 0       // A
        case .screenshot: return 1  // S
        case .silentOCR: return 1   // S
        }
    }

    var defaultModifiers: NSEvent.ModifierFlags {
        switch self {
        case .silentOCR: return [.option, .shift]
        default: return [.option]
        }
    }
}

/// 全局快捷键：Carbon RegisterEventHotKey。
/// 不需要辅助功能权限（系统级热键注册），临时签名重编后也不受 TCC 影响。
/// 之前用的 NSEvent 全局监听需要辅助功能权限，且临时签名每次重编都会丢授权，故改走 Carbon。
final class HotkeyManager {
    static let shared = HotkeyManager()
    var onAction: ((HotkeyAction) -> Void)?
    private var refs: [HotkeyAction: EventHotKeyRef] = [:]
    private var handlerInstalled = false

    private static let signature = OSType(0x57475446) // 'WGTF'

    func start() {
        installHandlerIfNeeded()
        reload()
    }

    /// 设置里改了组合键后调用：注销旧的，按新设置重注册
    func reload() {
        for ref in refs.values { UnregisterEventHotKey(ref) }
        refs.removeAll()
        installHandlerIfNeeded()
        for (index, action) in HotkeyAction.allCases.enumerated() {
            let (code, mods) = TranslateSettings.shared.hotkey(for: action)
            var ref: EventHotKeyRef?
            let hotKeyID = EventHotKeyID(signature: Self.signature, id: UInt32(index + 1))
            let status = RegisterEventHotKey(UInt32(code), carbonModifiers(mods), hotKeyID,
                                             GetApplicationEventTarget(), 0, &ref)
            if status == noErr, let ref { refs[action] = ref }
        }
    }

    func stop() {
        for ref in refs.values { UnregisterEventHotKey(ref) }
        refs.removeAll()
    }

    private func carbonModifiers(_ mods: NSEvent.ModifierFlags) -> UInt32 {
        var out: UInt32 = 0
        if mods.contains(.command) { out |= UInt32(cmdKey) }
        if mods.contains(.option) { out |= UInt32(optionKey) }
        if mods.contains(.control) { out |= UInt32(controlKey) }
        if mods.contains(.shift) { out |= UInt32(shiftKey) }
        return out
    }

    private func installHandlerIfNeeded() {
        guard !handlerInstalled else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        let status = InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
            var hotKeyID = EventHotKeyID()
            let err = GetEventParameter(event, EventParamName(kEventParamDirectObject),
                                        EventParamType(typeEventHotKeyID), nil,
                                        MemoryLayout<EventHotKeyID>.size, nil, &hotKeyID)
            if err == noErr {
                let index = Int(hotKeyID.id) - 1
                if HotkeyAction.allCases.indices.contains(index) {
                    HotkeyManager.shared.onAction?(HotkeyAction.allCases[index])
                }
            }
            return noErr
        }, 1, &spec, nil, nil)
        if status == noErr { handlerInstalled = true }
    }
}

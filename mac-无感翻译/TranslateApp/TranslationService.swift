import Foundation
import AppKit

// MARK: - 翻译引擎
enum TranslateEngine: String, CaseIterable {
    case googleFree = "googleFree"      // 免费，无需 Key，默认
    case openAI = "openAI"              // OpenAI / 兼容接口（ChatGPT、DeepSeek、通义、Gemini兼容等）
    case deepL = "deepL"                // DeepL API Free / Pro

    var displayName: String {
        switch self {
        case .googleFree: return "Google 免费机翻（无需 Key）"
        case .openAI: return "AI 大模型（OpenAI 兼容接口）"
        case .deepL: return "DeepL API"
        }
    }
}

enum TranslateError: LocalizedError {
    case emptyText
    case network(Error)
    case badResponse
    case apiError(String)
    case missingKey

    var errorDescription: String? {
        switch self {
        case .emptyText: return "没有要翻译的文本"
        case .network(let e): return "网络错误：\(e.localizedDescription)"
        case .badResponse: return "翻译服务返回异常"
        case .apiError(let s): return s
        case .missingKey: return "请先在设置里填写 API Key"
        }
    }
}

/// 设置，存在 UserDefaults，设置窗口和翻译服务共用
/// 无可变内存状态（全部走线程安全的 UserDefaults），可跨并发上下文使用
final class TranslateSettings: @unchecked Sendable {
    static let shared = TranslateSettings()
    private let d = UserDefaults.standard

    var engine: TranslateEngine {
        get { TranslateEngine(rawValue: d.string(forKey: "engine") ?? "") ?? .googleFree }
        set { d.set(newValue.rawValue, forKey: "engine") }
    }
    /// OpenAI 兼容：如 https://api.openai.com/v1 ，DeepSeek: https://api.deepseek.com/v1
    var apiBaseURL: String {
        get { d.string(forKey: "apiBaseURL") ?? "https://api.openai.com/v1" }
        set { d.set(newValue, forKey: "apiBaseURL") }
    }
    var apiKey: String {
        get { d.string(forKey: "apiKey") ?? "" }
        set { d.set(newValue, forKey: "apiKey") }
    }
    var model: String {
        get { d.string(forKey: "model") ?? "gpt-4o-mini" }
        set { d.set(newValue, forKey: "model") }
    }
    var deepLKey: String {
        get { d.string(forKey: "deepLKey") ?? "" }
        set { d.set(newValue, forKey: "deepLKey") }
    }
    var autoDetect: Bool {
        get { d.object(forKey: "autoDetect") as? Bool ?? true }
        set { d.set(newValue, forKey: "autoDetect") }
    }
    /// 固定目标语言，auto 时自动判断：含中文 -> 英文，否则 -> 中文
    var fixedTarget: String {
        get { d.string(forKey: "fixedTarget") ?? "auto" }
        set { d.set(newValue, forKey: "fixedTarget") }
    }
    var autoTranslateOnSelect: Bool {
        get { d.object(forKey: "autoTranslateOnSelect") as? Bool ?? true }
        set { d.set(newValue, forKey: "autoTranslateOnSelect") }
    }
    var showOriginal: Bool {
        get { d.object(forKey: "showOriginal") as? Bool ?? true }
        set { d.set(newValue, forKey: "showOriginal") }
    }
    // MARK: v2 新增
    var launchAtLogin: Bool {
        get { d.object(forKey: "launchAtLogin") as? Bool ?? false }
        set { d.set(newValue, forKey: "launchAtLogin") }
    }
    /// 翻译完成后自动朗读译文
    var autoSpeak: Bool {
        get { d.object(forKey: "autoSpeak") as? Bool ?? false }
        set { d.set(newValue, forKey: "autoSpeak") }
    }
    /// 剪贴板监听：复制文字后自动翻译出悬浮窗
    var clipboardWatch: Bool {
        get { d.object(forKey: "clipboardWatch") as? Bool ?? true }
        set { d.set(newValue, forKey: "clipboardWatch") }
    }
    /// 划词后先浮小「译」图标，点一下才翻译；关掉则恢复选中即弹窗
    var showPopButton: Bool {
        get { d.object(forKey: "showPopButton") as? Bool ?? true }
        set { d.set(newValue, forKey: "showPopButton") }
    }
    /// 主窗口源语言：auto / zh / en
    var fixedSource: String {
        get { d.string(forKey: "fixedSource") ?? "auto" }
        set { d.set(newValue, forKey: "fixedSource") }
    }
    /// 多引擎对照：各引擎是否参与并行查询（Google 免费默认开）
    func isEngineEnabled(_ engine: TranslateEngine) -> Bool {
        d.object(forKey: "engineEnabled_\(engine.rawValue)") as? Bool ?? true
    }
    func setEngineEnabled(_ enabled: Bool, for engine: TranslateEngine) {
        d.set(enabled, forKey: "engineEnabled_\(engine.rawValue)")
    }
    // MARK: 快捷键：存 "keyCode,modifierRawValue"，如 "2,524288" = ⌥D
    func hotkey(for action: HotkeyAction) -> (keyCode: UInt16, modifiers: NSEvent.ModifierFlags) {
        if let s = d.string(forKey: "hotkey_\(action.rawValue)") {
            let parts = s.split(separator: ",")
            if parts.count == 2, let code = UInt16(parts[0]), let raw = UInt(parts[1]) {
                return (code, NSEvent.ModifierFlags(rawValue: raw))
            }
        }
        return (action.defaultKeyCode, action.defaultModifiers)
    }
    func setHotkey(_ keyCode: UInt16, modifiers: NSEvent.ModifierFlags, for action: HotkeyAction) {
        d.set("\(keyCode),\(modifiers.rawValue)", forKey: "hotkey_\(action.rawValue)")
    }
    /// 快捷键显示，如 "⌥D"、"⌥⇧S"
    func hotkeyDescription(for action: HotkeyAction) -> String {
        let (code, mods) = hotkey(for: action)
        let keyNames: [UInt16: String] = [
            0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X", 8: "C", 9: "V",
            11: "B", 12: "Q", 13: "W", 14: "E", 15: "R", 16: "Y", 17: "T", 18: "1", 19: "2",
            20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
            29: "0", 30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P", 36: "⏎", 37: "L",
            38: "J", 39: "'", 40: "K", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "N", 46: "M",
            47: ".", 49: "空格", 53: "Esc",
        ]
        var s = ""
        if mods.contains(.control) { s += "⌃" }
        if mods.contains(.option) { s += "⌥" }
        if mods.contains(.shift) { s += "⇧" }
        if mods.contains(.command) { s += "⌘" }
        s += keyNames[code] ?? "键\(code)"
        return s
    }
}

/// 无可变内存状态（全部走 UserDefaults / URLSession），可跨并发上下文使用
final class TranslationService: @unchecked Sendable {
    static let shared = TranslationService()
    private init() {}

    func targetLanguage(for text: String) -> String {
        let s = TranslateSettings.shared
        if s.fixedTarget != "auto" { return s.fixedTarget }
        // 含中文字符 -> 译成英文，否则译成中文
        let hasChinese = text.unicodeScalars.contains { (0x4E00...0x9FFF).contains($0.value) }
        return hasChinese ? "en" : "zh-CN"
    }

    /// 语言检测：含中文 -> zh，否则 -> en
    func detectLanguage(of text: String) -> String {
        let hasChinese = text.unicodeScalars.contains { (0x4E00...0x9FFF).contains($0.value) }
        return hasChinese ? "zh" : "en"
    }

    func translate(_ text: String) async throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw TranslateError.emptyText }
        // 太长截断，避免免费接口报错；弹窗场景一般都是短句
        let input = String(trimmed.prefix(5000))
        let target = targetLanguage(for: input)
        let normalizedTarget = target == "zh-CN" ? "zh" : target
        // 润色模式：源语言与目标语言相同时走 AI 润色（有 Key 才行）
        if normalizedTarget == detectLanguage(of: input) {
            guard !TranslateSettings.shared.apiKey.isEmpty else {
                throw TranslateError.apiError("源语言与目标语言相同，已切换为润色模式，请先在设置 → 翻译服务里填写 AI API Key")
            }
            return try await polish(input)
        }
        return try await translate(input, source: "auto", target: target, engine: TranslateSettings.shared.engine)
    }

    /// 指定源/目标语言 + 指定引擎的翻译（多引擎对照和主窗口用）。
    /// source/target 取 "auto" / "zh" / "en"；Google 的 target 内部再转 zh-CN。
    func translate(_ text: String, source: String, target: String, engine: TranslateEngine) async throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw TranslateError.emptyText }
        let input = String(trimmed.prefix(5000))
        switch engine {
        case .googleFree:
            return try await googleTranslate(input, source: source, target: target)
        case .openAI:
            return try await openAITranslate(input, source: source, target: target)
        case .deepL:
            return try await deepLTranslate(input, source: source, target: target)
        }
    }

    /// 多引擎并行对照：同时跑 Google 免费 + DeepL（有 Key）+ AI 大模型（有 Key），
    /// 结果按主引擎优先排序返回。某个引擎失败不影响其他引擎。
    func translateAllEngines(_ text: String, source: String, target: String) async -> [(engine: TranslateEngine, result: Result<String, Error>)] {
        var engines: [TranslateEngine] = []
        let s = TranslateSettings.shared
        if s.isEngineEnabled(.googleFree) { engines.append(.googleFree) }
        if s.isEngineEnabled(.deepL), !s.deepLKey.isEmpty { engines.append(.deepL) }
        if s.isEngineEnabled(.openAI), !s.apiKey.isEmpty { engines.append(.openAI) }
        if engines.isEmpty { engines.append(.googleFree) }
        // 主引擎排第一
        engines.sort { (a: TranslateEngine, b: TranslateEngine) in
            if a == s.engine { return true }
            if b == s.engine { return false }
            return false
        }
        return await withTaskGroup(of: (TranslateEngine, Result<String, Error>).self) { group in
            for engine in engines {
                group.addTask { [engine] in
                    do {
                        let text = try await self.translate(text, source: source, target: target, engine: engine)
                        return (engine, .success(text))
                    } catch {
                        return (engine, .failure(error))
                    }
                }
            }
            var out: [(engine: TranslateEngine, result: Result<String, Error>)] = []
            for await item in group { out.append(item) }
            out.sort { (a: (engine: TranslateEngine, result: Result<String, Error>), b: (engine: TranslateEngine, result: Result<String, Error>)) in
                let ia = engines.firstIndex(of: a.engine) ?? Int.max
                let ib = engines.firstIndex(of: b.engine) ?? Int.max
                return ia < ib
            }
            return out
        }
    }

    /// 从并行结果里挑主结果：优先主引擎的成功结果，否则取第一个成功结果
    static func pickPrimary(from results: [(engine: TranslateEngine, result: Result<String, Error>)],
                            preferred: TranslateEngine) -> (engine: TranslateEngine, result: Result<String, Error>)? {
        for item in results where item.engine == preferred {
            if case .success = item.result { return item }
        }
        for item in results {
            if case .success = item.result { return item }
        }
        return results.first
    }

    /// AI 润色 / 语法纠错：源语言与目标语言相同时调用
    func polish(_ text: String) async throws -> String {
        let s = TranslateSettings.shared
        guard !s.apiKey.isEmpty else { throw TranslateError.missingKey }
        let lang = detectLanguage(of: text)
        let langName = lang == "zh" ? "Chinese" : "English"
        return try await openAIChat(
            system: "You are a professional editor. Proofread and polish the following \(langName) text: fix grammar, spelling and punctuation, improve fluency and style, but keep the original meaning and tone. Return ONLY the polished text, no explanation, no quotes.",
            user: text)
    }

    /// OpenAI 兼容接口的通用 chat 调用（翻译和润色共用）
    private func openAIChat(system: String, user: String) async throws -> String {
        let s = TranslateSettings.shared
        guard !s.apiKey.isEmpty else { throw TranslateError.missingKey }
        let base = s.apiBaseURL.trimmingCharacters(in: .init(charactersIn: "/"))
        guard let url = URL(string: "\(base)/chat/completions") else { throw TranslateError.badResponse }
        struct Msg: Codable { let role: String; let content: String }
        struct Req: Codable { let model: String; let messages: [Msg]; let temperature: Double }
        struct Resp: Codable {
            struct Choice: Codable { struct M: Codable { let content: String }; let message: M }
            let choices: [Choice]
        }
        let body = Req(model: s.model, messages: [
            Msg(role: "system", content: system),
            Msg(role: "user", content: user),
        ], temperature: 0.2)
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("Bearer \(s.apiKey)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
            let msg = String(data: data, encoding: .utf8) ?? ""
            throw TranslateError.apiError("API 返回 \(http.statusCode)：\(msg.prefix(300))")
        }
        let decoded = try JSONDecoder().decode(Resp.self, from: data)
        guard let out = decoded.choices.first?.message.content.trimmingCharacters(in: .whitespacesAndNewlines),
              !out.isEmpty else { throw TranslateError.badResponse }
        return out
    }

    // MARK: Google 免费（translate.googleapis.com，无需 Key）
    private func googleTranslate(_ text: String, source: String, target: String) async throws -> String {
        let tl = target == "en" ? "en" : "zh-CN"
        let sl = source == "auto" ? "auto" : (source == "en" ? "en" : "zh-CN")
        var comps = URLComponents(string: "https://translate.googleapis.com/translate_a/single")!
        comps.queryItems = [
            URLQueryItem(name: "client", value: "gtx"),
            URLQueryItem(name: "sl", value: sl),
            URLQueryItem(name: "tl", value: tl),
            URLQueryItem(name: "dt", value: "t"),
            URLQueryItem(name: "q", value: text),
        ]
        guard let url = comps.url else { throw TranslateError.badResponse }
        var req = URLRequest(url: url)
        req.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
        let (data, _) = try await URLSession.shared.data(for: req)
        // 返回是 JSON 数组：[[["译文","原文",...]],...]
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [Any],
              let sentences = json.first as? [[Any]] else {
            throw TranslateError.badResponse
        }
        let out = sentences.compactMap { $0.first as? String }.joined()
        guard !out.isEmpty else { throw TranslateError.badResponse }
        return out
    }

    // MARK: OpenAI 兼容接口
    private func openAITranslate(_ text: String, source: String, target: String) async throws -> String {
        let targetName = target == "en" ? "English" : "Simplified Chinese"
        let sourceName = source == "auto" ? "auto-detected language" : (source == "en" ? "English" : "Chinese")
        return try await openAIChat(
            system: "You are a professional translator. Translate the user text from \(sourceName) into \(targetName). Return ONLY the translation, no explanation, no quotes, no pinyin. Preserve line breaks and formatting.",
            user: text)
    }

    // MARK: DeepL
    private func deepLTranslate(_ text: String, source: String, target: String) async throws -> String {
        let s = TranslateSettings.shared
        guard !s.deepLKey.isEmpty else { throw TranslateError.missingKey }
        let tl = target == "en" ? "EN-US" : "ZH"
        // Free Key 以 :fx 结尾走 api-free，否则走 api
        let host = s.deepLKey.hasSuffix(":fx") ? "https://api-free.deepl.com" : "https://api.deepl.com"
        guard let url = URL(string: "\(host)/v2/translate") else { throw TranslateError.badResponse }
        var items = [
            URLQueryItem(name: "auth_key", value: s.deepLKey),
            URLQueryItem(name: "text", value: text),
            URLQueryItem(name: "target_lang", value: tl),
        ]
        if source != "auto" {
            items.append(URLQueryItem(name: "source_lang", value: source == "en" ? "EN" : "ZH"))
        }
        var comps = URLComponents()
        comps.queryItems = items
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.httpBody = comps.percentEncodedQuery?.data(using: .utf8)
        let (data, resp) = try await URLSession.shared.data(for: req)
        if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
            throw TranslateError.apiError("DeepL 返回 \(http.statusCode)")
        }
        struct Resp: Codable { struct T: Codable { let text: String }; let translations: [T] }
        let decoded = try JSONDecoder().decode(Resp.self, from: data)
        guard let out = decoded.translations.first?.text else { throw TranslateError.badResponse }
        return out
    }
}

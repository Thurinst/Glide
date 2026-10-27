import AppKit
import AVFoundation
import UniformTypeIdentifiers

/// 主窗口：输入翻译工作台。
/// 左侧历史记录（搜索 / 收藏 / 删除 / 导出），右侧原文输入 + 源/目标语言切换 + 译文区 + 其他引擎对照。
/// 源语言与目标语言相同时自动走 AI 润色模式（需填 AI Key）。
final class MainWindowController: NSWindowController, NSTableViewDataSource, NSTableViewDelegate, NSControlTextEditingDelegate, NSSearchFieldDelegate {

    private let inputView = NSTextView()
    private let outputView = NSTextView()
    private let sourcePopup = NSPopUpButton()
    private let targetPopup = NSPopUpButton()
    private let translateButton = NSButton(title: "翻译", target: nil, action: nil)
    private let statusLabel = NSTextField(labelWithString: "")
    private let alternatesLabel = NSTextField(labelWithString: "")
    private let polishHintLabel = NSTextField(labelWithString: "")
    private let historyTable = NSTableView()
    private let searchField = NSSearchField()
    private var filtered: [HistoryRecord] = []
    private var task: Task<Void, Never>?
    private let synthesizer = AVSpeechSynthesizer()

    convenience init() {
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 920, height: 620),
                           styleMask: [.titled, .closable, .miniaturizable, .resizable],
                           backing: .buffered, defer: false)
        win.title = "无感翻译"
        win.minSize = NSSize(width: 720, height: 480)
        win.center()
        self.init(window: win)
        buildUI()
        reloadHistory()
        updatePolishHint()
    }

    // MARK: UI

    private func buildUI() {
        guard let content = window?.contentView else { return }

        // ---- 左侧：历史记录 ----
        searchField.placeholderString = "搜索历史记录…"
        searchField.delegate = self
        searchField.translatesAutoresizingMaskIntoConstraints = false

        historyTable.addTableColumn(NSTableColumn(identifier: NSUserInterfaceItemIdentifier("HistoryColumn")))
        historyTable.headerView = nil
        historyTable.rowHeight = 34
        historyTable.delegate = self
        historyTable.dataSource = self
        let tableScroll = NSScrollView()
        tableScroll.documentView = historyTable
        tableScroll.hasVerticalScroller = true
        tableScroll.translatesAutoresizingMaskIntoConstraints = false

        let favButton = NSButton(title: "★ 收藏", target: self, action: #selector(toggleFavoriteSelected))
        favButton.bezelStyle = .rounded
        favButton.controlSize = .small
        let delButton = NSButton(title: "删除", target: self, action: #selector(deleteSelected))
        delButton.bezelStyle = .rounded
        delButton.controlSize = .small
        let csvButton = NSButton(title: "导出 CSV", target: self, action: #selector(exportCSV))
        csvButton.bezelStyle = .rounded
        csvButton.controlSize = .small
        let ankiButton = NSButton(title: "导出 Anki", target: self, action: #selector(exportAnki))
        ankiButton.bezelStyle = .rounded
        ankiButton.controlSize = .small
        let historyButtons = NSStackView(views: [favButton, delButton, csvButton, ankiButton])
        historyButtons.orientation = .horizontal
        historyButtons.spacing = 6
        historyButtons.translatesAutoresizingMaskIntoConstraints = false

        let historyStack = NSStackView(views: [searchField, tableScroll, historyButtons])
        historyStack.orientation = .vertical
        historyStack.spacing = 8
        historyStack.translatesAutoresizingMaskIntoConstraints = false

        // ---- 右侧：翻译工作台 ----
        sourcePopup.addItems(withTitles: ["自动检测", "中文", "英文"])
        let savedSource = TranslateSettings.shared.fixedSource
        sourcePopup.selectItem(at: savedSource == "zh" ? 1 : (savedSource == "en" ? 2 : 0))
        sourcePopup.target = self
        sourcePopup.action = #selector(languageChanged)
        targetPopup.addItems(withTitles: ["中文", "英文"])
        targetPopup.selectItem(at: 0)
        targetPopup.target = self
        targetPopup.action = #selector(languageChanged)
        let swapButton = NSButton(title: "⇄", target: self, action: #selector(swapLanguages))
        swapButton.bezelStyle = .circular
        swapButton.toolTip = "互换源语言和目标语言"
        swapButton.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            swapButton.widthAnchor.constraint(equalToConstant: 28),
            swapButton.heightAnchor.constraint(equalToConstant: 28),
        ])

        let langRow = NSStackView(views: [sourcePopup, swapButton, targetPopup])
        langRow.orientation = .horizontal
        langRow.alignment = .centerY
        langRow.spacing = 8
        langRow.translatesAutoresizingMaskIntoConstraints = false

        inputView.font = .systemFont(ofSize: 14)
        inputView.isRichText = false
        inputView.allowsUndo = true
        let inputScroll = NSScrollView()
        inputScroll.documentView = inputView
        inputScroll.hasVerticalScroller = true
        inputScroll.borderType = .bezelBorder
        inputScroll.translatesAutoresizingMaskIntoConstraints = false

        outputView.font = .systemFont(ofSize: 14)
        outputView.isRichText = false
        outputView.isEditable = false
        outputView.isSelectable = true
        let outputScroll = NSScrollView()
        outputScroll.documentView = outputView
        outputScroll.hasVerticalScroller = true
        outputScroll.borderType = .bezelBorder
        outputScroll.translatesAutoresizingMaskIntoConstraints = false

        polishHintLabel.font = .systemFont(ofSize: 11)
        polishHintLabel.textColor = .controlAccentColor
        polishHintLabel.translatesAutoresizingMaskIntoConstraints = false

        alternatesLabel.font = .systemFont(ofSize: 12)
        alternatesLabel.textColor = .secondaryLabelColor
        alternatesLabel.lineBreakMode = .byWordWrapping
        alternatesLabel.usesSingleLineMode = false
        alternatesLabel.cell?.wraps = true
        alternatesLabel.translatesAutoresizingMaskIntoConstraints = false

        translateButton.bezelStyle = .rounded
        translateButton.target = self
        translateButton.action = #selector(doTranslate)
        translateButton.keyEquivalent = "\r"
        let copyButton = NSButton(title: "复制译文", target: self, action: #selector(copyOutput))
        copyButton.bezelStyle = .rounded
        let speakButton = NSButton(title: "朗读", target: self, action: #selector(speakOutput))
        speakButton.bezelStyle = .rounded
        let actionRow = NSStackView(views: [translateButton, copyButton, speakButton])
        actionRow.orientation = .horizontal
        actionRow.alignment = .centerY
        actionRow.spacing = 8
        actionRow.translatesAutoresizingMaskIntoConstraints = false

        statusLabel.font = .systemFont(ofSize: 11)
        statusLabel.textColor = .tertiaryLabelColor
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let mainStack = NSStackView(views: [langRow, polishHintLabel, inputScroll, outputScroll, alternatesLabel, actionRow, statusLabel])
        mainStack.orientation = .vertical
        mainStack.alignment = .leading
        mainStack.spacing = 8
        mainStack.translatesAutoresizingMaskIntoConstraints = false
        mainStack.setCustomSpacing(2, after: langRow)
        mainStack.setCustomSpacing(4, after: inputScroll)
        mainStack.setCustomSpacing(4, after: outputScroll)

        let divider = NSBox()
        divider.boxType = .separator
        divider.translatesAutoresizingMaskIntoConstraints = false

        let root = NSStackView(views: [historyStack, divider, mainStack])
        root.orientation = .horizontal
        root.spacing = 12
        root.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(root)
        NSLayoutConstraint.activate([
            root.topAnchor.constraint(equalTo: content.topAnchor, constant: 16),
            root.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            root.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),
            root.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -16),
            historyStack.widthAnchor.constraint(equalToConstant: 240),
            historyStack.topAnchor.constraint(equalTo: root.topAnchor),
            historyStack.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            divider.widthAnchor.constraint(equalToConstant: 1),
            divider.heightAnchor.constraint(equalTo: root.heightAnchor),
            mainStack.topAnchor.constraint(equalTo: root.topAnchor),
            mainStack.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            inputScroll.heightAnchor.constraint(equalToConstant: 150),
            outputScroll.heightAnchor.constraint(equalToConstant: 150),
        ])
    }

    // MARK: 语言

    private func selectedSource() -> String {
        switch sourcePopup.indexOfSelectedItem {
        case 1: return "zh"
        case 2: return "en"
        default: return "auto"
        }
    }

    private func selectedTarget() -> String {
        targetPopup.indexOfSelectedItem == 1 ? "en" : "zh"
    }

    @objc private func languageChanged() {
        TranslateSettings.shared.fixedSource = selectedSource()
        updatePolishHint()
    }

    private func updatePolishHint() {
        let src = selectedSource()
        let dst = selectedTarget()
        let isPolish = src != "auto" && src == dst
        polishHintLabel.stringValue = isPolish ? "润色模式：源语言与目标语言相同，将使用 AI 大模型润色 / 纠错（需在设置里填 AI Key）" : ""
        translateButton.title = isPolish ? "润色" : "翻译"
    }

    @objc private func swapLanguages() {
        let oldSource = sourcePopup.indexOfSelectedItem   // 0 自动，1 中文，2 英文
        let oldTarget = targetPopup.indexOfSelectedItem   // 0 中文，1 英文
        let newTarget = oldSource == 0 ? (oldTarget == 0 ? 1 : 0) : (oldSource == 1 ? 0 : 1)
        let newSource = oldTarget == 0 ? 1 : 2
        sourcePopup.selectItem(at: newSource)
        targetPopup.selectItem(at: newTarget)
        updatePolishHint()
    }

    // MARK: 翻译

    @objc private func doTranslate() {
        let text = inputView.string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let source = selectedSource()
        let target = selectedTarget()
        let resolvedSource = source == "auto" ? TranslationService.shared.detectLanguage(of: text) : source
        let isPolish = resolvedSource == target

        translateButton.isEnabled = false
        statusLabel.stringValue = isPolish ? "正在润色…" : "正在翻译…"
        alternatesLabel.stringValue = ""
        task?.cancel()
        task = Task { [weak self] in
            guard let self = self else { return }
            let results: [(engine: TranslateEngine, result: Result<String, Error>)]
            if isPolish {
                do {
                    let polished = try await TranslationService.shared.polish(text)
                    results = [(.openAI, .success(polished))]
                } catch {
                    results = [(.openAI, .failure(error))]
                }
            } else {
                results = await TranslationService.shared.translateAllEngines(text, source: source, target: target)
            }
            if Task.isCancelled { return }
            await MainActor.run {
                self.translateButton.isEnabled = true
                let primary = TranslationService.pickPrimary(from: results, preferred: TranslateSettings.shared.engine)
                guard let primary = primary else {
                    self.statusLabel.stringValue = "没有可用的翻译引擎"
                    return
                }
                switch primary.result {
                case .success(let translated):
                    self.outputView.string = translated
                    self.statusLabel.stringValue = isPolish ? "润色完成（AI 大模型）" : "翻译完成（\(primary.engine.displayName)）"
                    HistoryStore.shared.add(source: text, translation: translated, engine: isPolish ? "AI 润色" : primary.engine.displayName)
                    self.reloadHistory()
                    let alternates = results.filter { $0.engine != primary.engine }.compactMap { item -> String? in
                        if case .success(let value) = item.result { return "\(item.engine.displayName)：\(value)" }
                        return nil
                    }
                    self.alternatesLabel.stringValue = alternates.joined(separator: "\n")
                    if TranslateSettings.shared.autoSpeak { self.speakOutput() }
                case .failure(let error):
                    self.outputView.string = ""
                    self.statusLabel.stringValue = "翻译失败：\(error.localizedDescription)"
                }
            }
        }
    }

    @objc private func copyOutput() {
        guard !outputView.string.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(outputView.string, forType: .string)
        statusLabel.stringValue = "已复制译文"
    }

    @objc private func speakOutput() {
        guard !outputView.string.isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)
        let utter = AVSpeechUtterance(string: outputView.string)
        utter.voice = AVSpeechSynthesisVoice(language: selectedTarget() == "en" ? "en-US" : "zh-CN")
        utter.rate = 0.5
        synthesizer.speak(utter)
    }

    /// 供 AppDelegate 调用：从外部打开主窗口并填入待翻译文本
    func openWithText(_ text: String) {
        showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
        inputView.string = text
        doTranslate()
    }

    // MARK: 历史记录

    func reloadHistory() {
        filtered = HistoryStore.shared.search(searchField.stringValue)
        historyTable.reloadData()
    }

    func numberOfRows(in tableView: NSTableView) -> Int { filtered.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let cellID = NSUserInterfaceItemIdentifier("HistoryCell")
        var cell = tableView.makeView(withIdentifier: cellID, owner: self) as? NSTableCellView
        if cell == nil {
            cell = NSTableCellView()
            cell?.identifier = cellID
            let tf = NSTextField(labelWithString: "")
            tf.font = .systemFont(ofSize: 12)
            tf.lineBreakMode = .byTruncatingTail
            tf.translatesAutoresizingMaskIntoConstraints = false
            cell?.addSubview(tf)
            cell?.textField = tf
            NSLayoutConstraint.activate([
                tf.leadingAnchor.constraint(equalTo: cell!.leadingAnchor, constant: 4),
                tf.trailingAnchor.constraint(equalTo: cell!.trailingAnchor, constant: -4),
                tf.centerYAnchor.constraint(equalTo: cell!.centerYAnchor),
            ])
        }
        let record = filtered[row]
        cell?.textField?.stringValue = (record.favorite ? "★ " : "") + record.source.replacingOccurrences(of: "\n", with: " ")
        cell?.toolTip = record.source
        return cell
    }

    func tableViewSelectionDidChange(_ notification: Notification) {
        let row = historyTable.selectedRow
        guard row >= 0, row < filtered.count else { return }
        let record = filtered[row]
        inputView.string = record.source
        outputView.string = record.translation
        statusLabel.stringValue = "来自历史记录（\(record.engine)）"
    }

    func controlTextDidChange(_ obj: Notification) {
        reloadHistory()
    }

    @objc private func toggleFavoriteSelected() {
        let row = historyTable.selectedRow
        guard row >= 0, row < filtered.count else { return }
        HistoryStore.shared.toggleFavorite(id: filtered[row].id)
        reloadHistory()
    }

    @objc private func deleteSelected() {
        let row = historyTable.selectedRow
        guard row >= 0, row < filtered.count else { return }
        HistoryStore.shared.delete(id: filtered[row].id)
        reloadHistory()
    }

    // MARK: 导出

    private func exportText(_ text: String, suggestedName: String, fileType: UTType) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedName
        panel.allowedContentTypes = [fileType]
        panel.beginSheetModal(for: window!) { response in
            guard response == .OK, let url = panel.url else { return }
            try? text.write(to: url, atomically: true, encoding: .utf8)
        }
    }

    @objc private func exportCSV() {
        exportText(HistoryStore.shared.exportCSV(), suggestedName: "无感翻译-历史记录.csv", fileType: .commaSeparatedText)
    }

    @objc private func exportAnki() {
        exportText(HistoryStore.shared.exportAnki(), suggestedName: "无感翻译-生词本.txt", fileType: .plainText)
    }
}

import Foundation

/// 一条翻译记录
struct HistoryRecord: Codable, Identifiable {
    var id: UUID
    var source: String
    var translation: String
    var engine: String
    var date: Date
    var favorite: Bool

    init(source: String, translation: String, engine: String) {
        self.id = UUID()
        self.source = source
        self.translation = translation
        self.engine = engine
        self.date = Date()
        self.favorite = false
    }
}

/// 历史记录 + 生词本（收藏）：存 ~/Library/Application Support/无感翻译/history.json，上限 500 条
final class HistoryStore {
    static let shared = HistoryStore()
    static let maxRecords = 500

    private let fileURL: URL
    private(set) var records: [HistoryRecord] = []

    private init() {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            .appendingPathComponent("无感翻译", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        fileURL = dir.appendingPathComponent("history.json")
        load()
    }

    private func load() {
        guard let data = try? Data(contentsOf: fileURL),
              let decoded = try? JSONDecoder().decode([HistoryRecord].self, from: data) else { return }
        records = decoded
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(records) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }

    /// 新记录插到最前面；相同原文去重（删旧的再插）
    func add(source: String, translation: String, engine: String) {
        let trimmed = source.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !translation.isEmpty else { return }
        records.removeAll { $0.source == trimmed }
        records.insert(HistoryRecord(source: trimmed, translation: translation, engine: engine), at: 0)
        if records.count > HistoryStore.maxRecords {
            records = Array(records.prefix(HistoryStore.maxRecords))
        }
        save()
    }

    func toggleFavorite(id: UUID) {
        guard let i = records.firstIndex(where: { $0.id == id }) else { return }
        records[i].favorite.toggle()
        save()
    }

    func delete(id: UUID) {
        records.removeAll { $0.id == id }
        save()
    }

    func clear() {
        records.removeAll()
        save()
    }

    func favorites() -> [HistoryRecord] {
        records.filter { $0.favorite }
    }

    func search(_ query: String) -> [HistoryRecord] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return records }
        return records.filter {
            $0.source.localizedCaseInsensitiveContains(q) ||
            $0.translation.localizedCaseInsensitiveContains(q)
        }
    }

    // MARK: 导出

    private func csvEscape(_ s: String) -> String {
        if s.contains(",") || s.contains("\"") || s.contains("\n") {
            return "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        return s
    }

    func exportCSV() -> String {
        var lines = ["原文,译文,引擎,时间,收藏"]
        let fmt = ISO8601DateFormatter()
        for r in records {
            lines.append([
                csvEscape(r.source),
                csvEscape(r.translation),
                csvEscape(r.engine),
                fmt.string(from: r.date),
                r.favorite ? "是" : "否",
            ].joined(separator: ","))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    /// Anki 导入格式：制表符分隔，制表符/换行先替换为空格
    func exportAnki() -> String {
        var lines: [String] = []
        for r in records {
            let src = r.source.replacingOccurrences(of: "\t", with: " ").replacingOccurrences(of: "\n", with: " ")
            let dst = r.translation.replacingOccurrences(of: "\t", with: " ").replacingOccurrences(of: "\n", with: " ")
            lines.append(src + "\t" + dst)
        }
        return lines.joined(separator: "\n") + "\n"
    }
}

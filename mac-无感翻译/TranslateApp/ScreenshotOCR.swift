import AppKit
import Vision

/// 截图 OCR 选区遮罩：全屏半透明黑底，鼠标拖框选区，松开后截取该区域。
private final class ScreenshotSelectionView: NSView {
    var onSelection: ((NSRect) -> Void)?
    private var startPoint: NSPoint?
    private var currentPoint: NSPoint?

    override func mouseDown(with event: NSEvent) {
        startPoint = convert(event.locationInWindow, from: nil)
        currentPoint = startPoint
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        currentPoint = convert(event.locationInWindow, from: nil)
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        guard let s = startPoint else { return }
        let e = convert(event.locationInWindow, from: nil)
        let rect = NSRect(x: min(s.x, e.x), y: min(s.y, e.y),
                          width: abs(e.x - s.x), height: abs(e.y - s.y))
        startPoint = nil
        currentPoint = nil
        needsDisplay = true
        // 框太小当作误点，直接取消
        guard rect.width >= 10, rect.height >= 10 else { return }
        onSelection?(rect)
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.withAlphaComponent(0.35).setFill()
        dirtyRect.fill()
        guard let s = startPoint, let c = currentPoint else { return }
        let rect = NSRect(x: min(s.x, c.x), y: min(s.y, c.y),
                          width: abs(c.x - s.x), height: abs(c.y - s.y))
        NSColor.clear.setFill()
        rect.fill(using: .clear)
        NSColor.controlAccentColor.setStroke()
        let path = NSBezierPath(rect: rect)
        path.lineWidth = 1.5
        path.stroke()
    }
}

/// 全屏遮罩窗：无边框、可成为 key 窗口以接收鼠标事件
private final class ScreenshotOverlayWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

/// 截图 OCR：⌥S 框选识别后翻译出悬浮窗；⌥⇧S 静默识别，文字直接进剪贴板。
/// Vision VNRecognizeTextRequest 离线识别（中英文），在后台线程跑，识别完回主线程回调。
final class ScreenshotOCR {
    static let shared = ScreenshotOCR()

    /// 非静默模式：识别到文字后回调（文字，选区屏幕坐标），由 AppDelegate 翻译并弹窗
    var onTextRecognized: ((String, NSRect) -> Void)?
    /// 静默模式：识别到文字后回调（只进剪贴板，不弹窗）
    var onSilentText: ((String) -> Void)?
    /// 识别失败回调（非静默时在悬浮窗内提示）
    var onError: ((String) -> Void)?

    private var overlay: ScreenshotOverlayWindow?
    private var escMonitor: Any?

    func start(silent: Bool) {
        // 选在鼠标所在的屏幕
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { $0.frame.contains(mouse) } ?? NSScreen.main
        guard let screen = screen else { return }

        let win = ScreenshotOverlayWindow(contentRect: screen.frame,
                                          styleMask: [.borderless],
                                          backing: .buffered, defer: false)
        win.level = .screenSaver
        win.isOpaque = false
        win.backgroundColor = .clear
        win.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        win.isReleasedWhenClosed = false

        let view = ScreenshotSelectionView(frame: NSRect(origin: .zero, size: screen.frame.size))
        view.onSelection = { [weak self] rect in
            self?.finishSelection(rect, on: screen, silent: silent)
        }
        win.contentView = view
        overlay = win
        NSApp.activate(ignoringOtherApps: true)
        win.makeKeyAndOrderFront(nil)
        // Esc 取消：只在遮罩存活期间监听，结束后立即移除，避免一直吞掉 Esc
        escMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 { // Esc
                self?.cancel()
                return nil
            }
            return event
        }
    }

    private func removeEscMonitor() {
        if let m = escMonitor { NSEvent.removeMonitor(m) }
        escMonitor = nil
    }

    func cancel() {
        removeEscMonitor()
        overlay?.orderOut(nil)
        overlay = nil
    }

    private func finishSelection(_ rect: NSRect, on screen: NSScreen, silent: Bool) {
        removeEscMonitor()
        overlay?.orderOut(nil)
        overlay = nil
        // 等遮罩完全消失再截图，避免把遮罩本身截进去
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            guard let self = self else { return }
            // 选区坐标换算到 CG 屏幕坐标：窗口原点在屏幕原点，视图坐标与 CG 坐标一致（左下原点）
            let cgRect = CGRect(x: screen.frame.origin.x + rect.origin.x,
                                y: screen.frame.origin.y + rect.origin.y,
                                width: rect.width, height: rect.height)
            guard let image = CGWindowListCreateImage(cgRect, .optionOnScreenOnly, kCGNullWindowID, .bestResolution) else {
                if !silent { self.onError?("截图失败，请重试") }
                return
            }
            self.recognize(image: image) { [weak self] text in
                guard let self = self else { return }
                guard let text = text, !text.isEmpty else {
                    if !silent { self.onError?("没有识别到文字，请换个区域再试") }
                    return
                }
                if silent {
                    self.onSilentText?(text)
                } else {
                    // 选区换算成屏幕坐标（多显示器时窗口原点不在 0,0），供悬浮窗定位
                    let screenRect = NSRect(x: screen.frame.origin.x + rect.origin.x,
                                            y: screen.frame.origin.y + rect.origin.y,
                                            width: rect.width, height: rect.height)
                    self.onTextRecognized?(text, screenRect)
                }
            }
        }
    }

    /// Vision 离线文字识别：后台线程跑请求，结果回主线程
    func recognize(image: CGImage, completion: @escaping (String?) -> Void) {
        let request = VNRecognizeTextRequest { req, error in
            if error != nil {
                DispatchQueue.main.async { completion(nil) }
                return
            }
            let observations = req.results as? [VNRecognizedTextObservation] ?? []
            let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            DispatchQueue.main.async { completion(trimmed.isEmpty ? nil : trimmed) }
        }
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        request.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                try handler.perform([request])
            } catch {
                DispatchQueue.main.async { completion(nil) }
            }
        }
    }
}

import AppKit
import Foundation

// GenerateIcon.swift — 用法: swift GenerateIcon.swift <输出目录>
// 在画布上画蓝渐变圆角 + 白色"译" + 细线，输出 AppIcon 需要的 10 个尺寸。
// 由 Xcode 构建阶段调用，图标缺失时才跑，跑完即有完整 AppIcon。

guard CommandLine.arguments.count > 1 else { exit(1) }
let outDir = CommandLine.arguments[1]

func drawIcon(size: CGFloat) -> NSImage {
    let img = NSImage(size: NSSize(width: size, height: size))
    img.lockFocus()
    let rect = NSRect(x: 0, y: 0, width: size, height: size)
    let path = NSBezierPath(roundedRect: rect, xRadius: size * 0.225, yRadius: size * 0.225)
    NSGraphicsContext.saveGraphicsState()
    path.setClip()
    let top = NSColor(red: 0.18, green: 0.47, blue: 0.97, alpha: 1)
    let bottom = NSColor(red: 0.07, green: 0.32, blue: 0.86, alpha: 1)
    NSGradient(starting: top, ending: bottom)?.draw(in: rect, angle: 90)
    NSGraphicsContext.restoreGraphicsState()
    let fontSize = size * 0.60
    let font = NSFont(name: "SongtiSC-Bold", size: fontSize)
        ?? NSFont(name: "PingFangSC-Semibold", size: fontSize)
        ?? NSFont.boldSystemFont(ofSize: fontSize)
    let text = NSAttributedString(string: "译", attributes: [
        .font: font,
        .foregroundColor: NSColor.white,
    ])
    let ts = text.size()
    text.draw(at: NSPoint(x: (size - ts.width) / 2, y: (size - ts.height) / 2 + size * 0.06))
    NSColor.white.withAlphaComponent(0.85).setFill()
    let lineH = max(2, size * 0.012)
    let lineRect = NSRect(x: (size - size * 0.36) / 2, y: size * 0.20, width: size * 0.36, height: lineH)
    NSBezierPath(roundedRect: lineRect, xRadius: lineH / 2, yRadius: lineH / 2).fill()
    img.unlockFocus()
    return img
}

let sizes: [(String, CGFloat)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
var failed = false
for (name, px) in sizes {
    let img = drawIcon(size: px)
    guard let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else {
        failed = true
        continue
    }
    let url = URL(fileURLWithPath: outDir).appendingPathComponent(name + ".png")
    do {
        try png.write(to: url)
    } catch {
        failed = true
    }
}
exit(failed ? 1 : 0)

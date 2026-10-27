#!/bin/bash
# 在 Mac 上编译 无感翻译.app（需要 Xcode Command Line Tools：xcode-select --install）
# 用法：cd 到本目录，./build.sh ，产物在 ./无感翻译.app ，拖进 /Applications 即可
set -e
cd "$(dirname "$0")"
# 目标系统定为 macOS 14：截图用的 CGWindowListCreateImage 在 macOS 15.0 被废弃，
# 新版 SDK 默认目标 >= 15 会直接报 unavailable；定到 14 才能继续编译，App 行为不变。
export MACOSX_DEPLOYMENT_TARGET=14.0
APP="无感翻译.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> 编译 Swift 源码…"
swiftc -O \
  -o "$APP/Contents/MacOS/无感翻译" \
  TranslateApp/main.swift \
  TranslateApp/TranslationService.swift \
  TranslateApp/SelectionMonitor.swift \
  TranslateApp/PopupWindow.swift \
  TranslateApp/SettingsView.swift \
  TranslateApp/HistoryStore.swift \
  TranslateApp/HotkeyManager.swift \
  TranslateApp/PopButton.swift \
  TranslateApp/ScreenshotOCR.swift \
  TranslateApp/MainWindow.swift \
  -framework AppKit -framework AVFoundation -framework Vision -framework ServiceManagement

cp Info.plist "$APP/Contents/Info.plist"
echo "==> 完成：$APP"
echo "首次运行：右键 -> 打开（绕过未签名提示），再去 系统设置 -> 隐私与安全性 -> 辅助功能 勾选本 App。"
open "$APP" 2>/dev/null || true

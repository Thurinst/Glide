#!/bin/bash
# 在 Mac 上编译 无感翻译.app（需要 Xcode Command Line Tools：xcode-select --install）
# 用法：cd 到本目录，./build.sh ，产物在 ./无感翻译.app ，拖进 /Applications 即可
set -e
cd "$(dirname "$0")"
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

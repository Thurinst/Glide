#!/bin/bash
# 双击安装「无感翻译」：编译 -> 装到 /Applications -> 打开
# 如果没装命令行工具，会先提示安装，装完再双击一次本文件即可。
cd "$(dirname "$0")"
if ! command -v swiftc >/dev/null 2>&1; then
  echo "没找到 swiftc，正在安装 Xcode Command Line Tools…"
  echo "请在弹出的窗口点「安装」，装完后重新双击本文件。"
  xcode-select --install
  read -p "按回车退出…" _
  exit 1
fi
./build.sh
echo "正在装到 /Applications…"
cp -R "无感翻译.app" /Applications/
echo "完成！已装到 /Applications/无感翻译.app"
echo "下一步：系统设置 → 隐私与安全性 → 辅助功能 → 勾选「无感翻译」"
open /Applications/无感翻译.app
read -p "按回车关闭本窗口…" _

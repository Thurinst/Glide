# Mac 无感翻译

菜单栏常驻 App，选中文字自动弹出翻译，不用切换窗口。

## 功能

- **划词即译**：在任何 App（浏览器、PDF、Word、飞书、微信…）里选中文字，鼠标一松就弹悬浮窗
- **双通道取词**：优先走 macOS 辅助功能（Accessibility，不碰剪贴板）；读不到的 App 自动用 Cmd+C 兜底
- **三种翻译源，可在设置里切换**
  1. **Google 免费机翻（默认，不用 Key）**：开箱即用
  2. **AI 大模型（OpenAI 兼容）**：填 API 地址 + Key + 模型即可，支持 OpenAI、DeepSeek、通义、Gemini 兼容接口等
  3. **DeepL API**：填 DeepL Key，Free Key（`:fx` 结尾）自动走免费接口
- **自动识别方向**：有中文 → 译英文，否则 → 译中文；也可固定目标语言
- **悬浮窗**：复制译文、朗读（中/英文发音）、📌 固定、Esc 关闭；跟随鼠标，贴边自动收
- **快捷键**：`⇧⌘T` 翻译当前选中 / 剪贴板

## 安装（在你的 Mac mini 上）

```bash
# 1. 把整个 mac-无感翻译 文件夹拷到 Mac 上
# 2. 先装命令行工具（只需一次）
xcode-select --install

# 3. 编译
cd mac-无感翻译
chmod +x build.sh
./build.sh

# 4. 把生成的 无感翻译.app 拖进 /Applications，双击运行
#    首次运行：右键 -> 打开（绕过“未签名开发者”提示）
```

## 授权（必须做，否则读不到选中文本）

首次启动会弹辅助功能授权：

`系统设置 → 隐私与安全性 → 辅助功能 → 勾选“无感翻译”`

没开这个权限时，App 会自动退到 Cmd+C 兜底模式，也能用，但体验不如辅助功能。

## 设置

点菜单栏右上角的「译」→ 设置：

| 项 | 说明 |
|---|---|
| 翻译引擎 | Google 免费 / AI 大模型 / DeepL |
| AI 接口地址 | OpenAI：`https://api.openai.com/v1`；DeepSeek：`https://api.deepseek.com/v1`；通义：`https://dashscope.aliyuncs.com/compatible-mode/v1` |
| AI API Key / 模型 | 如 `gpt-4o-mini`、`deepseek-chat`、`qwen-plus` |
| DeepL Key | Free Key 以 `:fx` 结尾 |
| 目标语言 | 自动 / 固定中文 / 固定英文 |

设置存在本机 UserDefaults，不上传任何地方；API Key 只发给你填的那个接口。

## 文件结构

```
TranslateApp/
  main.swift              菜单栏入口、快捷键、翻译调度
  TranslationService.swift  三种翻译引擎 + 设置存储
  SelectionMonitor.swift    划词监听（AX + Cmd+C 兜底）
  PopupWindow.swift         悬浮翻译窗（复制/朗读/固定）
  SettingsView.swift        设置窗口
Info.plist
build.sh                  一键编译成 .app
```

## 常见问题

- **选中没反应**：先看辅助功能权限开了没；再试 `⇧⌘T`；浏览器里有些页面要用 Cmd+C 兜底。
- **Google 免费接口偶尔限流**：等几秒再选一次，或切到 AI 模型。
- **想开机自启**：系统设置 → 通用 → 登录项 → 添加本 App。

## v2.0.0（2026-10-25，照 Easydict / Bob 功能标准）
- 主窗口（⌥A）：输入翻译工作台，源/目标语言切换 + 一键互换，左侧历史记录（搜索/收藏/删除/导出 CSV 与 Anki）。
- 截图 OCR（⌥S）：全屏遮罩拖框选区，Vision 离线识别中英文，识别完自动翻译出悬浮窗；识别失败在窗内提示。
- 静默 OCR（⌥⇧S）：框选识别，文字直接进剪贴板，不弹窗。
- 划词小图标：选中后先浮小「译」圆钮，点一下才翻译（设置里可关，关了恢复选中即弹窗）。
- 多引擎并行对照：一次查询同时跑 Google 免费 + DeepL（有 Key）+ AI 大模型（有 Key），主结果在上、其余对照在下。
- 历史记录 + 生词本：存 `~/Library/Application Support/无感翻译/history.json`（上限 500 条），收藏星标，导出 CSV / Anki（制表符 txt）。
- 润色模式：源语言与目标语言相同时自动走 AI 大模型润色/纠错（需填 AI Key）。
- 剪贴板监听（设置里开）：复制文字自动翻译出悬浮窗。
- 全局快捷键（设置里可改）：⌥D 划词、⌥A 输入、⌥S 截图、⌥⇧S 静默 OCR。
- 设置页：通用 / 翻译服务 / 快捷键 / 关于 四个标签页，开机自启（SMAppService）、自动发音。
- 图标：`IconB64/` 里 10 张 PNG 的 base64 文本，Xcode 构建时由“Decode App Icons”脚本阶段解码进 `Assets.xcassets/AppIcon.appiconset/`，不再靠下载链接。
- 编译：Xcode 工程直接 Run，或 `./build.sh`（已含新文件与 Vision / ServiceManagement 框架）。

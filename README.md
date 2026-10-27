# 无感翻译

Mac 划词翻译 App + 浏览器沉浸式翻译插件，两件套。选中文字就翻译，不用复制粘贴，不用切换窗口。

翻译源都支持「免费机翻开箱即用 + 自己填 API」：Google 免费（默认，不用 Key）、AI 大模型（OpenAI 兼容）、DeepL。

设计思路（为什么叫「无感翻译」、怎么做的、已知的取舍）见 [DESIGN.md](DESIGN.md)。

## 1. Mac App — `mac-无感翻译/`

菜单栏常驻的划词翻译 App。

- **划词即译**：选中文字自动弹出悬浮窗翻译（辅助功能取词 + Cmd+C 兜底）
- **悬浮窗**：复制译文、朗读、固定、Esc 关闭；窗口按译文长短自动调高，超出屏幕时自动上移
- **主窗口**：历史记录 + 生词本，支持导出 CSV / Anki
- **截图 OCR**：`⌥S` 截图翻译（Vision 离线识别），`⌥⇧S` 静默 OCR 直达剪贴板
- **快捷键**：`⌥D` 划词翻译、`⌥A` 打开主窗口、`⌥S` 截图翻译、`⌥⇧S` 静默 OCR
- **翻译源**：Google 免费（默认）/ AI 大模型（OpenAI / DeepSeek / 通义）/ DeepL

### 安装

```sh
xcode-select --install   # 只需一次，装命令行工具
./build.sh               # 生成 无感翻译.app
```

把生成的 `无感翻译.app` 拖进 `/Applications`，再去「系统设置 → 隐私与安全性 → 辅助功能」勾选它，选中文字就能自动翻译。

> 图标是构建时自动生成的：`GenerateIcon.swift` 画出蓝底「译」字标，`IconB64/` 里是各尺寸图标的 base64，构建阶段会解码成 `Assets.xcassets/AppIcon.appiconset/` 下的 PNG。所以仓库里不放二进制图标文件，克隆后第一次构建会自动生成。

详见 `mac-无感翻译/README.md`。

## 2. 浏览器插件 — `browser-无感翻译/`

沉浸式翻译平替，Chrome / Edge / ego lite（Chromium）都能装。

- `Alt+T` 全文双语对照翻译，再按还原；划词自动弹小窗；`Alt+Q` 翻译选中
- 翻译源：Google 免费（默认）/ AI 大模型（OpenAI 兼容）/ DeepL

### 安装

1. 先还原图标（克隆后跑一次即可）：
   ```sh
   sh browser-无感翻译/icons/decode-icons.sh
   ```
2. 浏览器打开 `chrome://extensions` → 开开发者模式 →「加载已解压的扩展程序」→ 选 `browser-无感翻译/` 文件夹。

详见 `browser-无感翻译/README.md`。

## 翻译源怎么选

| 场景 | 推荐 |
|---|---|
| 先用起来，不想填 Key | Google 免费（两个工具默认都是它，已实测中英互译可用） |
| 要质量好、翻长文/专业内容 | AI 大模型：DeepSeek `deepseek-chat` 便宜好用；OpenAI `gpt-4o-mini`；通义 `qwen-plus` |
| 要最准的机翻 | DeepL（Free Key 以 `:fx` 结尾） |

API Key 只存在你本机（Mac App 存在 UserDefaults，插件存在浏览器同步存储），只发给你填的那个接口。

## License

MIT

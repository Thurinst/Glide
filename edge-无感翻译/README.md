# 无感翻译 — Edge 扩展

沉浸式翻译平替，专为 Microsoft Edge 打包。Edge 与 Chrome 同为 Chromium 内核，所以扩展代码与 Chrome 版完全相同（Manifest V3），不用改一行代码就能在 Edge 里跑。

- `Alt+T` 全文双语对照翻译，再按还原；划词自动弹小窗；`Alt+Q` 翻译选中
- 翻译源：Google 免费（默认，不用 Key）/ AI 大模型（OpenAI 兼容）/ DeepL
- 设置：点工具栏的「无感翻译」图标 → 设置，可换引擎、填自己的 API Key、开关双语对照和自动翻译

## 安装（Edge）

1. 先还原图标（克隆后跑一次即可）：
   ```sh
   sh icons/decode-icons.sh
   ```
   Windows 上如果没有 `sh`，用 Git Bash 跑上面这行，或者手动把 `icons/` 下的三个 `.b64` 文件用在线 base64 工具解码成同名 `.png`。
2. Edge 地址栏打开 `edge://extensions` → 打开左下角「开发人员模式」→ 点「加载解压缩的扩展」→ 选本文件夹（`edge-无感翻译/`）。
3. 装好后工具栏会出现「无感翻译」图标。打开任意网页按 `Alt+T` 试一下。

> 也可以直接装 Chrome 版（`../browser-无感翻译/`）：Edge 支持直接加载 Chrome 扩展，两个文件夹的代码是一样的，分开只是为了安装路径写得清楚。

## 翻译源怎么选

| 场景 | 推荐 |
|---|---|
| 先用起来，不想填 Key | Google 免费（默认，已实测中英互译可用） |
| 要质量好、翻长文/专业内容 | AI 大模型：DeepSeek `deepseek-chat` 便宜好用；OpenAI `gpt-4o-mini`；通义 `qwen-plus` |
| 要最准的机翻 | DeepL（Free Key 以 `:fx` 结尾） |

API Key 只存在浏览器同步存储，只发给你填的那个接口。

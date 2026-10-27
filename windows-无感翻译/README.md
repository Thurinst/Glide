# 无感翻译 — Windows 版

Mac 版「无感翻译」的 Windows 移植。选中文字就翻译，免费机翻开箱即用，也可接自己的 AI / DeepL API。

## 在 Windows 上运行

1. 去 [python.org](https://www.python.org/downloads/) 装 Python 3.8 以上，安装时勾选 **Add Python to PATH**。
2. 把本文件夹（`windows-无感翻译/`）拷到 Windows 电脑上。
3. 双击 `wuganfanyi.py`，或者在文件夹里按住 Shift 点右键 →「在此处打开 PowerShell」→ 输入：
   ```powershell
   python wuganfanyi.py
   ```
4. 第一次运行会在文件夹里生成 `wuganfanyi-settings.json`（设置）和 `wuganfanyi-history.json`（历史记录）。

不用装任何第三方库，全部只用 Python 标准库（tkinter + ctypes + urllib + json）。

## 用法

- **剪贴板监听（默认开）**：任意地方选中文字按 `Ctrl+C`，悬浮窗自动弹出翻译。
- **Ctrl+Alt+D**：选中文字后按一下，自动模拟 `Ctrl+C` 取词并翻译（不用自己按复制）。
- **Ctrl+Alt+A**：显示 / 隐藏主窗口。
- **悬浮窗**：显示原文 + 译文，点「复制译文」或按 `Esc` 关闭；窗口按译文长短自动调高，底边快到任务栏时整个窗口往上挪，不会被任务栏挡住。
- **主窗口**：输入翻译、历史记录（双击回填）、设置。
- 点主窗口右上角 X 不会退出，只是隐藏到后台继续工作（快捷键和剪贴板监听还开着）；要彻底退出，点主窗口里的「退出」。

## 设置

点主窗口里的「设置」：

| 设置 | 说明 |
|---|---|
| 翻译引擎 | Google 免费（默认，不用 Key）/ AI 大模型（OpenAI 兼容）/ DeepL |
| AI 接口地址 | OpenAI 兼容地址，例：`https://api.openai.com/v1`；DeepSeek 用 `https://api.deepseek.com/v1`；通义用 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| AI 模型 | 例：`gpt-4o-mini` / `deepseek-chat` / `qwen-plus` |
| DeepL Key | Free Key 以 `:fx` 结尾 |
| 剪贴板监听 | 复制文字后自动翻译出悬浮窗（默认开） |
| 悬浮窗显示原文 | 默认开 |

API Key 只存在本机（`wuganfanyi-settings.json`），只发给你填的那个接口。

## 打包成 .exe（不用再装 Python 也能跑）

在 Windows 上：

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name 无感翻译 wuganfanyi.py
```

生成的 `dist/无感翻译.exe` 双击就能跑。设置和历史文件会生成在 exe 所在目录。

## 已知取舍

- Windows 没有 macOS 那种「辅助功能取词」，所以划词靠 `Ctrl+C`（剪贴板监听或 `Ctrl+Alt+D` 模拟复制），这是 Windows 上最稳的做法。
- 没有截图 OCR：Windows 自带 OCR（WinRT）从纯标准库调用起来比较绕，v1 先不做；需要的话可以后续加。
- 悬浮窗是 tkinter 的标准窗口，没有 macOS 的毛玻璃效果，但功能一样。

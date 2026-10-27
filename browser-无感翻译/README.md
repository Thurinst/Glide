# 无感翻译（浏览器插件）

无感翻译：网页沉浸式双语翻译的平替：网页全文双语对照 + 划词弹窗。免费机翻开箱即用，也可填自己的 AI / DeepL API。

## 功能

- **全文沉浸式翻译**：`Alt+T` 翻译整页，原文下面插入译文（双语对照），再按一次还原；也支持只显示译文模式
- **划词翻译**：选中文字自动弹小窗，带复制译文、朗读；`Alt+Q` 也能触发
- **三种翻译源**
  1. **Google 免费机翻（默认，不用 Key）**
  2. **AI 大模型（OpenAI 兼容）**：OpenAI / DeepSeek / 通义等，填接口地址 + Key + 模型
  3. **DeepL API**：Free Key（`:fx` 结尾）自动走免费接口
- **批量翻译**：全文翻译时多段合并请求，省次数、保上下文；AI 模式逐段翻保质量
- **右键菜单**：选中文字右键 → 翻译选中文字

## 安装（Chrome / Edge / ego lite 等 Chromium 浏览器）

1. 打开浏览器 → 地址栏输入 `chrome://extensions`（Edge 是 `edge://extensions`）
2. 右上角打开 **开发者模式**
3. 点 **加载已解压的扩展程序**，选择本文件夹 `browser-无感翻译`
4. 点工具栏里的插件图标 → 设置，选翻译引擎（默认 Google 免费，不用填）

> ego lite 也是 Chromium 内核，同样在 `chrome://extensions` 里加载。

## 使用

| 操作 | 效果 |
|---|---|
| 选中文字 | 自动弹翻译小窗 |
| `Alt+T` | 翻译 / 还原整页 |
| `Alt+Q` | 翻译当前选中 |
| 点工具栏图标 | 翻译本页 / 进设置 |
| 右键选中文字 | 翻译选中文字 |

## 设置

插件图标 → 设置，或扩展管理页 → 详细信息 → 扩展程序选项：

| 项 | 说明 |
|---|---|
| 翻译引擎 | Google 免费 / AI 大模型 / DeepL |
| AI 接口地址 | OpenAI：`https://api.openai.com/v1`；DeepSeek：`https://api.deepseek.com/v1`；通义：`https://dashscope.aliyuncs.com/compatible-mode/v1` |
| AI API Key / 模型 | 如 `gpt-4o-mini`、`deepseek-chat`、`qwen-plus` |
| DeepL Key | Free Key 以 `:fx` 结尾 |
| 双语对照 | 开：原文+译文；关：只显示译文 |
| 打开网页自动翻译 | 默认关，建议手动按 Alt+T |

设置存在浏览器 `chrome.storage.sync`，会跟随浏览器账号同步，不上传给第三方；API Key 只发给你填的那个接口。

## 文件结构

```
manifest.json      MV3 清单（权限、快捷键、右键菜单）
background.js      翻译接口统一入口（三种引擎 + 批量翻译）
content.js         全文翻译 + 划词弹窗
styles.css         译文块 / 弹窗样式
popup.html/js      工具栏弹窗
options.html/js    设置页
icons/             图标（需自行放 16/48/128 png，或用任意 png 改名）
```

## 图标

`icons/` 里需要 `icon16.png`、`icon48.png`、`icon128.png`。没有的话，先用任意 PNG 改名放进去即可，功能不受影响；也可以在网上找个翻译图标。

## 常见问题

- **Alt+T 没反应**：先点一下页面（让页面获得焦点），再按；或点工具栏图标里的“翻译本页”。
- **Google 免费接口偶尔限流**：等几秒再试，或切 AI 模型。
- **某些网站翻不全**：动态加载的内容（滚动才出现）需要再按一次 Alt+T；视频字幕、图片里的文字翻不了。
- **Safari**：Safari 不直接支持 Chrome 扩展，需要用 Xcode 转制，暂不在本版范围，Chrome/Edge/ego lite 直接用。

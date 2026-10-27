# -*- coding: utf-8 -*-
"""
无感翻译 — Windows 版
===================
Mac 版「无感翻译」的 Windows 移植：选中文字就翻译，免费机翻开箱即用，
也可接自己的 AI / DeepL API。

用法（Windows）：
    python wuganfanyi.py
只需要装 Python 3.8+（去 python.org 下），不用装任何第三方库，
全部只用标准库（tkinter + ctypes + urllib + json）。

功能：
- 剪贴板监听：选中文字按 Ctrl+C，悬浮窗自动弹出翻译（默认开，可在设置里关）。
- 全局快捷键 Ctrl+Alt+D：选中文字后按一下，自动模拟 Ctrl+C 取词并翻译。
- 全局快捷键 Ctrl+Alt+A：显示 / 隐藏主窗口。
- 悬浮窗：显示原文 + 译文，可复制译文，按 Esc 或点 X 关闭；窗口按译文长短自动调高，
  底边快到任务栏时整个窗口往上挪。
- 主窗口：输入翻译、历史记录（双击回填）、设置（引擎、API Key、目标语言等）。
- 翻译源：Google 免费（默认，不用 Key）/ AI 大模型（OpenAI 兼容）/ DeepL。

打包成 .exe（在 Windows 上）：
    pip install pyinstaller
    pyinstaller --onefile --windowed --name 无感翻译 wuganfanyi.py
生成的 dist/无感翻译.exe 双击就能跑，不用再装 Python。

注意：关闭主窗口右上角 X 时，程序不会退出，只是隐藏到后台继续工作
（快捷键和剪贴板监听还开着），按 Ctrl+Alt+A 可以再叫出来；
要彻底退出，点主窗口里的「退出」按钮。
"""

import ctypes
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_NAME = "无感翻译"
VERSION = "1.0.0"

# 全局快捷键（Windows 虚拟键码；改这里就能换键）
# Ctrl+Alt+D：翻译当前选中文字；Ctrl+Alt+A：显示/隐藏主窗口
HOTKEY_TRANSLATE_MODS = 0x0002 | 0x0001   # MOD_CONTROL | MOD_ALT
HOTKEY_TRANSLATE_VK = 0x44                # 'D'
HOTKEY_WINDOW_MODS = 0x0002 | 0x0001      # MOD_CONTROL | MOD_ALT
HOTKEY_WINDOW_VK = 0x41                   # 'A'
WM_HOTKEY = 0x0312

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

# 悬浮窗
POPUP_WIDTH = 380
POPUP_MIN_HEIGHT = 120
POPUP_MAX_HEIGHT = 500

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wuganfanyi-settings.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "wuganfanyi-history.json")
HISTORY_MAX = 200

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def target_lang_for(text, target):
    """目标语言：target 不是 auto 就用它；auto 时含中文翻英文，否则翻中文。"""
    if target and target != "auto":
        return target
    return "en" if CJK_RE.search(text) else "zh-CN"


# ---------------------------------------------------------------------------
# 设置（JSON，存在脚本同目录）
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "engine": "googleFree",          # googleFree | openAI | deepL
    "apiBaseURL": "https://api.openai.com/v1",
    "apiKey": "",
    "model": "gpt-4o-mini",
    "deepLKey": "",
    "target": "auto",                # auto | zh-CN | en
    "clipboardWatch": True,          # 监听剪贴板：Ctrl+C 后自动弹翻译
    "showOriginal": True,            # 悬浮窗里同时显示原文
}


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = dict(DEFAULT_SETTINGS)
        out.update({k: v for k, v in data.items() if k in out})
        return out
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存设置失败：", e, file=sys.stderr)


# ---------------------------------------------------------------------------
# 翻译引擎（与 Mac 版 / 浏览器版同一套接口）
# ---------------------------------------------------------------------------
class TranslateError(Exception):
    pass


def google_translate(text, target, timeout=15):
    """Google 免费机翻，无需 Key。"""
    tl = "en" if target == "en" else "zh-CN"
    qs = urllib.parse.urlencode({
        "client": "gtx", "sl": "auto", "tl": tl, "dt": "t",
        "q": text,
    })
    url = "https://translate.googleapis.com/translate_a/single?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise TranslateError("Google 翻译返回 %s" % e.code)
    except Exception as e:
        raise TranslateError("Google 翻译失败：%s" % e)
    parts = []
    for seg in (data[0] if isinstance(data, list) and data else []):
        if seg and seg[0]:
            parts.append(seg[0])
    out = "".join(parts).strip()
    if not out:
        raise TranslateError("Google 翻译返回为空")
    return out


def openai_translate(text, target, cfg, timeout=30):
    """AI 大模型（OpenAI 兼容：OpenAI / DeepSeek / 通义）。"""
    if not cfg.get("apiKey"):
        raise TranslateError("请先在设置里填写 AI API Key")
    target_name = "English" if target == "en" else "Simplified Chinese"
    base = (cfg.get("apiBaseURL") or "https://api.openai.com/v1").rstrip("/")
    body = json.dumps({
        "model": cfg.get("model") or "gpt-4o-mini",
        "temperature": 0.2,
        "messages": [
            {"role": "system",
             "content": "You are a professional translator. Translate the user text into %s. "
                        "Return ONLY the translation, no explanation, no quotes. "
                        "Preserve line breaks." % target_name},
            {"role": "user", "content": text},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + cfg["apiKey"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise TranslateError("AI 接口返回 %s：%s" % (e.code, e.read().decode("utf-8", "replace")[:200]))
    except Exception as e:
        raise TranslateError("AI 接口失败：%s" % e)
    out = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not out:
        raise TranslateError("AI 接口返回为空")
    return out


def deepl_translate(text, target, cfg, timeout=30):
    """DeepL API。Free Key 以 :fx 结尾走 api-free，否则走 api。"""
    key = cfg.get("deepLKey") or ""
    if not key:
        raise TranslateError("请先在设置里填写 DeepL Key")
    tl = "EN-US" if target == "en" else "ZH"
    host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    body = urllib.parse.urlencode(
        {"auth_key": key, "text": text, "target_lang": tl}).encode("utf-8")
    req = urllib.request.Request(
        host + "/v2/translate", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise TranslateError("DeepL 返回 %s" % e.code)
    except Exception as e:
        raise TranslateError("DeepL 失败：%s" % e)
    trans = data.get("translations") or []
    out = (trans[0].get("text") if trans else "") or ""
    if not out:
        raise TranslateError("DeepL 返回为空")
    return out


def translate(text, cfg):
    """按当前引擎翻译一段文字，返回译文。"""
    target = target_lang_for(text, cfg.get("target", "auto"))
    engine = cfg.get("engine", "googleFree")
    if engine == "openAI":
        return openai_translate(text, target, cfg)
    if engine == "deepL":
        return deepl_translate(text, target, cfg)
    return google_translate(text, target)


def engine_display_name(cfg):
    return {"googleFree": "Google 免费机翻（无需 Key）",
            "openAI": "AI 大模型",
            "deepL": "DeepL API"}.get(cfg.get("engine", "googleFree"), "")


# ---------------------------------------------------------------------------
# 历史记录（JSON，存在脚本同目录，上限 200 条）
# ---------------------------------------------------------------------------
def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(items):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items[:HISTORY_MAX], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存历史失败：", e, file=sys.stderr)

# ---------------------------------------------------------------------------
# Win32 小工具（ctypes，只用标准库）
# ---------------------------------------------------------------------------
def get_work_area():
    """取工作区矩形（去掉任务栏的可用区域），返回 (left, top, right, bottom)。"""
    try:
        rect = (wintypes.LONG * 4)()
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, rect, 0):
            return (rect[0], rect[1], rect[2], rect[3])
    except Exception:
        pass
    # 兜底：整个屏幕
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        return (0, 0, w, h)
    except Exception:
        return (0, 0, 1920, 1080)


def simulate_ctrl_c():
    """模拟按下 Ctrl+C（把当前选中的文字复制到剪贴板）。"""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def read_clipboard_text(root):
    try:
        return root.clipboard_get() or ""
    except Exception:
        return ""


def write_clipboard_text(root, text):
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 悬浮窗（无边框、置顶、跟鼠标、Esc 关闭、按内容自动调高、超任务栏时上移）
# ---------------------------------------------------------------------------
class PopupWindow:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.win = None
        self._orig_label = None
        self._result_label = None
        self._status_label = None
        self._result_text = ""

    def _ensure(self):
        if self.win is not None and self.win.winfo_exists():
            return
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#ffffff", highlightthickness=1,
                      highlightbackground="#d0d0d0")
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<Button-1>", lambda e: win.focus_set())

        pad = tk.Frame(win, bg="#ffffff")
        pad.pack(fill="both", expand=True, padx=12, pady=10)

        self._orig_label = tk.Label(
            pad, text="", font=("Microsoft YaHei", 10), fg="#666666",
            bg="#ffffff", anchor="w", justify="left",
            wraplength=POPUP_WIDTH - 32)
        self._orig_label.pack(fill="x")

        self._result_label = tk.Label(
            pad, text="", font=("Microsoft YaHei", 12), fg="#111111",
            bg="#ffffff", anchor="w", justify="left",
            wraplength=POPUP_WIDTH - 32)
        self._result_label.pack(fill="x", pady=(4, 0))

        self._status_label = tk.Label(
            pad, text="", font=("Microsoft YaHei", 9), fg="#999999",
            bg="#ffffff", anchor="w", justify="left")
        self._status_label.pack(fill="x", pady=(6, 0))

        btn_row = tk.Frame(pad, bg="#ffffff")
        btn_row.pack(fill="x", pady=(8, 0))
        tk.Button(btn_row, text="复制译文", font=("Microsoft YaHei", 10),
                  command=self._copy_result).pack(side="left")
        tk.Button(btn_row, text="关闭 (Esc)", font=("Microsoft YaHei", 10),
                  command=self.close).pack(side="right")
        self.win = win

    def _copy_result(self):
        if self._result_text:
            write_clipboard_text(self.root, self._result_text)
            self._status_label.config(text="已复制到剪贴板")

    def show_loading(self, original):
        self._ensure()
        self._result_text = ""
        if self.cfg.get("showOriginal", True):
            shown = original if len(original) <= 200 else original[:200] + "…"
            self._orig_label.config(text=shown)
        else:
            self._orig_label.config(text="")
        self._result_label.config(text="正在翻译…")
        self._status_label.config(text="")
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_result(self, original, result):
        self._ensure()
        self._result_text = result
        if self.cfg.get("showOriginal", True):
            shown = original if len(original) <= 200 else original[:200] + "…"
            self._orig_label.config(text=shown)
        else:
            self._orig_label.config(text="")
        shown_result = result if len(result) <= 1200 else result[:1200] + "…（较长，已截断，完整译文见主窗口历史）"
        self._result_label.config(text=shown_result)
        self._status_label.config(text="翻译完成（%s）" % engine_display_name(self.cfg))
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_error(self, original, error):
        self._ensure()
        self._result_text = ""
        if self.cfg.get("showOriginal", True):
            shown = original if len(original) <= 200 else original[:200] + "…"
            self._orig_label.config(text=shown)
        else:
            self._orig_label.config(text="")
        self._result_label.config(text="翻译失败")
        self._status_label.config(text=str(error))
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_hint(self, message):
        """没有选中文字时的提示。"""
        self._ensure()
        self._result_text = ""
        self._orig_label.config(text="")
        self._result_label.config(text=message)
        self._status_label.config(text="")
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def _place(self):
        """按内容定高、跟鼠标定位、超任务栏时把整个窗口往上挪。"""
        self.win.update_idletasks()
        content_h = 0
        for w in (self._orig_label, self._result_label, self._status_label):
            if w and w.winfo_exists():
                content_h += w.winfo_reqheight()
        # 顶部/底部留白 + 按钮行高度
        height = content_h + 10 + 10 + 8 + 32
        height = max(POPUP_MIN_HEIGHT, min(POPUP_MAX_HEIGHT, height))

        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()
        wa_left, wa_top, wa_right, wa_bottom = get_work_area()

        x = mx + 12
        y = my + 16
        if x + POPUP_WIDTH > wa_right:
            x = max(wa_left, wa_right - POPUP_WIDTH)
        if y + height > wa_bottom:
            y = wa_bottom - height
        if y < wa_top:
            y = wa_top
        self.win.geometry("%dx%d+%d+%d" % (POPUP_WIDTH, height, x, y))

    def close(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()

# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_settings()
        self.history = load_history()
        self.popup = PopupWindow(root, self.cfg)
        self._last_clipboard = ""
        self._own_clipboard = None      # 本程序自己写进剪贴板的内容，监听时跳过
        self._hide_hint_shown = False
        self._hotkey_stop = False
        self.root.title("%s %s" % (APP_NAME, VERSION))
        self.root.geometry("680x560")
        self._build_ui()
        self._refresh_history_list()
        self._update_engine_label()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_hotkey_thread()
        self.root.after(800, self._poll_clipboard)

    # ----- 界面 -----
    def _build_ui(self):
        root = self.root
        top = tk.Frame(root)
        top.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(top, text="目标语言：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.target_var = tk.StringVar(value=self.cfg.get("target", "auto"))
        target_menu = ttk.Combobox(
            top, textvariable=self.target_var, width=10, state="readonly",
            values=["auto", "zh-CN", "en"])
        target_menu.pack(side="left")
        target_menu.bind("<<ComboboxSelected>>", self._on_target_changed)
        self.engine_label = tk.Label(top, text="", font=("Microsoft YaHei", 10),
                                     fg="#666666")
        self.engine_label.pack(side="left", padx=(12, 0))
        tk.Button(top, text="设置", font=("Microsoft YaHei", 10),
                  command=self._open_settings).pack(side="right")
        tk.Button(top, text="退出", font=("Microsoft YaHei", 10),
                  command=self.quit_app).pack(side="right", padx=(0, 6))

        tk.Label(root, text="输入（中文↔英文自动检测）：",
                 font=("Microsoft YaHei", 10)).pack(anchor="w", padx=12, pady=(8, 0))
        self.input_text = tk.Text(root, height=6, font=("Microsoft YaHei", 11),
                                  wrap="word")
        self.input_text.pack(fill="both", expand=True, padx=12)

        btn_row = tk.Frame(root)
        btn_row.pack(fill="x", padx=12, pady=8)
        tk.Button(btn_row, text="翻译", font=("Microsoft YaHei", 11),
                  command=self._translate_main).pack(side="left")
        tk.Button(btn_row, text="复制译文", font=("Microsoft YaHei", 10),
                  command=self._copy_output).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="清空", font=("Microsoft YaHei", 10),
                  command=self._clear_main).pack(side="left", padx=(8, 0))
        tk.Label(btn_row, text="快捷键：Ctrl+Alt+D 翻译选中 / Ctrl+Alt+A 显示窗口",
                 font=("Microsoft YaHei", 9), fg="#999999").pack(side="right")

        tk.Label(root, text="译文：", font=("Microsoft YaHei", 10)).pack(
            anchor="w", padx=12)
        self.output_text = tk.Text(root, height=6, font=("Microsoft YaHei", 11),
                                   wrap="word", state="disabled", bg="#f7f7f7")
        self.output_text.pack(fill="both", expand=True, padx=12)

        self.status_label = tk.Label(root, text="就绪", font=("Microsoft YaHei", 9),
                                     fg="#999999", anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=(4, 0))

        hist_bar = tk.Frame(root)
        hist_bar.pack(fill="x", padx=12, pady=(6, 0))
        tk.Label(hist_bar, text="历史记录（双击回填）：",
                 font=("Microsoft YaHei", 10)).pack(side="left")
        tk.Button(hist_bar, text="删除选中", font=("Microsoft YaHei", 9),
                  command=self._delete_history_selected).pack(side="right")
        tk.Button(hist_bar, text="清空历史", font=("Microsoft YaHei", 9),
                  command=self._clear_history).pack(side="right", padx=(0, 6))

        self.history_list = tk.Listbox(root, height=6, font=("Microsoft YaHei", 10))
        self.history_list.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.history_list.bind("<Double-Button-1>", self._history_double_click)

    def _on_target_changed(self, _event=None):
        self.cfg["target"] = self.target_var.get()
        save_settings(self.cfg)

    def _update_engine_label(self):
        self.engine_label.config(text="引擎：" + engine_display_name(self.cfg))

    def _set_output(self, text):
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.config(state="disabled")

    def _set_status(self, text):
        self.status_label.config(text=text)

    # ----- 主窗口翻译 -----
    def _translate_main(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            self._set_status("请先输入要翻译的文字")
            return
        if len(text) > 5000:
            self._set_status("文字太长（超过 5000 字），请分段翻译")
            return
        self._set_status("正在翻译…")
        self._translate_async(text, on_done=self._main_translate_done)

    def _main_translate_done(self, text, result, error):
        if error:
            self._set_status("翻译失败：" + str(error))
            return
        self._set_output(result)
        self._set_status("翻译完成（%s）" % engine_display_name(self.cfg))
        self._add_history(text, result)

    def _copy_output(self):
        text = self.output_text.get("1.0", "end").strip()
        if text:
            self._own_clipboard = text
            write_clipboard_text(self.root, text)
            self._set_status("已复制译文到剪贴板")

    def _clear_main(self):
        self.input_text.delete("1.0", "end")
        self._set_output("")
        self._set_status("就绪")

    # ----- 后台翻译（不卡界面） -----
    def _translate_async(self, text, on_done):
        def worker():
            try:
                result = translate(text, self.cfg)
                self.root.after(0, lambda: on_done(text, result, None))
            except Exception as e:
                self.root.after(0, lambda: on_done(text, None, e))
        threading.Thread(target=worker, daemon=True).start()

    # ----- 历史 -----
    def _add_history(self, source, result):
        item = {"source": source, "result": result,
                "engine": self.cfg.get("engine", "googleFree"),
                "time": time.strftime("%m-%d %H:%M")}
        self.history.insert(0, item)
        self.history = self.history[:HISTORY_MAX]
        save_history(self.history)
        self._refresh_history_list()

    def _refresh_history_list(self):
        self.history_list.delete(0, "end")
        for item in self.history:
            src = item.get("source", "").replace("\n", " ")
            res = item.get("result", "").replace("\n", " ")
            if len(src) > 28:
                src = src[:28] + "…"
            if len(res) > 28:
                res = res[:28] + "…"
            self.history_list.insert("end", "%s  %s → %s" % (
                item.get("time", ""), src, res))

    def _history_double_click(self, _event=None):
        sel = self.history_list.curselection()
        if not sel:
            return
        item = self.history[sel[0]]
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", item.get("source", ""))
        self._set_output(item.get("result", ""))
        self._set_status("已从历史回填")

    def _delete_history_selected(self):
        sel = self.history_list.curselection()
        if not sel:
            return
        del self.history[sel[0]]
        save_history(self.history)
        self._refresh_history_list()

    def _clear_history(self):
        if not self.history:
            return
        if messagebox.askyesno("清空历史", "确定要清空全部历史记录吗？"):
            self.history = []
            save_history(self.history)
            self._refresh_history_list()

    # ----- 设置窗口 -----
    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置")
        dlg.geometry("480x430")
        dlg.transient(self.root)
        dlg.grab_set()

        engine_var = tk.StringVar(value=self.cfg.get("engine", "googleFree"))
        tk.Label(dlg, text="翻译引擎：", font=("Microsoft YaHei", 10)).pack(
            anchor="w", padx=14, pady=(12, 0))
        for value, label in [("googleFree", "Google 免费（默认，不用 Key）"),
                             ("openAI", "AI 大模型（OpenAI 兼容）"),
                             ("deepL", "DeepL API")]:
            tk.Radiobutton(dlg, text=label, variable=engine_var, value=value,
                           font=("Microsoft YaHei", 10)).pack(anchor="w", padx=24)

        def field(label, key, show=None):
            tk.Label(dlg, text=label, font=("Microsoft YaHei", 10)).pack(
                anchor="w", padx=14, pady=(8, 0))
            entry = tk.Entry(dlg, width=56, font=("Microsoft YaHei", 10),
                             show=show or "")
            entry.insert(0, self.cfg.get(key, ""))
            entry.pack(fill="x", padx=14)
            return entry

        base_entry = field("AI 接口地址（OpenAI 兼容，例：https://api.openai.com/v1 或 DeepSeek 地址）：",
                           "apiBaseURL")
        key_entry = field("AI API Key：", "apiKey", show="*")
        model_entry = field("AI 模型（例：gpt-4o-mini / deepseek-chat / qwen-plus）：",
                            "model")
        deepl_entry = field("DeepL Key（Free Key 以 :fx 结尾）：", "deepLKey", show="*")

        watch_var = tk.BooleanVar(value=self.cfg.get("clipboardWatch", True))
        tk.Checkbutton(dlg, text="剪贴板监听：复制文字后自动翻译出悬浮窗",
                       variable=watch_var, font=("Microsoft YaHei", 10)).pack(
            anchor="w", padx=14, pady=(10, 0))
        orig_var = tk.BooleanVar(value=self.cfg.get("showOriginal", True))
        tk.Checkbutton(dlg, text="悬浮窗里同时显示原文",
                       variable=orig_var, font=("Microsoft YaHei", 10)).pack(
            anchor="w", padx=14)

        tk.Label(dlg, text="Key 只存在本机（wuganfanyi-settings.json），只发给你填的那个接口。",
                 font=("Microsoft YaHei", 9), fg="#999999").pack(
            anchor="w", padx=14, pady=(8, 0))

        btn_row = tk.Frame(dlg)
        btn_row.pack(fill="x", padx=14, pady=14)

        def save():
            self.cfg["engine"] = engine_var.get()
            self.cfg["apiBaseURL"] = base_entry.get().strip()
            self.cfg["apiKey"] = key_entry.get().strip()
            self.cfg["model"] = model_entry.get().strip()
            self.cfg["deepLKey"] = deepl_entry.get().strip()
            self.cfg["clipboardWatch"] = bool(watch_var.get())
            self.cfg["showOriginal"] = bool(orig_var.get())
            save_settings(self.cfg)
            self._update_engine_label()
            self.popup.cfg = self.cfg
            dlg.destroy()
            self._set_status("设置已保存")

        tk.Button(btn_row, text="保存", font=("Microsoft YaHei", 11),
                  command=save).pack(side="left")
        tk.Button(btn_row, text="取消", font=("Microsoft YaHei", 10),
                  command=dlg.destroy).pack(side="left", padx=(8, 0))

    # ----- 剪贴板监听：Ctrl+C 后自动翻译 -----
    def _poll_clipboard(self):
        try:
            text = read_clipboard_text(self.root)
        except Exception:
            text = ""
        if text and text != self._last_clipboard:
            self._last_clipboard = text
            if (self.cfg.get("clipboardWatch", True)
                    and text != self._own_clipboard
                    and 1 < len(text.strip()) < 3000
                    and text.strip() != self._last_popup_source):
                self._last_popup_source = text.strip()
                self._translate_and_popup(text.strip())
        self.root.after(800, self._poll_clipboard)

    _last_popup_source = ""

    # ----- 悬浮窗翻译 -----
    def _translate_and_popup(self, text):
        self.popup.show_loading(text)
        self._translate_async(text, on_done=self._popup_translate_done)

    def _popup_translate_done(self, text, result, error):
        if error:
            self.popup.show_error(text, error)
            return
        self.popup.show_result(text, result)
        self._add_history(text, result)

    # ----- 全局快捷键 -----
    def _start_hotkey_thread(self):
        def hotkey_loop():
            user32 = ctypes.windll.user32
            # hwnd=None：热键消息发到本线程的消息队列，GetMessage 就能收到
            ok1 = user32.RegisterHotKey(None, 1, HOTKEY_TRANSLATE_MODS,
                                        HOTKEY_TRANSLATE_VK)
            ok2 = user32.RegisterHotKey(None, 2, HOTKEY_WINDOW_MODS,
                                        HOTKEY_WINDOW_VK)
            if not ok1 or not ok2:
                self.root.after(0, lambda: self._set_status(
                    "全局快捷键注册失败（可能被别的程序占了）：Ctrl+Alt+D / Ctrl+Alt+A"))
            msg = wintypes.MSG()
            while not self._hotkey_stop:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                if msg.message == WM_HOTKEY:
                    if msg.wParam == 1:
                        self.root.after(0, self._on_hotkey_translate)
                    elif msg.wParam == 2:
                        self.root.after(0, self._toggle_main_window)
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.UnregisterHotKey(None, 1)
            user32.UnregisterHotKey(None, 2)

        threading.Thread(target=hotkey_loop, daemon=True).start()

    def _on_hotkey_translate(self):
        """Ctrl+Alt+D：模拟 Ctrl+C 取当前选中文字，再翻译。"""
        before = read_clipboard_text(self.root)
        simulate_ctrl_c()
        # 等剪贴板更新
        self.root.after(200, lambda: self._after_copy(before))

    def _after_copy(self, before):
        text = read_clipboard_text(self.root).strip()
        if not text or text == before.strip():
            self.popup.show_hint("没有选中文字，请先选中一段文字再按 Ctrl+Alt+D")
            return
        self._last_clipboard = text
        self._last_popup_source = text
        self._translate_and_popup(text)

    def _toggle_main_window(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_set()
        else:
            self._on_close()

    # ----- 关闭 / 退出 -----
    def _on_close(self):
        """点 X：隐藏到后台（快捷键和剪贴板监听继续工作），不退出。"""
        self.root.withdraw()
        if not self._hide_hint_shown:
            self._hide_hint_shown = True
            self.popup.show_hint(
                "已隐藏到后台，Ctrl+Alt+D 还能翻译，Ctrl+Alt+A 叫回主窗口；"
                "要彻底退出请点主窗口里的「退出」。")

    def quit_app(self):
        self._hotkey_stop = True
        try:
            ctypes.windll.user32.PostThreadMessageW(
                threading.get_ident(), 0x0012, 0, 0)  # WM_QUIT，唤醒热键线程
        except Exception:
            pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    if sys.platform != "win32":
        print("提示：这是 Windows 版，在 %s 上只能做语法检查，"
              "热键和剪贴板功能要在 Windows 上跑才生效。" % sys.platform,
              file=sys.stderr)
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

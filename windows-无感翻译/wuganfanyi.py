# -*- coding: utf-8 -*-
"""
无感翻译 — Windows 版 v2.0.0
============================
Mac 版「无感翻译」的 Windows 移植：选中文字就翻译，免费机翻开箱即用，
也可接自己的 AI / DeepL API。

用法（Windows）：
    python wuganfanyi.py
只需要装 Python 3.8+（去 python.org 下），不用装任何第三方库，
全部只用标准库（tkinter + ctypes + urllib + json）。

功能（v2.0.0）：
- 划词翻译（唯一触发方式）：鼠标拖拽选中英文后自动翻译出悬浮窗；
  设置里可关掉自动翻，改为选中后浮一个蓝色「译」按钮，点了才翻。
  注意：不再监听剪贴板，复制（Ctrl+C）不会触发翻译。
- 全局快捷键 Ctrl+Alt+D：选中文字后按一下，模拟 Ctrl+C 取词并翻译（备用方式）。
- 全局快捷键 Ctrl+Alt+A：显示 / 隐藏主窗口。
- 全局快捷键 Ctrl+Alt+S：截图翻译（框选区域 → Windows 内置 OCR 识别 → 翻译）。
- 悬停取词（默认关）：鼠标停在英文单词上超过设定毫秒后自动翻译。
- 悬浮窗：只留一个（新弹窗出现时旧的先关掉），显示原文 + 译文，可复制、
  可收藏，按 Esc 关闭；窗口按译文长短自动调高，底边快到任务栏时上移。
- 主窗口：白底蓝主色现代界面；输入翻译、历史记录（双击回填）、生词本
  （★ 收藏）、CSV / Anki 导出、多引擎对照、润色模式。
- 翻译源：Google 免费（默认，不用 Key）/ AI 大模型（OpenAI 兼容）/ DeepL。
- 单实例：重复启动时唤起已有窗口，不多开。

打包成 .exe（在 Windows 上）：
    pip install pyinstaller
    pyinstaller --onefile --windowed --name 无感翻译 wuganfanyi.py
生成的 dist/无感翻译.exe 双击就能跑，不用再装 Python。

注意：关闭主窗口右上角 X 时，程序不会退出，只是隐藏到后台继续工作
（快捷键和划词监听还开着），按 Ctrl+Alt+A 可以再叫出来；
要彻底退出，点主窗口里的「退出」按钮。
"""

import csv
import ctypes
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk
import urllib.error
import urllib.parse
import urllib.request
import uuid
from ctypes import wintypes
from tkinter import filedialog

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_NAME = "无感翻译"
VERSION = "2.0.0"

# 全局快捷键（Windows 虚拟键码；改这里就能换键）
# Ctrl+Alt+D：翻译当前选中文字；Ctrl+Alt+A：显示/隐藏主窗口；Ctrl+Alt+S：截图翻译
HOTKEY_TRANSLATE_MODS = 0x0002 | 0x0001   # MOD_CONTROL | MOD_ALT
HOTKEY_TRANSLATE_VK = 0x44                # 'D'
HOTKEY_WINDOW_MODS = 0x0002 | 0x0001      # MOD_CONTROL | MOD_ALT
HOTKEY_WINDOW_VK = 0x41                   # 'A'
HOTKEY_OCR_MODS = 0x0002 | 0x0001         # MOD_CONTROL | MOD_ALT
HOTKEY_OCR_VK = 0x53                      # 'S'
WM_HOTKEY = 0x0312

VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

# 悬浮窗
POPUP_WIDTH = 380
POPUP_MIN_HEIGHT = 120
POPUP_MAX_HEIGHT = 500

# 配色（跟浏览器扩展一致的主色）
COLOR_PRIMARY = "#4a7dff"
COLOR_PRIMARY_DARK = "#3a6bf0"
COLOR_BG = "#ffffff"
COLOR_TEXT = "#222222"
COLOR_TEXT_2 = "#666666"
COLOR_TEXT_3 = "#999999"
COLOR_BORDER = "#d9dee8"
COLOR_BTN_BG = "#f0f3fa"
COLOR_BTN_BG_HOVER = "#e2e8f5"
COLOR_OUTPUT_BG = "#f8f9fc"
FONT = "Microsoft YaHei"

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wuganfanyi-settings.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "wuganfanyi-history.json")
FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "wuganfanyi-favorites.json")
HISTORY_MAX = 200
FAVORITES_MAX = 500

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_RE = re.compile(r"[A-Za-z]")
WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{1,29}$")


def target_lang_for(text, target):
    """目标语言：target 不是 auto 就用它；auto 时含中文翻英文，否则翻中文。"""
    if target and target != "auto":
        return target
    return "en" if CJK_RE.search(text) else "zh-CN"


def detect_lang(text):
    """粗略判断输入语言：含中文即中文，否则英文。"""
    return "zh" if CJK_RE.search(text) else "en"


def is_english_text(text):
    """是否英文文本：含英文字母且不含中文（划词/悬停只对英文触发）。"""
    return bool(ENGLISH_RE.search(text)) and not CJK_RE.search(text)


def is_polish_case(text, cfg):
    """输入语言与目标语言相同时走润色，不走翻译。"""
    target = target_lang_for(text, cfg.get("target", "auto"))
    target_short = "en" if target == "en" else "zh"
    return detect_lang(text) == target_short


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
    "selectTranslate": True,         # 划词翻译：开=选中英文直接翻，关=选中后点「译」按钮再翻
    "hoverTranslate": False,         # 悬停取词：鼠标停在英文单词上自动翻译
    "hoverDelayMs": 500,             # 悬停延时（毫秒，200-1000）
    "compareEngines": False,         # 多引擎对照：同时调已配置好的引擎并排显示
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


def _openai_chat(messages, cfg, temperature=0.2, timeout=30):
    """调一次 OpenAI 兼容的 /chat/completions，返回 content 文本。"""
    if not cfg.get("apiKey"):
        raise TranslateError("请先在设置里填写 AI API Key")
    base = (cfg.get("apiBaseURL") or "https://api.openai.com/v1").rstrip("/")
    body = json.dumps({
        "model": cfg.get("model") or "gpt-4o-mini",
        "temperature": temperature,
        "messages": messages,
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


def openai_translate(text, target, cfg, timeout=30):
    """AI 大模型（OpenAI 兼容：OpenAI / DeepSeek / 通义）。"""
    target_name = "English" if target == "en" else "Simplified Chinese"
    return _openai_chat([
        {"role": "system",
         "content": "You are a professional translator. Translate the user text into %s. "
                    "Return ONLY the translation, no explanation, no quotes. "
                    "Preserve line breaks." % target_name},
        {"role": "user", "content": text},
    ], cfg, temperature=0.2, timeout=timeout)


def openai_polish(text, target, cfg, timeout=30):
    """润色：输入与目标语言相同时调用 AI 润色（Google / DeepL 没有润色接口）。"""
    if not cfg.get("apiKey"):
        raise TranslateError("润色需要配置 AI Key")
    lang_name = "English" if target == "en" else "Simplified Chinese"
    return _openai_chat([
        {"role": "system",
         "content": "You are a professional writing coach. Polish the user text in %s "
                    "to sound natural, fluent and idiomatic. Fix grammar and word "
                    "choice, keep the meaning unchanged. Return ONLY the polished "
                    "text, no explanation, no quotes." % lang_name},
        {"role": "user", "content": text},
    ], cfg, temperature=0.3, timeout=timeout)


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


ENGINE_SHORT = {"googleFree": "Google", "openAI": "AI", "deepL": "DeepL"}


def translate_all(text, cfg):
    """多引擎对照：同时调用已配置好的引擎，返回 {engine: (译文或 None, 错误或 None)}。
    Google 免费始终可用；AI 仅当填了 Key 才参与；DeepL 仅当填了 Key 才参与。"""
    target = target_lang_for(text, cfg.get("target", "auto"))
    jobs = [("googleFree", lambda: google_translate(text, target))]
    if cfg.get("apiKey"):
        jobs.append(("openAI", lambda: openai_translate(text, target, cfg)))
    if cfg.get("deepLKey"):
        jobs.append(("deepL", lambda: deepl_translate(text, target, cfg)))
    results = {}

    def run(key, fn):
        try:
            results[key] = (fn(), None)
        except Exception as e:
            results[key] = (None, str(e))

    threads = []
    for key, fn in jobs:
        t = threading.Thread(target=run, args=(key, fn), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=35)
    return results


def engine_display_name(cfg):
    return {"googleFree": "Google 免费机翻（无需 Key）",
            "openAI": "AI 大模型",
            "deepL": "DeepL API"}.get(cfg.get("engine", "googleFree"), "")


# ---------------------------------------------------------------------------
# 历史记录 / 生词本（JSON，存在脚本同目录）
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


def load_favorites():
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_favorites(items):
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(items[:FAVORITES_MAX], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存生词本失败：", e, file=sys.stderr)

# ---------------------------------------------------------------------------
# Win32 小工具（ctypes，只用标准库；非 Windows 上不调用）
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
# 单实例（命名互斥体）：重复启动时唤起已有窗口，不多开
# ---------------------------------------------------------------------------
_SINGLE_MUTEX = None


def ensure_single_instance():
    """返回 True 表示本进程是唯一实例；False 表示已有实例在跑（已尝试唤起它）。
    非 Windows 上直接返回 True。"""
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL,
                                          wintypes.LPCWSTR]
        kernel32.GetLastError.restype = wintypes.DWORD
        user32.FindWindowW.restype = wintypes.HWND
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        global _SINGLE_MUTEX
        _SINGLE_MUTEX = kernel32.CreateMutexW(
            None, True, "Global\\WuganfanyiSingleInstance")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            hwnd = user32.FindWindowW(None, "%s %s" % (APP_NAME, VERSION))
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE：还原并显示
                user32.SetForegroundWindow(hwnd)
            return False
        return True
    except Exception:
        return True


# ---------------------------------------------------------------------------
# 低级鼠标钩子（WH_MOUSE_LL）：监听左键拖拽选中与鼠标移动
# 事件只进队列，不在钩子回调里做任何耗时操作，由主线程轮询处理。
# ---------------------------------------------------------------------------
class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class MouseHook:
    def __init__(self):
        self.events = queue.Queue()
        self._hook = None
        self._cb = None
        self._tid = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.HINSTANCE, wintypes.DWORD]
            user32.CallNextHookEx.restype = wintypes.LPARAM
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                              wintypes.WPARAM, wintypes.LPARAM]
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG),
                                           wintypes.HWND, wintypes.UINT,
                                           wintypes.UINT]
            user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

            CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                         wintypes.WPARAM, wintypes.LPARAM)
            self._cb = CMPFUNC(self._proc)
            hmod = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(14, self._cb, hmod, 0)  # WH_MOUSE_LL
            if not self._hook:
                return
            self._tid = threading.get_ident()
            msg = wintypes.MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            try:
                if self._hook:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass

    def _proc(self, nCode, wParam, lParam):
        if nCode == 0:
            try:
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if wParam == 0x0201:      # WM_LBUTTONDOWN
                    self.events.put(("down", info.pt.x, info.pt.y))
                elif wParam == 0x0202:    # WM_LBUTTONUP
                    self.events.put(("up", info.pt.x, info.pt.y))
                elif wParam == 0x0200:    # WM_MOUSEMOVE
                    self.events.put(("move", info.pt.x, info.pt.y))
            except Exception:
                pass
        try:
            return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)
        except Exception:
            return 0

    def stop(self):
        if self._tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass


# ---------------------------------------------------------------------------
# UI Automation 取词（悬停取词用）：取鼠标所在位置的英文单词
# 全部经 ctypes 调 UIAutomationCore.dll 的 COM 接口；任何一步失败都返回 ""，
# 调用方静默跳过，不报错、不弹窗。
# ---------------------------------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]


def _guid_from_str(s):
    u = uuid.UUID(s)
    return _GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (wintypes.BYTE * 8)(*u.bytes[8:]))


def _call_vtable(obj, index, restype, argtypes, *args):
    """调 COM 对象虚表里的第 index 个方法（obj 是 c_void_p 接口指针）。"""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn_ptr = vtbl[index]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    fn = ctypes.cast(fn_ptr, proto)
    return fn(obj, *args)


def _release_com(obj):
    try:
        _call_vtable(obj, 2, wintypes.ULONG, [])
    except Exception:
        pass


class UIAWordGetter:
    """Windows UI Automation 取词：取鼠标所在位置的英文单词。失败返回 ''。"""

    CLSID_CUIAutomation = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
    IID_IUIAutomation = "{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}"
    UIA_TextPatternId = 10014
    TextUnit_Word = 2

    def __init__(self):
        self._failed = False

    def word_at(self, x, y):
        if sys.platform != "win32" or self._failed:
            return ""
        try:
            return self._word_at_inner(x, y)
        except Exception:
            return ""

    def _word_at_inner(self, x, y):
        ole32 = ctypes.windll.ole32
        oleaut32 = ctypes.windll.oleaut32
        ole32.CoInitializeEx.restype = wintypes.HRESULT
        ole32.CoInitializeEx.argtypes = [wintypes.LPVOID, wintypes.DWORD]
        ole32.CoCreateInstance.restype = wintypes.HRESULT
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(_GUID),
                                           ctypes.POINTER(ctypes.c_void_p)]
        oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]
        ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
        uia = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(_guid_from_str(self.CLSID_CUIAutomation)), None, 1,
            ctypes.byref(_guid_from_str(self.IID_IUIAutomation)),
            ctypes.byref(uia))
        if hr != 0 or not uia:
            self._failed = True
            return ""
        try:
            pt = wintypes.POINT(x, y)
            el = ctypes.c_void_p()
            # IUIAutomation::ElementFromPoint（虚表第 7 个方法）
            hr = _call_vtable(uia, 7, wintypes.HRESULT,
                              [wintypes.POINT, ctypes.POINTER(ctypes.c_void_p)],
                              pt, ctypes.byref(el))
            if hr != 0 or not el:
                return ""
            try:
                pat = ctypes.c_void_p()
                # IUIAutomationElement::GetCurrentPattern（虚表第 17 个方法）
                hr = _call_vtable(el, 17, wintypes.HRESULT,
                                  [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
                                  self.UIA_TextPatternId, ctypes.byref(pat))
                if hr != 0 or not pat:
                    return ""
                try:
                    rng = ctypes.c_void_p()
                    # IUIAutomationTextPattern::RangeFromPoint（虚表第 3 个方法）
                    hr = _call_vtable(pat, 3, wintypes.HRESULT,
                                      [wintypes.POINT, ctypes.POINTER(ctypes.c_void_p)],
                                      pt, ctypes.byref(rng))
                    if hr != 0 or not rng:
                        return ""
                    try:
                        # IUIAutomationTextRange::ExpandToEnclosingUnit(Word)（第 6 个）
                        hr = _call_vtable(rng, 6, wintypes.HRESULT,
                                          [ctypes.c_int], self.TextUnit_Word)
                        if hr != 0:
                            return ""
                        bstr = ctypes.c_void_p()
                        # IUIAutomationTextRange::GetText(-1)（第 12 个）
                        hr = _call_vtable(rng, 12, wintypes.HRESULT,
                                          [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
                                          -1, ctypes.byref(bstr))
                        if hr != 0 or not bstr:
                            return ""
                        try:
                            return ctypes.wstring_at(bstr.value) or ""
                        finally:
                            oleaut32.SysFreeString(bstr)
                    finally:
                        _release_com(rng)
                finally:
                    _release_com(pat)
            finally:
                _release_com(el)
        finally:
            _release_com(uia)


# ---------------------------------------------------------------------------
# 截图 OCR：GDI BitBlt 截图 → BMP 文件 → PowerShell + Windows.Media.Ocr 识别
# ---------------------------------------------------------------------------
def capture_rect_to_bmp(x, y, w, h, path):
    """用 GDI BitBlt 截取屏幕矩形区域，写成 24 位 BMP 文件。仅 Windows。"""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, wintypes.HDC,
                             ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                                wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                                wintypes.UINT]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        raise RuntimeError("GetDC 失败")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    try:
        old = gdi32.SelectObject(hdc_mem, hbmp)
        SRCCOPY = 0x00CC0020
        if not gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY):
            raise RuntimeError("BitBlt 失败")
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = h
        bi.biPlanes = 1
        bi.biBitCount = 24
        bi.biCompression = 0  # BI_RGB
        row_bytes = ((w * 3 + 3) // 4) * 4
        bi.biSizeImage = row_bytes * h
        buf = ctypes.create_string_buffer(row_bytes * h)
        lines = gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)
        if lines == 0:
            raise RuntimeError("GetDIBits 失败")
        gdi32.SelectObject(hdc_mem, old)
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
    file_size = 14 + 40 + row_bytes * h
    with open(path, "wb") as f:
        f.write(struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54))
        f.write(ctypes.string_at(ctypes.byref(bi), ctypes.sizeof(bi)))
        f.write(buf.raw)


OCR_PS_SCRIPT = r'''
param([string]$ImagePath, [string]$OutPath)
$ErrorActionPreference = 'Stop'
try {
    $file = [Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath).GetAwaiter().GetResult()
    $stream = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read).GetAwaiter().GetResult()
    $decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream).GetAwaiter().GetResult()
    $bitmap = $decoder.GetSoftwareBitmapAsync().GetAwaiter().GetResult()
    $engine = $null
    foreach ($tag in @('en', 'zh-Hans')) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($tag)
        if ($engine) { break }
    }
    if (-not $engine) {
        $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
        if ($langs.Count -gt 0) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langs[0].LanguageTag) }
    }
    $text = ''
    if ($engine) {
        $res = $engine.RecognizeAsync($bitmap).GetAwaiter().GetResult()
        if ($res) { $text = $res.Text }
    }
    [System.IO.File]::WriteAllText($OutPath, $text, [System.Text.Encoding]::UTF8)
} catch {
    try { [System.IO.File]::WriteAllText($OutPath, '', [System.Text.Encoding]::UTF8) } catch {}
}
'''


def ocr_image_file(image_path, timeout=60):
    """调用 PowerShell + Windows.Media.Ocr 识别图片里的文字，返回 str。
    识别为空或 OCR 不可用时返回 ''（不抛错，由调用方提示）。"""
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise RuntimeError("系统里没有 PowerShell，无法使用截图 OCR")
    tmpdir = tempfile.gettempdir()
    script_path = os.path.join(tmpdir, "wuganfanyi-ocr.ps1")
    out_path = os.path.join(tmpdir, "wuganfanyi-ocr.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(OCR_PS_SCRIPT)
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    try:
        subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", script_path, "-ImagePath", image_path,
                        "-OutPath", out_path],
                       timeout=timeout, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""
    try:
        with open(out_path, "r", encoding="utf-8-sig") as f:
            return f.read().strip()
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# UI 样式助手（扁平圆角风格：白底 + 蓝主色 + 微软雅黑）
# ---------------------------------------------------------------------------
def _flat_button(parent, text, command, primary=False, font_size=10):
    """扁平按钮：主按钮蓝底白字，次按钮浅灰底深字；悬停时加深。"""
    bg = COLOR_PRIMARY if primary else COLOR_BTN_BG
    fg = "#ffffff" if primary else "#333333"
    hover_bg = COLOR_PRIMARY_DARK if primary else COLOR_BTN_BG_HOVER
    btn = tk.Button(parent, text=text, command=command,
                    font=(FONT, font_size), relief="flat", borderwidth=0,
                    cursor="hand2", bg=bg, fg=fg,
                    activebackground=hover_bg, activeforeground=fg,
                    padx=14, pady=6)

    def on_enter(_e):
        btn.config(bg=hover_bg)

    def on_leave(_e):
        btn.config(bg=bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def _styled_text(parent, height, bg=COLOR_BG, font_size=11):
    """带浅灰边框的输入/输出框。"""
    return tk.Text(parent, height=height, font=(FONT, font_size), wrap="word",
                   bg=bg, fg=COLOR_TEXT, relief="flat",
                   highlightthickness=1, highlightbackground=COLOR_BORDER,
                   highlightcolor=COLOR_PRIMARY, insertbackground=COLOR_PRIMARY,
                   padx=10, pady=8, selectbackground="#cfe0ff")


def _styled_entry(parent, width=52, show=""):
    """带浅灰边框的单行输入框。"""
    return tk.Entry(parent, width=width, font=(FONT, 10), bg=COLOR_BG,
                    fg=COLOR_TEXT, relief="flat", show=show,
                    highlightthickness=1, highlightbackground=COLOR_BORDER,
                    highlightcolor=COLOR_PRIMARY, insertbackground=COLOR_PRIMARY)


# ---------------------------------------------------------------------------
# 悬浮窗（无边框、置顶、跟鼠标、Esc 关闭、按内容自动调高、超任务栏时上移）
# 单例：任何一次新内容显示前先把旧窗口藏起来，绝不叠加。
# ---------------------------------------------------------------------------
class PopupWindow:
    def __init__(self, root, cfg, on_favorite=None):
        self.root = root
        self.cfg = cfg
        self.on_favorite = on_favorite
        self.win = None
        self._orig_label = None
        self._result_label = None
        self._status_label = None
        self._orig_text = ""
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
            pad, text="", font=(FONT, 10), fg=COLOR_TEXT_2,
            bg="#ffffff", anchor="w", justify="left",
            wraplength=POPUP_WIDTH - 32)
        self._orig_label.pack(fill="x")

        self._result_label = tk.Label(
            pad, text="", font=(FONT, 12), fg="#111111",
            bg="#ffffff", anchor="w", justify="left",
            wraplength=POPUP_WIDTH - 32)
        self._result_label.pack(fill="x", pady=(4, 0))

        self._status_label = tk.Label(
            pad, text="", font=(FONT, 9), fg=COLOR_TEXT_3,
            bg="#ffffff", anchor="w", justify="left")
        self._status_label.pack(fill="x", pady=(6, 0))

        btn_row = tk.Frame(pad, bg="#ffffff")
        btn_row.pack(fill="x", pady=(8, 0))
        _flat_button(btn_row, "复制译文", self._copy_result,
                     primary=True).pack(side="left")
        _flat_button(btn_row, "★ 收藏", self._favorite).pack(
            side="left", padx=(8, 0))
        _flat_button(btn_row, "关闭 (Esc)", self.close).pack(side="right")
        self.win = win

    def _hide_existing(self):
        """新内容显示前先藏起旧窗口：屏幕上永远只有一个悬浮窗。"""
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()

    def _copy_result(self):
        if self._result_text:
            write_clipboard_text(self.root, self._result_text)
            self._status_label.config(text="已复制到剪贴板")

    def _favorite(self):
        if not self._result_text:
            self._status_label.config(text="没有可收藏的译文")
            return
        if self.on_favorite:
            self.on_favorite(self._orig_text, self._result_text)

    def set_status(self, text):
        if self._status_label is not None and self._status_label.winfo_exists():
            self._status_label.config(text=text)

    def _show_orig(self, original):
        if self.cfg.get("showOriginal", True):
            shown = original if len(original) <= 200 else original[:200] + "…"
            self._orig_label.config(text=shown)
        else:
            self._orig_label.config(text="")

    def show_loading(self, original):
        self._hide_existing()
        self._ensure()
        self._orig_text = original
        self._result_text = ""
        self._show_orig(original)
        self._result_label.config(text="正在翻译…")
        self._status_label.config(text="")
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_result(self, original, result, note=None):
        self._hide_existing()
        self._ensure()
        self._orig_text = original
        self._result_text = result
        self._show_orig(original)
        shown_result = result if len(result) <= 1200 else result[:1200] + "…（较长，已截断，完整译文见主窗口历史）"
        self._result_label.config(text=shown_result)
        status = note or ("翻译完成（%s）" % engine_display_name(self.cfg))
        self._status_label.config(text=status)
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_error(self, original, error):
        self._hide_existing()
        self._ensure()
        self._orig_text = original
        self._result_text = ""
        self._show_orig(original)
        self._result_label.config(text="翻译失败")
        self._status_label.config(text=str(error))
        self._place()
        self.win.deiconify()
        self.win.focus_set()

    def show_hint(self, message):
        """没有选中文字时的提示。"""
        self._hide_existing()
        self._ensure()
        self._orig_text = ""
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

    def is_visible(self):
        return (self.win is not None and self.win.winfo_exists()
                and self.win.winfo_viewable())

    def contains_point(self, x, y):
        if not self.is_visible():
            return False
        try:
            wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
            return (wx <= x < wx + self.win.winfo_width()
                    and wy <= y < wy + self.win.winfo_height())
        except Exception:
            return False

    def close(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()


# ---------------------------------------------------------------------------
# 译按钮 PopButton：划词开关关时，选中英文后在鼠标附近浮现的小蓝圆钮，
# 点一下才翻译；4 秒自动消失；同一时间最多一个。
# ---------------------------------------------------------------------------
class PopButton:
    SIZE = 40

    def __init__(self, root, on_click):
        self.root = root
        self.on_click = on_click
        self.win = None
        self.text = ""
        self._timer = None

    def show(self, text, x=None, y=None):
        self.hide()
        self.text = text
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=COLOR_PRIMARY)
        canvas = tk.Canvas(win, width=self.SIZE, height=self.SIZE,
                           bg=COLOR_PRIMARY, highlightthickness=0,
                           cursor="hand2")
        canvas.pack()
        canvas.create_oval(2, 2, self.SIZE - 2, self.SIZE - 2,
                           fill=COLOR_PRIMARY, outline="#ffffff", width=1)
        canvas.create_text(self.SIZE // 2, self.SIZE // 2, text="译",
                           fill="#ffffff", font=(FONT, 15, "bold"))
        canvas.bind("<Button-1>", lambda e: self._click())
        win.bind("<Escape>", lambda e: self.hide())
        mx = self.root.winfo_pointerx() if x is None else x
        my = self.root.winfo_pointery() if y is None else y
        wa_left, wa_top, wa_right, wa_bottom = get_work_area()
        px = mx + 10
        py = my + 14
        if px + self.SIZE > wa_right:
            px = wa_right - self.SIZE
        if py + self.SIZE > wa_bottom:
            py = wa_bottom - self.SIZE
        if px < wa_left:
            px = wa_left
        if py < wa_top:
            py = wa_top
        win.geometry("%dx%d+%d+%d" % (self.SIZE, self.SIZE, px, py))
        self.win = win
        self._timer = self.root.after(4000, self.hide)

    def _click(self):
        text = self.text
        self.hide()
        if text and self.on_click:
            self.on_click(text)

    def hide(self):
        if self._timer is not None:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        if self.win is not None:
            try:
                if self.win.winfo_exists():
                    self.win.destroy()
            except Exception:
                pass
            self.win = None

    def is_visible(self):
        return self.win is not None and self.win.winfo_exists()

    def geometry_contains(self, x, y):
        if not self.is_visible():
            return False
        try:
            wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
            return (wx <= x < wx + self.win.winfo_width()
                    and wy <= y < wy + self.win.winfo_height())
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 截图框选遮罩：全屏半透明，拖拽框选区域，松开确认，Esc 取消
# ---------------------------------------------------------------------------
class ScreenshotOverlay:
    def __init__(self, root, on_selected, on_cancel):
        self.root = root
        self.on_selected = on_selected
        self.on_cancel = on_cancel
        self.win = None
        self.canvas = None
        self._start = None
        self._rect_id = None

    def show(self):
        if self.win is not None:
            return
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.35)
        except Exception:
            pass
        win.configure(bg="#000000")
        w = win.winfo_screenwidth()
        h = win.winfo_screenheight()
        win.geometry("%dx%d+0+0" % (w, h))
        canvas = tk.Canvas(win, width=w, height=h, bg="#000000",
                           highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        canvas.create_text(w // 2, 30, text="拖拽框选要识别的区域，松开确认，Esc 取消",
                           fill="#ffffff", font=(FONT, 13))
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        win.bind("<Escape>", lambda e: self.cancel())
        win.focus_set()
        self.win = win
        self.canvas = canvas

    def _on_press(self, event):
        self._start = (event.x, event.y)
        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, event):
        if self._start is None:
            return
        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
        x0, y0 = self._start
        self._rect_id = self.canvas.create_rectangle(
            x0, y0, event.x, event.y, outline=COLOR_PRIMARY, width=2)

    def _on_release(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        self._destroy()
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w >= 10 and h >= 10:
            self.on_selected(x, y, w, h)
        else:
            self.on_cancel()

    def cancel(self):
        self._destroy()
        self.on_cancel()

    def _destroy(self):
        if self.win is not None:
            try:
                if self.win.winfo_exists():
                    self.win.destroy()
            except Exception:
                pass
            self.win = None
            self.canvas = None
            self._start = None
            self._rect_id = None

# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainApp:
    def __init__(self, root):
        self.root = root
        self._win32 = sys.platform == "win32"
        self.cfg = load_settings()
        self.history = load_history()
        self.favorites = load_favorites()
        self._fav_keys = {(it.get("source", ""), it.get("result", ""))
                          for it in self.favorites}
        self.popup = PopupWindow(root, self.cfg,
                                 on_favorite=self._favorite_from_popup)
        self.popbutton = PopButton(root, on_click=self._translate_and_popup)
        self._uia = UIAWordGetter() if self._win32 else None
        self._mouse_hook = None
        self._mouse_down = None
        self._last_mouse_pos = (0, 0)
        self._last_mouse_time = time.time()
        self._hover_word_done = None
        self._hover_pending = False
        self._hide_hint_shown = False
        self._hotkey_stop = False
        self._hotkey_tid = None
        self._ocr_disabled = False
        self._ocr_overlay = None
        self.root.title("%s %s" % (APP_NAME, VERSION))
        self.root.geometry("720x800")
        self.root.configure(bg=COLOR_BG)
        self._build_ui()
        self._refresh_history_list()
        self._refresh_favorites_list()
        self._update_engine_label()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Esc：主窗口有焦点时也能关掉悬浮窗（悬浮窗自己也绑了 Esc）
        self.root.bind("<Escape>", self._on_escape)
        if self._win32:
            self._start_hotkey_thread()
            self._start_mouse_hook()
            self.root.after(120, self._poll_mouse_events)
        else:
            self._set_status("提示：Windows 专属功能（划词/悬停/热键/截图 OCR）"
                             "需在 Windows 上运行")

    def _on_escape(self, _event=None):
        if self.popup.is_visible():
            self.popup.close()
        elif self.popbutton.is_visible():
            self.popbutton.hide()

    # ----- 界面 -----
    def _build_ui(self):
        root = self.root
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=(FONT, 10), padding=(16, 8),
                        background=COLOR_BTN_BG, foreground="#555555",
                        borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", COLOR_BG)],
                  foreground=[("selected", COLOR_PRIMARY)])
        style.configure("TCombobox", font=(FONT, 10), padding=4)

        # 顶栏：蓝色「译」标识 + 标题 + 版本
        header = tk.Frame(root, bg=COLOR_BG)
        header.pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(header, text="译", font=(FONT, 16, "bold"),
                 bg=COLOR_PRIMARY, fg="#ffffff", width=2, height=1).pack(side="left")
        tk.Label(header, text="无感翻译", font=(FONT, 15, "bold"),
                 bg=COLOR_BG, fg=COLOR_TEXT).pack(side="left", padx=(10, 0))
        tk.Label(header, text="v" + VERSION, font=(FONT, 10),
                 bg=COLOR_BG, fg=COLOR_TEXT_3).pack(side="left", padx=(6, 0),
                                                    pady=(5, 0))
        _flat_button(header, "退出", self.quit_app).pack(side="right")
        _flat_button(header, "设置", self._open_settings).pack(
            side="right", padx=(0, 8))

        # 目标语言 + 引擎 + 多引擎对照
        top = tk.Frame(root, bg=COLOR_BG)
        top.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(top, text="目标语言：", font=(FONT, 10),
                 bg=COLOR_BG, fg="#333333").pack(side="left")
        self.target_var = tk.StringVar(value=self.cfg.get("target", "auto"))
        target_menu = ttk.Combobox(
            top, textvariable=self.target_var, width=10, state="readonly",
            values=["auto", "zh-CN", "en"])
        target_menu.pack(side="left")
        target_menu.bind("<<ComboboxSelected>>", self._on_target_changed)
        self.engine_label = tk.Label(top, text="", font=(FONT, 10),
                                     bg=COLOR_BG, fg=COLOR_TEXT_2)
        self.engine_label.pack(side="left", padx=(12, 0))
        self.compare_var = tk.BooleanVar(
            value=self.cfg.get("compareEngines", False))
        tk.Checkbutton(top, text="多引擎对照", variable=self.compare_var,
                       font=(FONT, 10), bg=COLOR_BG, fg="#333333",
                       activebackground=COLOR_BG,
                       command=self._on_compare_changed).pack(side="right")

        # 输入
        tk.Label(root, text="输入（中文↔英文自动检测）：",
                 font=(FONT, 10), bg=COLOR_BG, fg="#333333").pack(
            anchor="w", padx=16, pady=(10, 0))
        self.input_text = _styled_text(root, 5)
        self.input_text.pack(fill="x", padx=16, pady=(4, 0))

        btn_row = tk.Frame(root, bg=COLOR_BG)
        btn_row.pack(fill="x", padx=16, pady=10)
        _flat_button(btn_row, "翻 译", self._translate_main,
                     primary=True, font_size=11).pack(side="left")
        _flat_button(btn_row, "复制译文", self._copy_output).pack(
            side="left", padx=(8, 0))
        _flat_button(btn_row, "★ 收藏", self._favorite_from_main).pack(
            side="left", padx=(8, 0))
        _flat_button(btn_row, "清空", self._clear_main).pack(
            side="left", padx=(8, 0))
        tk.Label(btn_row, text="Ctrl+Alt+D 翻译选中 · Ctrl+Alt+A 显示窗口 · Ctrl+Alt+S 截图翻译",
                 font=(FONT, 9), bg=COLOR_BG, fg=COLOR_TEXT_3).pack(side="right")

        # 译文
        tk.Label(root, text="译文：", font=(FONT, 10),
                 bg=COLOR_BG, fg="#333333").pack(anchor="w", padx=16)
        self.output_text = _styled_text(root, 5, bg=COLOR_OUTPUT_BG)
        self.output_text.pack(fill="x", padx=16, pady=(4, 0))
        self.output_text.config(state="disabled")

        self.status_label = tk.Label(root, text="就绪", font=(FONT, 9),
                                     bg=COLOR_BG, fg=COLOR_TEXT_3, anchor="w")
        self.status_label.pack(fill="x", padx=16, pady=(6, 0))

        # 历史 / 生词本
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        hist_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(hist_tab, text="  历史  ")
        tk.Label(hist_tab, text="历史记录（双击回填，★ 为已收藏）：",
                 font=(FONT, 10), bg=COLOR_BG, fg="#333333").pack(
            anchor="w", pady=(6, 0))
        self.history_list = tk.Listbox(
            hist_tab, height=7, font=(FONT, 10), bg=COLOR_BG, fg=COLOR_TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            selectbackground=COLOR_PRIMARY, selectforeground="#ffffff")
        self.history_list.pack(fill="both", expand=True, pady=(4, 0))
        self.history_list.bind("<Double-Button-1>", self._history_double_click)
        hist_btns = tk.Frame(hist_tab, bg=COLOR_BG)
        hist_btns.pack(fill="x", pady=(8, 0))
        _flat_button(hist_btns, "导出 CSV",
                     lambda: self._export_csv(self.history, "无感翻译-历史.csv"),
                     font_size=9).pack(side="left")
        _flat_button(hist_btns, "导出 Anki",
                     lambda: self._export_anki(self.history, "无感翻译-历史-Anki.txt"),
                     font_size=9).pack(side="left", padx=(8, 0))
        _flat_button(hist_btns, "清空历史", self._clear_history,
                     font_size=9).pack(side="right")
        _flat_button(hist_btns, "删除选中", self._delete_history_selected,
                     font_size=9).pack(side="right", padx=(0, 8))

        fav_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(fav_tab, text="  生词本  ")
        tk.Label(fav_tab, text="生词本（双击回填）：",
                 font=(FONT, 10), bg=COLOR_BG, fg="#333333").pack(
            anchor="w", pady=(6, 0))
        self.favorites_list = tk.Listbox(
            fav_tab, height=7, font=(FONT, 10), bg=COLOR_BG, fg=COLOR_TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            selectbackground=COLOR_PRIMARY, selectforeground="#ffffff")
        self.favorites_list.pack(fill="both", expand=True, pady=(4, 0))
        self.favorites_list.bind("<Double-Button-1>",
                                 self._favorites_double_click)
        fav_btns = tk.Frame(fav_tab, bg=COLOR_BG)
        fav_btns.pack(fill="x", pady=(8, 0))
        _flat_button(fav_btns, "导出 CSV",
                     lambda: self._export_csv(self.favorites, "无感翻译-生词本.csv"),
                     font_size=9).pack(side="left")
        _flat_button(fav_btns, "导出 Anki",
                     lambda: self._export_anki(self.favorites, "无感翻译-生词本-Anki.txt"),
                     font_size=9).pack(side="left", padx=(8, 0))
        _flat_button(fav_btns, "清空生词本", self._clear_favorites,
                     font_size=9).pack(side="right")
        _flat_button(fav_btns, "删除选中", self._delete_favorite_selected,
                     font_size=9).pack(side="right", padx=(0, 8))

    def _on_target_changed(self, _event=None):
        self.cfg["target"] = self.target_var.get()
        save_settings(self.cfg)

    def _on_compare_changed(self):
        self.cfg["compareEngines"] = bool(self.compare_var.get())
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

    def _main_translate_done(self, text, result, error, kind, items):
        if error:
            msg = str(error)
            if "润色需要配置 AI Key" in msg:
                self._set_status("润色需要配置 AI Key（请在设置里填写 AI API Key）")
            else:
                self._set_status("翻译失败：" + msg)
            return
        self._set_output(result)
        if kind == "polish":
            self._set_status("润色完成（AI）")
        elif kind == "compare":
            self._set_status("多引擎对照完成（%d 个引擎）" % len(items))
        else:
            self._set_status("翻译完成（%s）" % engine_display_name(self.cfg))
        for engine, res in items:
            self._add_history(text, res, engine=engine)

    def _copy_output(self):
        text = self.output_text.get("1.0", "end").strip()
        if text:
            write_clipboard_text(self.root, text)
            self._set_status("已复制译文到剪贴板")

    def _clear_main(self):
        self.input_text.delete("1.0", "end")
        self._set_output("")
        self._set_status("就绪")

    # ----- 后台翻译（不卡界面） -----
    def _translate_async(self, text, on_done):
        """后台翻译。on_done(text, result, error, kind, items)；
        kind 为 translate / compare / polish；items 是 [(引擎, 译文), ...]，用于记历史。"""
        def worker():
            try:
                if is_polish_case(text, self.cfg):
                    target = target_lang_for(text, self.cfg.get("target", "auto"))
                    result = openai_polish(text, target, self.cfg)
                    self.root.after(
                        0, lambda: on_done(text, result, None, "polish",
                                           [("openAI", result)]))
                elif self.cfg.get("compareEngines"):
                    results = translate_all(text, self.cfg)
                    ok = [(k, v) for k, (v, _e) in results.items() if v]
                    if not ok:
                        err = ""
                        for _k, (_v, e) in results.items():
                            if e:
                                err = e
                                break
                        self.root.after(
                            0, lambda: on_done(text, None, err or "翻译失败",
                                               "compare", []))
                    else:
                        combined = "\n\n".join(
                            "「%s」%s" % (ENGINE_SHORT[k], v) for k, v in ok)
                        self.root.after(
                            0, lambda: on_done(text, combined, None,
                                               "compare", ok))
                else:
                    result = translate(text, self.cfg)
                    self.root.after(
                        0, lambda: on_done(
                            text, result, None, "translate",
                            [(self.cfg.get("engine", "googleFree"), result)]))
            except Exception as e:
                self.root.after(0, lambda: on_done(text, None, e, "translate", []))
        threading.Thread(target=worker, daemon=True).start()

    # ----- 历史 -----
    def _add_history(self, source, result, engine=None):
        item = {"source": source, "result": result,
                "engine": engine or self.cfg.get("engine", "googleFree"),
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
            if len(src) > 26:
                src = src[:26] + "…"
            if len(res) > 26:
                res = res[:26] + "…"
            star = ("★ " if (item.get("source", ""), item.get("result", ""))
                    in self._fav_keys else "")
            self.history_list.insert("end", "%s%s %s → %s" % (
                star, item.get("time", ""), src, res))

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

    # ----- 生词本 -----
    def _add_favorite(self, source, result):
        key = (source, result)
        if key in self._fav_keys:
            return False
        item = {"source": source, "result": result,
                "engine": self.cfg.get("engine", "googleFree"),
                "time": time.strftime("%m-%d %H:%M")}
        self.favorites.insert(0, item)
        self.favorites = self.favorites[:FAVORITES_MAX]
        self._fav_keys.add(key)
        save_favorites(self.favorites)
        self._refresh_favorites_list()
        self._refresh_history_list()
        return True

    def _favorite_from_main(self):
        src = self.input_text.get("1.0", "end").strip()
        res = self.output_text.get("1.0", "end").strip()
        if not src or not res:
            self._set_status("没有可收藏的内容（请先翻译）")
            return
        if self._add_favorite(src, res):
            self._set_status("已收藏到生词本 ★")
        else:
            self._set_status("这条已经在生词本里了")

    def _favorite_from_popup(self, source, result):
        if self._add_favorite(source, result):
            self.popup.set_status("已收藏到生词本 ★")
        else:
            self.popup.set_status("这条已经在生词本里了")

    def _refresh_favorites_list(self):
        self.favorites_list.delete(0, "end")
        for item in self.favorites:
            src = item.get("source", "").replace("\n", " ")
            res = item.get("result", "").replace("\n", " ")
            if len(src) > 26:
                src = src[:26] + "…"
            if len(res) > 26:
                res = res[:26] + "…"
            self.favorites_list.insert("end", "%s %s → %s" % (
                item.get("time", ""), src, res))

    def _favorites_double_click(self, _event=None):
        sel = self.favorites_list.curselection()
        if not sel:
            return
        item = self.favorites[sel[0]]
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", item.get("source", ""))
        self._set_output(item.get("result", ""))
        self._set_status("已从生词本回填")

    def _delete_favorite_selected(self):
        sel = self.favorites_list.curselection()
        if not sel:
            return
        item = self.favorites[sel[0]]
        self._fav_keys.discard((item.get("source", ""), item.get("result", "")))
        del self.favorites[sel[0]]
        save_favorites(self.favorites)
        self._refresh_favorites_list()
        self._refresh_history_list()

    def _clear_favorites(self):
        if not self.favorites:
            return
        if messagebox.askyesno("清空生词本", "确定要清空全部生词本吗？"):
            self.favorites = []
            self._fav_keys = set()
            save_favorites(self.favorites)
            self._refresh_favorites_list()
            self._refresh_history_list()

    # ----- 导出 -----
    def _export_csv(self, items, default_name):
        if not items:
            self._set_status("没有可导出的内容")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name,
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["原文", "译文", "引擎", "时间"])
                for it in items:
                    w.writerow([it.get("source", ""), it.get("result", ""),
                                it.get("engine", ""), it.get("time", "")])
            self._set_status("已导出 CSV：%d 条 → %s" % (len(items), path))
        except Exception as e:
            self._set_status("导出失败：" + str(e))

    def _export_anki(self, items, default_name):
        if not items:
            self._set_status("没有可导出的内容")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile=default_name,
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for it in items:
                    src = it.get("source", "").replace("\t", " ").replace("\n", " ")
                    res = it.get("result", "").replace("\t", " ").replace("\n", " ")
                    f.write("%s\t%s\n" % (src, res))
            self._set_status("已导出 Anki：%d 条 → %s" % (len(items), path))
        except Exception as e:
            self._set_status("导出失败：" + str(e))

    # ----- 设置窗口 -----
    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置")
        dlg.geometry("520x620")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self.root)
        dlg.grab_set()

        engine_var = tk.StringVar(value=self.cfg.get("engine", "googleFree"))
        tk.Label(dlg, text="翻译引擎：", font=(FONT, 10),
                 bg=COLOR_BG, fg="#333333").pack(anchor="w", padx=14, pady=(12, 0))
        for value, label in [("googleFree", "Google 免费（默认，不用 Key）"),
                             ("openAI", "AI 大模型（OpenAI 兼容）"),
                             ("deepL", "DeepL API")]:
            tk.Radiobutton(dlg, text=label, variable=engine_var, value=value,
                           font=(FONT, 10), bg=COLOR_BG, fg="#333333",
                           activebackground=COLOR_BG).pack(anchor="w", padx=24)

        def field(label, key, show=None):
            tk.Label(dlg, text=label, font=(FONT, 10),
                     bg=COLOR_BG, fg="#333333").pack(anchor="w", padx=14, pady=(8, 0))
            entry = _styled_entry(dlg, show=show or "")
            entry.insert(0, self.cfg.get(key, ""))
            entry.pack(fill="x", padx=14, pady=(2, 0))
            return entry

        base_entry = field("AI 接口地址（OpenAI 兼容，例：https://api.openai.com/v1 或 DeepSeek 地址）：",
                           "apiBaseURL")
        key_entry = field("AI API Key：", "apiKey", show="*")
        model_entry = field("AI 模型（例：gpt-4o-mini / deepseek-chat / qwen-plus）：",
                            "model")
        deepl_entry = field("DeepL Key（Free Key 以 :fx 结尾）：", "deepLKey", show="*")

        tk.Label(dlg, text="划词与悬停：", font=(FONT, 10),
                 bg=COLOR_BG, fg="#333333").pack(anchor="w", padx=14, pady=(12, 0))
        select_var = tk.BooleanVar(value=self.cfg.get("selectTranslate", True))
        tk.Checkbutton(dlg, text="划词翻译：选中英文直接翻译（关=选中后点「译」按钮再翻）",
                       variable=select_var, font=(FONT, 10), bg=COLOR_BG,
                       fg="#333333", activebackground=COLOR_BG).pack(
            anchor="w", padx=14)
        hover_var = tk.BooleanVar(value=self.cfg.get("hoverTranslate", False))
        tk.Checkbutton(dlg, text="悬停取词：鼠标停在英文单词上自动翻译",
                       variable=hover_var, font=(FONT, 10), bg=COLOR_BG,
                       fg="#333333", activebackground=COLOR_BG).pack(
            anchor="w", padx=14)
        hover_row = tk.Frame(dlg, bg=COLOR_BG)
        hover_row.pack(fill="x", padx=14, pady=(4, 0))
        tk.Label(hover_row, text="悬停延时（毫秒）：", font=(FONT, 10),
                 bg=COLOR_BG, fg="#333333").pack(side="left")
        delay_spin = tk.Spinbox(hover_row, from_=200, to=1000, increment=50,
                                width=6, font=(FONT, 10), bg=COLOR_BG,
                                relief="flat", highlightthickness=1,
                                highlightbackground=COLOR_BORDER,
                                buttonbackground=COLOR_BTN_BG)
        delay_spin.delete(0, "end")
        delay_spin.insert(0, str(self.cfg.get("hoverDelayMs", 500)))
        delay_spin.pack(side="left")
        tk.Label(hover_row, text="200-1000，默认 500",
                 font=(FONT, 9), bg=COLOR_BG, fg=COLOR_TEXT_3).pack(
            side="left", padx=(8, 0))

        orig_var = tk.BooleanVar(value=self.cfg.get("showOriginal", True))
        tk.Checkbutton(dlg, text="悬浮窗里同时显示原文",
                       variable=orig_var, font=(FONT, 10), bg=COLOR_BG,
                       fg="#333333", activebackground=COLOR_BG).pack(
            anchor="w", padx=14, pady=(10, 0))

        tk.Label(dlg, text="Key 只存在本机（wuganfanyi-settings.json），只发给你填的那个接口。",
                 font=(FONT, 9), bg=COLOR_BG, fg=COLOR_TEXT_3).pack(
            anchor="w", padx=14, pady=(8, 0))

        btn_row = tk.Frame(dlg, bg=COLOR_BG)
        btn_row.pack(fill="x", padx=14, pady=14)

        def save():
            self.cfg["engine"] = engine_var.get()
            self.cfg["apiBaseURL"] = base_entry.get().strip()
            self.cfg["apiKey"] = key_entry.get().strip()
            self.cfg["model"] = model_entry.get().strip()
            self.cfg["deepLKey"] = deepl_entry.get().strip()
            self.cfg["selectTranslate"] = bool(select_var.get())
            self.cfg["hoverTranslate"] = bool(hover_var.get())
            try:
                delay = int(delay_spin.get())
            except Exception:
                delay = 500
            self.cfg["hoverDelayMs"] = max(200, min(1000, delay))
            self.cfg["showOriginal"] = bool(orig_var.get())
            save_settings(self.cfg)
            self._update_engine_label()
            self.popup.cfg = self.cfg
            dlg.destroy()
            self._set_status("设置已保存（立即生效）")

        _flat_button(btn_row, "保存", save, primary=True,
                     font_size=11).pack(side="left")
        _flat_button(btn_row, "取消", dlg.destroy).pack(side="left", padx=(8, 0))

    # ----- 划词：鼠标钩子事件（主线程轮询处理） -----
    def _start_mouse_hook(self):
        if not self._win32:
            return
        try:
            self._mouse_hook = MouseHook()
            self._mouse_hook.start()
        except Exception:
            self._mouse_hook = None

    def _poll_mouse_events(self):
        if self._mouse_hook is not None:
            try:
                while True:
                    ev = self._mouse_hook.events.get_nowait()
                    self._handle_mouse_event(ev)
            except queue.Empty:
                pass
            self._check_hover()
        self.root.after(120, self._poll_mouse_events)

    def _handle_mouse_event(self, ev):
        kind, x, y = ev
        if kind == "down":
            self._mouse_down = (x, y)
            # 点在自己的悬浮窗/译按钮上时不动；点在别处先收起译按钮
            if self.popup.contains_point(x, y) or self.popbutton.geometry_contains(x, y):
                return
            self.popbutton.hide()
        elif kind == "up":
            if self._mouse_down is None:
                return
            x0, y0 = self._mouse_down
            self._mouse_down = None
            dx, dy = x - x0, y - y0
            if dx * dx + dy * dy < 64:  # 位移小于 8px：只是点一下，不是拖拽选中
                return
            if self._foreground_is_own_window():
                return
            if self.popup.contains_point(x, y):
                return
            self.root.after(120, self._do_selection_translate)
        elif kind == "move":
            px, py = self._last_mouse_pos
            self._last_mouse_pos = (x, y)
            self._last_mouse_time = time.time()
            if (x - px) ** 2 + (y - py) ** 2 > 36:
                self._hover_word_done = None

    def _foreground_is_own_window(self):
        """当前前台窗口是不是本程序自己的窗口（主窗口/悬浮窗/译按钮）。"""
        if not self._win32:
            return False
        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            fg = user32.GetForegroundWindow()
            ids = {self.root.winfo_id()}
            if self.popup.win is not None and self.popup.win.winfo_exists():
                ids.add(self.popup.win.winfo_id())
            if self.popbutton.win is not None and self.popbutton.win.winfo_exists():
                ids.add(self.popbutton.win.winfo_id())
            return fg in ids
        except Exception:
            return False

    def _do_selection_translate(self):
        """拖拽选中后：模拟 Ctrl+C 取选中文字，再按划词开关的模式处理。"""
        if not self._win32:
            return
        if self._foreground_is_own_window():
            return
        before = read_clipboard_text(self.root)
        simulate_ctrl_c()
        self.root.after(180, lambda: self._after_selection_copy(before, 0))

    def _after_selection_copy(self, before, attempt):
        text = read_clipboard_text(self.root).strip()
        if (not text or text == (before or "").strip()) and attempt == 0:
            # 剪贴板还没更新（目标程序慢），再等 250ms 重试一次
            self.root.after(250, lambda: self._after_selection_copy(before, 1))
            return
        if not text or text == (before or "").strip():
            return  # 没选中文字（或 Ctrl+C 没取到）
        if len(text) < 2 or not is_english_text(text):
            return  # 只对英文选中触发，中文选中不干扰阅读
        if len(text) > 3000:
            text = text[:3000]
        if self.cfg.get("selectTranslate", True):
            self._translate_and_popup(text)
        else:
            self.popup.close()
            self.popbutton.show(text)

    # ----- 悬停取词 -----
    def _check_hover(self):
        if not self.cfg.get("hoverTranslate", False):
            return
        if self._hover_pending:
            return
        if self._hover_word_done is not None:
            return
        delay = self.cfg.get("hoverDelayMs", 500) / 1000.0
        if time.time() - self._last_mouse_time < delay:
            return
        x, y = self._last_mouse_pos
        if self._foreground_is_own_window():
            return
        self._hover_pending = True

        def worker():
            word = self._uia.word_at(x, y) if self._uia else ""
            self.root.after(0, lambda: self._on_hover_word(word, x, y))

        threading.Thread(target=worker, daemon=True).start()

    def _on_hover_word(self, word, x, y):
        self._hover_pending = False
        mx, my = self._last_mouse_pos
        if abs(mx - x) > 6 or abs(my - y) > 6:
            return  # 鼠标已经移走了
        if not word:
            return
        word = word.strip().strip(".,;:!?\"'()[]{}<>")
        if not WORD_RE.match(word):
            return
        if word == self._hover_word_done:
            return
        self._hover_word_done = word
        self._translate_and_popup(word)

    # ----- 悬浮窗翻译 -----
    def _translate_and_popup(self, text):
        self.popbutton.hide()
        self.popup.show_loading(text)
        self._translate_async(text, on_done=self._popup_translate_done)

    def _popup_translate_done(self, text, result, error, kind, items):
        if error:
            self.popup.show_error(text, error)
            return
        note = None
        if kind == "polish":
            note = "润色结果（AI）"
        elif kind == "compare":
            note = "多引擎对照"
        self.popup.show_result(text, result, note=note)
        for engine, res in items:
            self._add_history(text, res, engine=engine)

    # ----- 全局快捷键 -----
    def _ocr_usable(self):
        if not self._win32:
            return False
        return bool(shutil.which("powershell") or shutil.which("pwsh"))

    def _start_hotkey_thread(self):
        def hotkey_loop():
            try:
                user32 = ctypes.windll.user32
                ok1 = user32.RegisterHotKey(None, 1, HOTKEY_TRANSLATE_MODS,
                                            HOTKEY_TRANSLATE_VK)
                ok2 = user32.RegisterHotKey(None, 2, HOTKEY_WINDOW_MODS,
                                            HOTKEY_WINDOW_VK)
                ok3 = False
                if self._ocr_usable():
                    ok3 = user32.RegisterHotKey(None, 3, HOTKEY_OCR_MODS,
                                                HOTKEY_OCR_VK)
                    if not ok3:
                        self._ocr_disabled = True
                else:
                    self._ocr_disabled = True
                if not ok1 or not ok2:
                    self.root.after(0, lambda: self._set_status(
                        "全局快捷键注册失败（可能被别的程序占了）：Ctrl+Alt+D / Ctrl+Alt+A"))
                if self._ocr_disabled:
                    self.root.after(0, lambda: self._set_status(
                        "截图 OCR 不可用（缺少 PowerShell 或 OCR 组件），Ctrl+Alt+S 已禁用"))
                self._hotkey_tid = threading.get_ident()
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
                        elif msg.wParam == 3:
                            self.root.after(0, self._on_hotkey_ocr)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                pass
            finally:
                try:
                    user32 = ctypes.windll.user32
                    user32.UnregisterHotKey(None, 1)
                    user32.UnregisterHotKey(None, 2)
                    user32.UnregisterHotKey(None, 3)
                except Exception:
                    pass

        threading.Thread(target=hotkey_loop, daemon=True).start()

    def _on_hotkey_translate(self):
        """Ctrl+Alt+D：模拟 Ctrl+C 取当前选中文字，再翻译（手动方式，不限语言）。"""
        before = read_clipboard_text(self.root)
        simulate_ctrl_c()
        # 等剪贴板更新
        self.root.after(200, lambda: self._after_copy(before))

    def _after_copy(self, before):
        text = read_clipboard_text(self.root).strip()
        if not text or text == (before or "").strip():
            self.popup.show_hint("没有选中文字，请先选中一段文字再按 Ctrl+Alt+D")
            return
        self._translate_and_popup(text)

    def _toggle_main_window(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_set()
        else:
            self._on_close()

    # ----- 截图 OCR -----
    def _on_hotkey_ocr(self):
        """Ctrl+Alt+S：截图翻译。"""
        if self._ocr_disabled:
            self.popup.show_hint("截图 OCR 不可用（缺少 PowerShell 或 OCR 组件）")
            return
        if self._ocr_overlay is not None:
            return  # 已在框选
        self._ocr_overlay = ScreenshotOverlay(
            self.root, self._on_ocr_region, self._on_ocr_cancel)
        self._ocr_overlay.show()

    def _on_ocr_cancel(self):
        self._ocr_overlay = None

    def _on_ocr_region(self, x, y, w, h):
        self._ocr_overlay = None
        self.popup.show_loading("正在识别截图文字…")

        def worker():
            try:
                tmp = os.path.join(tempfile.gettempdir(), "wuganfanyi-shot.bmp")
                capture_rect_to_bmp(x, y, w, h, tmp)
                text = ocr_image_file(tmp)
                err = ""
            except Exception as e:
                text = ""
                err = str(e)
            self.root.after(0, lambda: self._on_ocr_done(text, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ocr_done(self, text, err):
        if not text:
            self.popup.show_hint("没有识别到文字" + ("（%s）" % err if err else ""))
            return
        self._translate_and_popup(text)

    # ----- 关闭 / 退出 -----
    def _on_close(self):
        """点 X：隐藏到后台（快捷键和划词监听继续工作），不退出。"""
        self.root.withdraw()
        if not self._hide_hint_shown:
            self._hide_hint_shown = True
            self.popup.show_hint(
                "已隐藏到后台，Ctrl+Alt+D 还能翻译，Ctrl+Alt+A 叫回主窗口；"
                "要彻底退出请点主窗口里的「退出」。")

    def quit_app(self):
        self._hotkey_stop = True
        if self._mouse_hook is not None:
            self._mouse_hook.stop()
        if self._hotkey_tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._hotkey_tid, 0x0012, 0, 0)  # WM_QUIT，唤醒热键线程
            except Exception:
                pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    if sys.platform != "win32":
        print("提示：这是 Windows 版，在 %s 上只能做语法检查，"
              "划词/悬停/热键/截图 OCR 等功能要在 Windows 上跑才生效。"
              % sys.platform, file=sys.stderr)
    elif not ensure_single_instance():
        return  # 已有实例在跑，并已把它唤到前台
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

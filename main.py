"""
Novel2Script AI - 图形界面入口（PyCharm 右键 Run 即可）

功能：
1. 粘贴 / 打开至少 3 章小说文本。
2. 一键转换为结构化剧本 YAML，并同时给出标注【角色】【对话】【环境】的可读剧本。
3. 大模型由 LangChain + LangGraph 驱动；在项目根目录 .env 中填入 LLM_API_KEY 即可启用，
   未配置时自动回退到内置规则引擎，保证离线也能出稿。

使用方式：
1. 用 PyCharm 打开 novel2script_ai 文件夹。
2. （可选）复制 .env.example 为 .env，填入你的 API Key。
3. 右键 main.py → Run 'main'。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# 允许直接 Run main.py：把 src 加入模块搜索路径
import sys

SRC = Path(__file__).resolve().parent / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from novel2script.config import LLMConfig
from novel2script.models import ConvertOptions
from novel2script.service import build_novel_from_text, convert_novel
from novel2script.renderer import render_readable_script
from novel2script.yaml_io import dump_yaml


# ── 主题色彩 ──────────────────────────────────────────────────────

class Colors:
    """统一的调色板，保持界面风格一致。"""
    BG = "#f5f7fa"               # 整体底色
    CARD_BG = "#ffffff"          # 卡片/面板背景
    PRIMARY = "#4a6cf7"          # 主色（按钮等）
    PRIMARY_HOVER = "#3b5de7"    # 主色悬停
    SUCCESS = "#10b981"          # 成功绿
    WARNING = "#f59e0b"          # 警告橙
    DANGER = "#ef4444"           # 错误红
    TEXT = "#1e293b"             # 主文字
    TEXT_LIGHT = "#64748b"       # 辅文字
    BORDER = "#e2e8f0"           # 边框线
    HEADER_BG = "#1e293b"        # 顶部栏背景
    HEADER_FG = "#ffffff"        # 顶部栏文字
    ACCENT = "#8b5cf6"           # 强调紫
    INPUT_BG = "#f8fafc"         # 输入区背景


APP_TITLE = "Novel2Script AI · 小说转剧本（LangChain + LangGraph）"

EXAMPLE_TEXT = """第一章 旧站台
夜色落下时，林夏来到废弃的火车站。站台上全是雾，远处的灯像被水泡过一样模糊。

林夏说："是谁让我来这里？"

一阵风吹过，候车厅的铁门发出刺耳的响声。她握紧手机，屏幕上只有一条陌生短信：午夜十二点，旧站台见。

第二章 匿名信
第二天上午，林夏回到办公室。桌上多了一封没有署名的信，信纸边缘被雨水泡皱。

顾言问："你脸色怎么这么差？"

林夏没有回答。她打开信，里面只有一张旧照片，照片背面写着：别相信你父亲。

第三章 夜访
深夜，林夏按照照片上的地址来到一条狭窄的巷子。巷子尽头有一间亮着灯的旧屋。

门内传来老人咳嗽的声音。林夏刚要敲门，屋里的灯忽然灭了。

顾言低声说："我们可能被人跟踪了。"
"""


# ── 自定义控件 ─────────────────────────────────────────────────────

class RoundedButton(tk.Canvas):
    """带圆角和悬停效果的美观按钮。"""

    def __init__(
        self, parent, text="", command=None, width=120, height=36,
        bg=Colors.PRIMARY, fg="#ffffff", hover_bg=Colors.PRIMARY_HOVER,
        font_size=10, **kwargs,
    ):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=parent["bg"], **kwargs)
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg
        self._width = width
        self._height = height
        self._font = ("Microsoft YaHei UI", font_size, "bold")
        self._disabled = False
        self._draw(bg)
        self.bind("<Enter>", lambda e: self._on_enter())
        self.bind("<Leave>", lambda e: self._on_leave())
        self.bind("<Button-1>", lambda e: self._on_click())

    def _draw(self, color):
        self.delete("all")
        r = 8
        w, h = self._width, self._height
        # 圆角矩形
        self.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=color, outline=color)
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=color, outline=color)
        self.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=color, outline=color)
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=color, outline=color)
        self.create_rectangle(r, 0, w-r, h, fill=color, outline=color)
        self.create_rectangle(0, r, w, h-r, fill=color, outline=color)
        # 文字
        fg = "#aaaaaa" if self._disabled else self._fg
        self.create_text(w//2, h//2, text=self._text, fill=fg, font=self._font)

    def _on_enter(self):
        if not self._disabled:
            self._draw(self._hover_bg)

    def _on_leave(self):
        self._draw(self._bg)

    def _on_click(self):
        if not self._disabled and self._command:
            self._command()

    def set_disabled(self, disabled: bool):
        self._disabled = disabled
        self._draw(self._bg)


class StatusBadge(tk.Frame):
    """引擎状态指示器，带有小圆点图标。"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=Colors.CARD_BG, **kwargs)
        self._dot = tk.Canvas(self, width=10, height=10, highlightthickness=0, bg=Colors.CARD_BG)
        self._dot.pack(side=tk.LEFT, padx=(0, 6))
        self._label = tk.Label(self, text="", bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT,
                               font=("Microsoft YaHei UI", 9))
        self._label.pack(side=tk.LEFT)

    def set_status(self, text: str, color: str):
        self._dot.delete("all")
        self._dot.create_oval(2, 2, 9, 9, fill=color, outline=color)
        self._label.config(text=text, fg=color)


# ── 主应用 ─────────────────────────────────────────────────────────

class Novel2ScriptApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1360x860")
        self.root.configure(bg=Colors.BG)
        self.root.minsize(1000, 650)

        self.config = LLMConfig.from_env()
        self.last_screenplay: dict | None = None

        self.title_var = tk.StringVar(value="雾城来信")
        self.author_var = tk.StringVar(value="示例作者")
        self.format_var = tk.StringVar(value="web_series")
        self.use_llm_var = tk.BooleanVar(value=self.config.is_configured)
        self.status_var = tk.StringVar(value="就绪 · 请粘贴至少 3 章小说文本，然后点击「生成剧本」")

        self._setup_styles()
        self._build_ui()
        self._refresh_engine_hint()

    def _setup_styles(self):
        """配置 ttk 样式。"""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TNotebook", background=Colors.BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=Colors.BORDER, padding=[16, 8],
                        font=("Microsoft YaHei UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", Colors.CARD_BG)],
                  foreground=[("selected", Colors.PRIMARY)])

        style.configure("TCheckbutton", background=Colors.CARD_BG,
                        font=("Microsoft YaHei UI", 9))

        style.configure("TProgressbar", troughcolor=Colors.BORDER,
                        background=Colors.PRIMARY, thickness=4)

    # ── UI 构建 ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        # 顶部标题栏
        header = tk.Frame(self.root, bg=Colors.HEADER_BG, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="📖 Novel2Script AI",
            bg=Colors.HEADER_BG, fg=Colors.HEADER_FG,
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side=tk.LEFT, padx=20, pady=12)

        tk.Label(
            header, text="小说转结构化剧本  |  LangChain + LangGraph",
            bg=Colors.HEADER_BG, fg="#94a3b8",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, pady=12)

        # 工具栏
        toolbar = tk.Frame(self.root, bg=Colors.CARD_BG, padx=16, pady=10)
        toolbar.pack(fill=tk.X, padx=12, pady=(12, 0))

        # 左侧参数区
        params = tk.Frame(toolbar, bg=Colors.CARD_BG)
        params.pack(side=tk.LEFT, fill=tk.X)

        self._make_label_entry(params, "标题", self.title_var, 14, 0)
        self._make_label_entry(params, "作者", self.author_var, 10, 1)

        # 格式选择
        tk.Label(params, text="格式", bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT,
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=4, padx=(12, 4))
        fmt_menu = ttk.Combobox(
            params, textvariable=self.format_var, width=12, state="readonly",
            values=["film", "web_series", "short_drama", "animation",
                    "audio_drama", "stage_play", "unknown"],
        )
        fmt_menu.grid(row=0, column=5, padx=4)

        # 大模型开关
        ttk.Checkbutton(
            params, text="启用大模型", variable=self.use_llm_var,
            command=self._refresh_engine_hint, style="TCheckbutton",
        ).grid(row=0, column=6, padx=(16, 0))

        # 右侧按钮区
        btn_frame = tk.Frame(toolbar, bg=Colors.CARD_BG)
        btn_frame.pack(side=tk.RIGHT)

        RoundedButton(btn_frame, text="载入示例", command=self.load_example,
                      width=90, height=32, bg="#6b7280", hover_bg="#4b5563",
                      font_size=9).pack(side=tk.LEFT, padx=4)
        RoundedButton(btn_frame, text="打开文件", command=self.open_text_file,
                      width=90, height=32, bg="#6b7280", hover_bg="#4b5563",
                      font_size=9).pack(side=tk.LEFT, padx=4)
        self.convert_btn = RoundedButton(
            btn_frame, text="✦ 生成剧本", command=self.convert,
            width=120, height=34, bg=Colors.PRIMARY, hover_bg=Colors.PRIMARY_HOVER,
            font_size=10,
        )
        self.convert_btn.pack(side=tk.LEFT, padx=4)
        RoundedButton(btn_frame, text="保存 YAML", command=self.save_yaml,
                      width=100, height=32, bg=Colors.SUCCESS, hover_bg="#059669",
                      font_size=9).pack(side=tk.LEFT, padx=4)
        RoundedButton(btn_frame, text="保存文本", command=self.save_readable,
                      width=90, height=32, bg=Colors.SUCCESS, hover_bg="#059669",
                      font_size=9).pack(side=tk.LEFT, padx=4)

        # 引擎状态
        status_bar = tk.Frame(self.root, bg=Colors.CARD_BG, padx=16, pady=6)
        status_bar.pack(fill=tk.X, padx=12)
        self.engine_badge = StatusBadge(status_bar)
        self.engine_badge.pack(side=tk.LEFT)

        # 进度条（隐藏直到开始转换）
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", style="TProgressbar")

        # 主体内容
        body = tk.Frame(self.root, bg=Colors.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # 左侧输入面板
        left_panel = tk.Frame(body, bg=Colors.CARD_BG, bd=0, relief=tk.FLAT)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        left_header = tk.Frame(left_panel, bg=Colors.CARD_BG, padx=12, pady=8)
        left_header.pack(fill=tk.X)
        tk.Label(
            left_header, text="📝 小说文本输入",
            bg=Colors.CARD_BG, fg=Colors.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            left_header, text="至少 3 章，用「第一章 / 第二章…」标题分隔",
            bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT,
            font=("Microsoft YaHei UI", 8),
        ).pack(side=tk.LEFT, padx=12)

        self.input_text = scrolledtext.ScrolledText(
            left_panel, wrap=tk.WORD, font=("Microsoft YaHei UI", 10),
            bg=Colors.INPUT_BG, fg=Colors.TEXT, relief=tk.FLAT,
            insertbackground=Colors.PRIMARY, selectbackground=Colors.PRIMARY,
            selectforeground="#ffffff", padx=12, pady=8, borderwidth=0,
        )
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))
        self.input_text.insert("1.0", EXAMPLE_TEXT)

        # 右侧输出面板
        right_panel = tk.Frame(body, bg=Colors.CARD_BG, bd=0, relief=tk.FLAT)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        right_header = tk.Frame(right_panel, bg=Colors.CARD_BG, padx=12, pady=8)
        right_header.pack(fill=tk.X)
        tk.Label(
            right_header, text="🎬 转换结果",
            bg=Colors.CARD_BG, fg=Colors.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        self.scene_count_label = tk.Label(
            right_header, text="",
            bg=Colors.CARD_BG, fg=Colors.ACCENT,
            font=("Microsoft YaHei UI", 9),
        )
        self.scene_count_label.pack(side=tk.RIGHT)

        self.tabs = ttk.Notebook(right_panel, style="TNotebook")
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.readable_text = scrolledtext.ScrolledText(
            self.tabs, wrap=tk.WORD, font=("Microsoft YaHei UI", 10),
            bg=Colors.INPUT_BG, fg=Colors.TEXT, relief=tk.FLAT,
            padx=12, pady=8, borderwidth=0,
        )
        self.yaml_text = scrolledtext.ScrolledText(
            self.tabs, wrap=tk.NONE, font=("Consolas", 10),
            bg="#1e1e2e", fg="#cdd6f4", relief=tk.FLAT,
            insertbackground="#cdd6f4", selectbackground="#45475a",
            padx=12, pady=8, borderwidth=0,
        )
        self.tabs.add(self.readable_text, text="  📄 可读剧本（角色 / 对话 / 环境）  ")
        self.tabs.add(self.yaml_text, text="  📋 结构化 YAML  ")

        # 底部状态栏
        bottom = tk.Frame(self.root, bg=Colors.BG, padx=16, pady=6)
        bottom.pack(fill=tk.X)
        tk.Label(
            bottom, textvariable=self.status_var,
            bg=Colors.BG, fg=Colors.TEXT_LIGHT, anchor="w",
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=tk.X)

    def _make_label_entry(self, parent, label, var, width, col):
        tk.Label(parent, text=label, bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT,
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=col*2, padx=(0, 4))
        entry = tk.Entry(
            parent, textvariable=var, width=width,
            font=("Microsoft YaHei UI", 10), relief=tk.FLAT,
            bg=Colors.INPUT_BG, fg=Colors.TEXT, highlightthickness=1,
            highlightcolor=Colors.PRIMARY, highlightbackground=Colors.BORDER,
        )
        entry.grid(row=0, column=col*2+1, padx=(0, 8))

    # ── 行为 ────────────────────────────────────────────────

    def _refresh_engine_hint(self) -> None:
        if self.use_llm_var.get():
            if self.config.is_configured:
                self.engine_badge.set_status(
                    f"大模型就绪 · {self.config.model} (LangChain+LangGraph)",
                    Colors.SUCCESS,
                )
            else:
                self.engine_badge.set_status(
                    "未配置 API Key · 请在 .env 填写 LLM_API_KEY · 当前使用规则引擎",
                    Colors.WARNING,
                )
        else:
            self.engine_badge.set_status("规则引擎模式（离线，无需联网）", Colors.TEXT_LIGHT)

    def load_example(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", EXAMPLE_TEXT)
        self.status_var.set("已载入示例文本")

    def open_text_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择小说文本文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="gbk", errors="ignore")
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", text)
        self.status_var.set(f"已打开：{Path(path).name}")

    def convert(self) -> None:
        raw_text = self.input_text.get("1.0", tk.END).strip()
        title = self.title_var.get().strip() or "未命名剧本"
        author = self.author_var.get().strip()
        fmt = self.format_var.get().strip() or "web_series"
        prefer_llm = self.use_llm_var.get()

        self.convert_btn.set_disabled(True)
        engine = "大模型" if (prefer_llm and self.config.is_configured) else "规则引擎"
        self.status_var.set(f"⏳ 正在用{engine}生成剧本，请稍候…")
        self.progress.pack(fill=tk.X, padx=12, pady=(0, 4))
        self.progress.start(15)

        def worker() -> None:
            try:
                novel = build_novel_from_text(raw_text, title=title, author=author, fmt=fmt)
                options = ConvertOptions(default_format=fmt)
                screenplay, used_llm = convert_novel(novel, options=options, prefer_llm=prefer_llm)
                yaml_out = dump_yaml(screenplay)
                readable = render_readable_script(screenplay)
                self.root.after(0, self._on_success, screenplay, yaml_out, readable, used_llm)
            except Exception as exc:
                self.root.after(0, self._on_error, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, screenplay: dict, yaml_out: str, readable: str, used_llm: bool) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.last_screenplay = screenplay
        self.readable_text.delete("1.0", tk.END)
        self.readable_text.insert("1.0", readable)
        self.yaml_text.delete("1.0", tk.END)
        self.yaml_text.insert("1.0", yaml_out)
        self.tabs.select(0)
        self.convert_btn.set_disabled(False)

        scene_count = len(screenplay.get("script", {}).get("scenes", []))
        char_count = len(screenplay.get("script", {}).get("characters", []))
        self.scene_count_label.config(text=f"{char_count} 角色 · {scene_count} 场景")

        engine = "大模型 (LangChain+LangGraph)" if used_llm else "规则引擎"
        note = "" if used_llm or not self.use_llm_var.get() else "（大模型不可用，已回退）"
        self.status_var.set(f"✅ 生成完成 · {engine}{note} · {scene_count} 个场景 · 可保存输出")

    def _on_error(self, exc: Exception) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.convert_btn.set_disabled(False)
        messagebox.showerror("生成失败", str(exc))
        self.status_var.set(f"❌ 生成失败：{exc}")

    def save_yaml(self) -> None:
        text = self.yaml_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("没有可保存内容", "请先点击「生成剧本」。")
            return
        path = filedialog.asksaveasfilename(
            title="保存剧本 YAML",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("YAML files", "*.yml")],
            initialfile="output_script.yaml",
        )
        if not path:
            return
        Path(path).write_text(text + "\n", encoding="utf-8")
        self.status_var.set(f"✅ 已保存 YAML：{Path(path).name}")

    def save_readable(self) -> None:
        text = self.readable_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("没有可保存内容", "请先点击「生成剧本」。")
            return
        path = filedialog.asksaveasfilename(
            title="保存可读剧本文本",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="screenplay_readable.txt",
        )
        if not path:
            return
        Path(path).write_text(text + "\n", encoding="utf-8")
        self.status_var.set(f"✅ 已保存剧本文本：{Path(path).name}")


def main() -> None:
    window = tk.Tk()
    Novel2ScriptApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()


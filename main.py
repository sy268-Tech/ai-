"""
Novel2Script AI - 图形界面入口

功能：
1. 粘贴 / 打开小说文本（支持单章或多章）。
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
from novel2script.service import build_novel_from_text, convert_novel, extend_screenplay, _try_parse_structured_text
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
        self._cancel_event: threading.Event | None = None
        self._cancel_btn: RoundedButton | None = None
        self._generation_id: int = 0  # 递增 ID，用于忽略已取消/旧生成的回调

        self.title_var = tk.StringVar(value="雾城来信")
        self.author_var = tk.StringVar(value="示例作者")
        self.format_var = tk.StringVar(value="web_series")
        self.use_llm_var = tk.BooleanVar(value=self.config.is_configured)
        self.status_var = tk.StringVar(value="就绪 · 请粘贴小说文本，然后点击「生成剧本」")

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
        self.extend_btn = RoundedButton(
            btn_frame, text="✦ 续写剧本", command=self.extend_script,
            width=120, height=34, bg=Colors.ACCENT, hover_bg="#7c3aed",
            font_size=10,
        )
        self.extend_btn.pack(side=tk.LEFT, padx=4)
        self._cancel_btn = RoundedButton(
            btn_frame, text="✕ 取消生成", command=self.cancel_generation,
            width=100, height=34, bg=Colors.DANGER, hover_bg="#dc2626",
            font_size=10,
        )
        # 取消按钮初始隐藏
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
            left_header, text="支持多种分隔：第X章 / Scene 1 / Chat1 / 1. 标题 / ---，也可单章直接转换",
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

        # ── 配置可读剧本的颜色标签 ──────────────────────────
        self._setup_readable_tags()

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

    def _setup_readable_tags(self) -> None:
        """配置可读剧本的颜色标签（角色/对白/场景/环境等）。"""
        tags_config = {
            "scene_header":    {"foreground": "#7c3aed", "font": ("Microsoft YaHei UI", 11, "bold")},   # 场景标题 ◇
            "environment":     {"foreground": "#d97706"},                                                # 环境描述 【环境】
            "character":       {"foreground": "#2563eb"},                                                # 角色 【角色】●
            "dialogue":        {"foreground": "#059669"},                                                # 对白 【对话】
            "action_beat":     {"foreground": "#6b7280"},                                                # 动作/旁白/音效
            "location":        {"foreground": "#0891b2"},                                                # 地点 ◆
            "transition":      {"foreground": "#dc2626"},                                                # 转场
            "title_line":      {"foreground": "#1e293b", "font": ("Microsoft YaHei UI", 10, "bold")},    # 标题/分隔线
            "section_header":  {"foreground": "#4a6cf7", "font": ("Microsoft YaHei UI", 10, "bold")},    # 【角色表】【地点表】【正文】
            "meta_info":       {"foreground": "#64748b"},                                                # 元信息（一句话故事等）
        }
        for tag_name, cfg in tags_config.items():
            self.readable_text.tag_configure(tag_name, **cfg)

    def _apply_readable_colors(self) -> None:
        """扫描可读剧本内容，按行类型应用颜色标签。"""
        text_widget = self.readable_text
        content = text_widget.get("1.0", tk.END)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            ln = f"{i + 1}.0"
            le = f"{i + 1}.end"

            # 场景标题行：◇ 第N场 ...
            if line.startswith("◇"):
                text_widget.tag_add("scene_header", ln, le)
            # 环境标注
            elif "【环境】" in line:
                text_widget.tag_add("environment", ln, le)
            # 对话行
            elif "【对话】" in line:
                text_widget.tag_add("dialogue", ln, le)
            # 角色在场
            elif "【角色】" in line:
                text_widget.tag_add("character", ln, le)
            # 转场
            elif "〔转场" in line:
                text_widget.tag_add("transition", ln, le)
            # 动作/旁白/音效/画面/停顿/插入
            elif any(f"（{t}）" in line for t in ("动作", "旁白", "音效", "画面", "停顿", "插入")):
                text_widget.tag_add("action_beat", ln, le)
            # 地点表条目
            elif line.startswith("◆"):
                text_widget.tag_add("location", ln, le)
            # 章节标题：【角色表】【地点表】【正文】
            elif line.strip() in ("【角色表】", "【地点表】") or line.strip().startswith("【正文】"):
                text_widget.tag_add("section_header", ln, le)
            # 分隔线
            elif line.strip().startswith("══") or line.strip().startswith("──"):
                text_widget.tag_add("title_line", ln, le)
            # 标题行（以空格缩进 + 《开头的书名）
            elif "《" in line and "》" in line and ("剧本初稿" in line or "剧本" in line):
                text_widget.tag_add("title_line", ln, le)
            # 元信息
            elif line.startswith("一句话故事：") or line.startswith("剧情梗概：") or line.startswith("改编自"):
                text_widget.tag_add("meta_info", ln, le)
            # 角色表条目 ●
            elif line.strip().startswith("●"):
                text_widget.tag_add("character", ln, le)

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

        # 如果文件是结构化 YAML，自动提取标题和作者
        _, meta = _try_parse_structured_text(text)
        if meta.get("title"):
            self.title_var.set(meta["title"])
        if meta.get("author"):
            self.author_var.set(meta["author"])

        self.status_var.set(f"已打开：{Path(path).name}")

    def convert(self) -> None:
        raw_text = self.input_text.get("1.0", tk.END).strip()
        title = self.title_var.get().strip() or "未命名剧本"
        author = self.author_var.get().strip()
        fmt = self.format_var.get().strip() or "web_series"
        prefer_llm = self.use_llm_var.get()

        # 从结构化 YAML 中提取元数据，自动同步标题/作者到 GUI
        _, yaml_meta = _try_parse_structured_text(raw_text)
        if yaml_meta.get("title"):
            title = yaml_meta["title"]
            self.root.after(0, lambda t=title: self.title_var.set(t))
        if yaml_meta.get("author"):
            author = yaml_meta["author"]
            self.root.after(0, lambda a=author: self.author_var.set(a))
        if yaml_meta.get("format"):
            fmt = yaml_meta["format"]

        # 取消上一次未完成的生成，并递增代际 ID 使旧回调失效
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._generation_id += 1
        gen_id = self._generation_id

        self._cancel_event = threading.Event()
        self.convert_btn.set_disabled(True)
        self._cancel_btn.pack(side=tk.LEFT, padx=4)
        engine = "大模型" if (prefer_llm and self.config.is_configured) else "规则引擎"
        self.status_var.set(f"⏳ 正在用{engine}生成剧本，请稍候…（可点击「取消生成」）")
        self.progress.pack(fill=tk.X, padx=12, pady=(0, 4))
        self.progress.start(15)

        cancel_ev = self._cancel_event  # 捕获引用，避免后续覆盖影响本线程

        def worker() -> None:
            try:
                novel = build_novel_from_text(raw_text, title=title, author=author, fmt=fmt, config=self.config)
                options = ConvertOptions(default_format=fmt)
                screenplay, used_llm = convert_novel(novel, options=options, prefer_llm=prefer_llm)
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                yaml_out = dump_yaml(screenplay)
                readable = render_readable_script(screenplay)
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                self.root.after(0, self._on_success, screenplay, yaml_out, readable, used_llm, gen_id)
            except Exception as exc:
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                self.root.after(0, self._on_error, exc, gen_id)

        threading.Thread(target=worker, daemon=True).start()

    def extend_script(self) -> None:
        """续写剧本——在已有剧本基础上追加新场景。"""
        if self.last_screenplay is None:
            messagebox.showwarning("没有可续写的剧本", "请先生成或加载一份剧本，然后再点击「续写剧本」。")
            return

        new_text = self.input_text.get("1.0", tk.END).strip()
        if not new_text:
            messagebox.showwarning("文本为空", "请在输入区粘贴续写内容，然后点击「续写剧本」。")
            return

        # 取消上一次未完成的操作，并递增代际 ID 使旧回调失效
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._generation_id += 1
        gen_id = self._generation_id

        prefer_llm = bool(self.use_llm_var.get() and self.config.is_configured)
        self._cancel_event = threading.Event()
        engine = "大模型续写" if prefer_llm else "规则引擎续写"
        self.status_var.set(f"⏳ 正在用{engine}续写剧本，请稍候…（可点击「取消生成」）")
        self.progress.pack(fill=tk.X, padx=12, pady=(0, 4))
        self.progress.start(15)
        self.convert_btn.set_disabled(True)
        self.extend_btn.set_disabled(True)
        self._cancel_btn.pack(side=tk.LEFT, padx=4)

        old_scene_count = len(self.last_screenplay.get("script", {}).get("scenes", []))
        old_char_count = len(self.last_screenplay.get("script", {}).get("characters", []))

        cancel_ev = self._cancel_event  # 捕获引用

        def worker() -> None:
            try:
                options = ConvertOptions(default_format=self.format_var.get())
                screenplay, used_llm = extend_screenplay(
                    self.last_screenplay,
                    new_text,
                    prefer_llm=prefer_llm,
                    options=options,
                )
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                yaml_out = dump_yaml(screenplay)
                readable = render_readable_script(screenplay)
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                self.root.after(
                    0, self._on_extend_success,
                    screenplay, yaml_out, readable, used_llm,
                    old_scene_count, old_char_count, gen_id,
                )
            except Exception as exc:
                if cancel_ev.is_set():
                    self.root.after(0, self._on_cancel, gen_id)
                    return
                self.root.after(0, self._on_error, exc, gen_id)

        threading.Thread(target=worker, daemon=True).start()

    def _on_extend_success(
        self, screenplay: dict, yaml_out: str, readable: str,
        used_llm: bool, old_scene_count: int, old_char_count: int,
        gen_id: int = 0,
    ) -> None:
        if gen_id != self._generation_id:
            return  # 已被取消或有更新的生成，丢弃过期结果
        self.progress.stop()
        self.progress.pack_forget()
        self._cancel_btn.pack_forget()
        self.last_screenplay = screenplay
        self.readable_text.delete("1.0", tk.END)
        self.readable_text.insert("1.0", readable)
        self._apply_readable_colors()
        self.yaml_text.delete("1.0", tk.END)
        self.yaml_text.insert("1.0", yaml_out)
        self.tabs.select(0)
        self.convert_btn.set_disabled(False)
        self.extend_btn.set_disabled(False)

        scene_count = len(screenplay.get("script", {}).get("scenes", []))
        char_count = len(screenplay.get("script", {}).get("characters", []))
        new_scenes = scene_count - old_scene_count
        new_chars = char_count - old_char_count
        self.scene_count_label.config(text=f"{char_count} 角色 · {scene_count} 场景")

        engine = "大模型续写 (LangChain+LangGraph)" if used_llm else "规则引擎续写"
        note = f"（续写新增 {new_scenes} 场景"
        if new_chars > 0:
            note += f"，{new_chars} 新角色"
        note += "）"
        self.status_var.set(f"✅ 续写完成 · {engine}{note} · 现共 {scene_count} 个场景")

    def _on_success(self, screenplay: dict, yaml_out: str, readable: str, used_llm: bool,
                    gen_id: int = 0) -> None:
        if gen_id != self._generation_id:
            return  # 已被取消或有更新的生成，丢弃过期结果
        self.progress.stop()
        self.progress.pack_forget()
        self._cancel_btn.pack_forget()
        self.last_screenplay = screenplay
        self.readable_text.delete("1.0", tk.END)
        self.readable_text.insert("1.0", readable)
        self._apply_readable_colors()
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

    def _on_error(self, exc: Exception, gen_id: int = 0) -> None:
        if gen_id != self._generation_id:
            return  # 已被取消或有更新的生成，忽略过期错误
        self.progress.stop()
        self.progress.pack_forget()
        self._cancel_btn.pack_forget()
        self.convert_btn.set_disabled(False)
        self.extend_btn.set_disabled(False)
        messagebox.showerror("生成失败", str(exc))
        self.status_var.set(f"❌ 生成失败：{exc}")

    def cancel_generation(self) -> None:
        """用户点击取消生成按钮——立即恢复 UI，不等待 worker 线程。"""
        if self._cancel_event is not None:
            self._cancel_event.set()
        # 立即在主线程恢复 UI，不等待 worker 线程（LLM 调用可能很久才返回）
        self.progress.stop()
        self.progress.pack_forget()
        self._cancel_btn.pack_forget()
        self.convert_btn.set_disabled(False)
        self.extend_btn.set_disabled(False)
        self.status_var.set("⏹ 已取消生成 · 可以重新开始")

    def _on_cancel(self, gen_id: int) -> None:
        """Worker 线程检测到取消后的回调——仅在仍是最新生成时才做 UI 清理。"""
        if gen_id != self._generation_id:
            return  # 已被更新的生成覆盖，忽略
        self.progress.stop()
        self.progress.pack_forget()
        self._cancel_btn.pack_forget()
        self.convert_btn.set_disabled(False)
        self.extend_btn.set_disabled(False)
        self.status_var.set("⏹ 已取消生成 · 可以重新开始")

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


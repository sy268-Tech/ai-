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


APP_TITLE = "Novel2Script AI · 小说转剧本（LangChain + LangGraph）"

EXAMPLE_TEXT = """第一章 旧站台
夜色落下时，林夏来到废弃的火车站。站台上全是雾，远处的灯像被水泡过一样模糊。

林夏说：“是谁让我来这里？”

一阵风吹过，候车厅的铁门发出刺耳的响声。她握紧手机，屏幕上只有一条陌生短信：午夜十二点，旧站台见。

第二章 匿名信
第二天上午，林夏回到办公室。桌上多了一封没有署名的信，信纸边缘被雨水泡皱。

顾言问：“你脸色怎么这么差？”

林夏没有回答。她打开信，里面只有一张旧照片，照片背面写着：别相信你父亲。

第三章 夜访
深夜，林夏按照照片上的地址来到一条狭窄的巷子。巷子尽头有一间亮着灯的旧屋。

门内传来老人咳嗽的声音。林夏刚要敲门，屋里的灯忽然灭了。

顾言低声说：“我们可能被人跟踪了。”
"""


class Novel2ScriptApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1280x820")

        self.config = LLMConfig.from_env()
        self.last_screenplay: dict | None = None

        self.title_var = tk.StringVar(value="雾城来信")
        self.author_var = tk.StringVar(value="示例作者")
        self.format_var = tk.StringVar(value="web_series")
        self.use_llm_var = tk.BooleanVar(value=self.config.is_configured)
        self.status_var = tk.StringVar()

        self._build_ui()
        self._refresh_engine_hint()

    # ── UI 构建 ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill=tk.X)

        tk.Label(top, text="剧本标题").grid(row=0, column=0, sticky="w")
        tk.Entry(top, textvariable=self.title_var, width=20).grid(row=0, column=1, padx=6)

        tk.Label(top, text="作者").grid(row=0, column=2, sticky="w")
        tk.Entry(top, textvariable=self.author_var, width=14).grid(row=0, column=3, padx=6)

        tk.Label(top, text="格式").grid(row=0, column=4, sticky="w")
        tk.OptionMenu(
            top, self.format_var,
            "film", "web_series", "short_drama", "animation",
            "audio_drama", "stage_play", "unknown",
        ).grid(row=0, column=5, padx=6)

        tk.Checkbutton(
            top, text="使用大模型", variable=self.use_llm_var,
            command=self._refresh_engine_hint,
        ).grid(row=0, column=6, padx=6)

        tk.Button(top, text="载入示例", command=self.load_example).grid(row=0, column=7, padx=3)
        tk.Button(top, text="打开 TXT", command=self.open_text_file).grid(row=0, column=8, padx=3)
        self.convert_btn = tk.Button(top, text="生成剧本", command=self.convert)
        self.convert_btn.grid(row=0, column=9, padx=3)
        tk.Button(top, text="保存 YAML", command=self.save_yaml).grid(row=0, column=10, padx=3)
        tk.Button(top, text="保存剧本文本", command=self.save_readable).grid(row=0, column=11, padx=3)

        # 引擎状态提示
        self.engine_label = tk.Label(top, text="", fg="#444", anchor="w")
        self.engine_label.grid(row=1, column=0, columnspan=12, sticky="w", pady=(6, 0))

        body = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        left = tk.Frame(body)
        tk.Label(left, text="小说文本输入（至少 3 章，建议用「第一章/第二章…」分隔）").pack(anchor="w")
        self.input_text = scrolledtext.ScrolledText(left, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True)
        self.input_text.insert("1.0", EXAMPLE_TEXT)
        body.add(left, minsize=480)

        right = tk.Frame(body)
        tk.Label(right, text="转换结果").pack(anchor="w")
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        self.readable_text = scrolledtext.ScrolledText(self.tabs, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.yaml_text = scrolledtext.ScrolledText(self.tabs, wrap=tk.NONE, font=("Consolas", 10))
        self.tabs.add(self.readable_text, text="可读剧本（角色/对话/环境）")
        self.tabs.add(self.yaml_text, text="结构化 YAML")
        body.add(right, minsize=560)

        bottom = tk.Frame(self.root, padx=10, pady=6)
        bottom.pack(fill=tk.X)
        tk.Label(bottom, textvariable=self.status_var, anchor="w").pack(fill=tk.X)
        self.status_var.set("请粘贴至少 3 章小说文本，然后点击「生成剧本」。")

    # ── 行为 ────────────────────────────────────────────────

    def _refresh_engine_hint(self) -> None:
        if self.use_llm_var.get():
            if self.config.is_configured:
                self.engine_label.config(
                    text=f"引擎：大模型 LangChain+LangGraph（{self.config.model}） · 已读取 .env",
                    fg="#0a7d28",
                )
            else:
                self.engine_label.config(
                    text="未检测到 API Key：请复制 .env.example 为 .env 并填入 LLM_API_KEY；当前将自动回退规则引擎。",
                    fg="#b25b00",
                )
        else:
            self.engine_label.config(text="引擎：内置规则引擎（离线，无需联网）", fg="#444")

    def load_example(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", EXAMPLE_TEXT)
        self.status_var.set("已载入示例文本。")

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
        self.status_var.set(f"已打开：{path}")

    def convert(self) -> None:
        raw_text = self.input_text.get("1.0", tk.END).strip()
        title = self.title_var.get().strip() or "未命名剧本"
        author = self.author_var.get().strip()
        fmt = self.format_var.get().strip() or "web_series"
        prefer_llm = self.use_llm_var.get()

        # 大模型调用可能耗时，放到后台线程，避免界面卡死
        self.convert_btn.config(state=tk.DISABLED)
        engine = "大模型" if (prefer_llm and self.config.is_configured) else "规则引擎"
        self.status_var.set(f"正在用{engine}生成剧本，请稍候…")

        def worker() -> None:
            try:
                novel = build_novel_from_text(raw_text, title=title, author=author, fmt=fmt)
                options = ConvertOptions(default_format=fmt)
                screenplay, used_llm = convert_novel(novel, options=options, prefer_llm=prefer_llm)
                yaml_out = dump_yaml(screenplay)
                readable = render_readable_script(screenplay)
                self.root.after(0, self._on_success, screenplay, yaml_out, readable, used_llm)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, self._on_error, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, screenplay: dict, yaml_out: str, readable: str, used_llm: bool) -> None:
        self.last_screenplay = screenplay
        self.readable_text.delete("1.0", tk.END)
        self.readable_text.insert("1.0", readable)
        self.yaml_text.delete("1.0", tk.END)
        self.yaml_text.insert("1.0", yaml_out)
        self.tabs.select(0)
        self.convert_btn.config(state=tk.NORMAL)

        scene_count = len(screenplay.get("script", {}).get("scenes", []))
        engine = "大模型 (LangChain+LangGraph)" if used_llm else "规则引擎"
        note = "" if used_llm or not self.use_llm_var.get() else "（大模型不可用，已回退）"
        self.status_var.set(f"生成成功：{engine}{note}，共 {scene_count} 个场景。可保存 YAML 或剧本文本。")

    def _on_error(self, exc: Exception) -> None:
        self.convert_btn.config(state=tk.NORMAL)
        messagebox.showerror("生成失败", str(exc))
        self.status_var.set(f"生成失败：{exc}")

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
        self.status_var.set(f"已保存 YAML：{path}")

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
        self.status_var.set(f"已保存剧本文本：{path}")


def main() -> None:
    window = tk.Tk()
    Novel2ScriptApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()




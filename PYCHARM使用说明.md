# PyCharm 直接运行说明

## 运行步骤

1. 用 PyCharm 打开 `novel2script_ai` 文件夹。
2. （可选）复制 `.env.example` 为 `.env`，填入你的大模型 API Key。
3. 找到根目录的 `main.py`，右键 → **Run 'main'**。
4. 程序弹出图形界面。

## 使用方式

1. 在左侧输入框粘贴或打开至少 3 章小说文本（用「第一章 / 第二章 / 第三章」标题分隔）。
2. 点击「生成剧本」按钮。
3. 右侧「可读剧本」tab 展示标注了【角色】【对话】【环境】的直观视图。
4. 切到「结构化 YAML」tab 查看机器可读格式。
5. 保存为 `.yaml`（结构化）或 `.txt`（可读）。

## 大模型配置

勾选「使用大模型」前，需在 `.env` 文件中填入 API Key：

```
LLM_API_KEY=sk-your-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

未配置时程序使用内置规则引擎，离线即可运行。

## 是否需要安装依赖？

如果只运行 `main.py` 且不使用大模型，标准库的 tkinter 即可。
如需大模型功能，建议安装完整依赖：

```bash
pip install -e ".[dev]"
```

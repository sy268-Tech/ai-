# Novel2Script AI

**AI 小说转剧本工具** —— 将 3 个章节以上的小说文本自动转换为结构化剧本（YAML 格式），
标注角色、对话和环境，让作者可以快速获得可编辑、可进一步打磨的剧本初稿。

## 核心特性

| 功能 | 说明 |
|------|------|
| 大模型驱动 | 基于 **LangChain + LangGraph** 框架，支持 OpenAI / DeepSeek / 通义千问 / Kimi / 智谱等兼容 API |
| 结构化输出 | 所有大模型返回都通过 Pydantic 模型约束（`with_structured_output`），保证结果规范 |
| 有向状态图 | 转换流水线建模为 LangGraph StateGraph：角色识别 → 地点识别 → 场景切分 → 节拍抽取 |
| 离线可用 | 未配置 API Key 时自动回退内置规则引擎，保证零依赖也能产出初稿 |
| 多格式输出 | 同时生成 YAML（机器可读）+ 标注【角色】【对话】【环境】的可读剧本文本 |
| Schema 校验 | 输出自动通过 `screenplay.schema.yaml` 校验，保证字段完整、引用一致 |
| 美观界面 | 现代化深色标题栏 + 浅色卡片式布局，圆角按钮、状态指示器、进度条、暗色 YAML 编辑器 |

## 快速开始

### 1. 安装

```bash
cd novel2script_ai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. 配置大模型（可选）

```bash
cp .env.example .env
# 打开 .env，填入你的 API Key：
#   LLM_API_KEY=sk-your-real-key
#   LLM_BASE_URL=https://api.deepseek.com/v1   (或 OpenAI/通义千问 等)
#   LLM_MODEL=deepseek-chat
```

### 3. 运行

**方式 A：图形界面（推荐，PyCharm 右键 Run）**

```bash
python main.py
```

界面功能：
- 粘贴 / 打开至少 3 章小说文本
- 点击「✦ 生成剧本」
- 左侧 Tab 查看标注了【角色】【对话】【环境】的可读剧本
- 右侧 Tab 查看暗色主题的结构化 YAML 输出
- 支持保存为 `.yaml` 或 `.txt`

**方式 B：命令行**

```bash
# 纯文本小说 → 剧本
novel2script convert novel.txt --text --title "雾城来信" --author "张三" -o output.yaml --readable

# 结构化 YAML 小说 → 剧本
novel2script convert examples/novel_input.yaml -o output.yaml

# 强制使用规则引擎（不调用大模型）
novel2script convert novel.txt --text --no-llm -o output.yaml

# 校验输出
novel2script validate output.yaml

# 查看当前大模型配置
novel2script config
```

## 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    main.py (GUI)                     │
│                    cli.py (CLI)                      │
└───────────────────────┬─────────────────────────────┘
                        │
                ┌───────▼───────┐
                │  service.py   │  统一入口（选择生成器、组装结果）
                └───────┬───────┘
         ┌──────────────┼──────────────┐
         ▼                             ▼
┌────────────────┐           ┌───────────────────────────┐
│ pipeline.py    │           │ adapters.py               │
│ RuleBasedGen   │           │ LangGraphScriptGenerator  │
│ (离线规则引擎) │           │ (LangChain+LangGraph)     │
└────────────────┘           └───────────┬───────────────┘
                                         │
                             ┌───────────▼───────────────┐
                             │  LangGraph StateGraph      │
                             │  ┌─────────────────────┐  │
                             │  │ extract_characters   │  │
                             │  │ extract_locations    │  │
                             │  │ segment_scenes       │  │
                             │  │ extract_beats        │  │
                             │  └─────────────────────┘  │
                             │  Pydantic structured out   │
                             └───────────────────────────┘
```

## 项目结构

```
novel2script_ai/
├── main.py                 # 图形界面入口（现代化 UI）
├── .env.example            # 环境变量模板（复制为 .env 填入 API Key）
├── pyproject.toml          # 项目配置与依赖
├── schemas/
│   └── screenplay.schema.yaml   # YAML Schema 定义
├── docs/
│   └── screenplay_yaml_schema_design.md  # Schema 设计文档
├── examples/
│   └── novel_input.yaml    # 示例小说输入
├── src/novel2script/
│   ├── __init__.py         # 包入口，导出公开 API
│   ├── config.py           # .env 加载 + LLMConfig 数据类
│   ├── models.py           # 数据模型（NovelInput / ConvertOptions）
│   ├── llm_schemas.py      # 大模型结构化输出 Pydantic 模型
│   ├── adapters.py         # 生成器接口 + LangGraph 大模型生成器
│   ├── pipeline.py         # 规则引擎生成器（离线 fallback）
│   ├── service.py          # 高层服务（选生成器、调流水线）
│   ├── renderer.py         # 标注角色/对话/环境的可读剧本渲染器
│   ├── validators.py       # Schema + 交叉引用校验
│   ├── utils.py            # 工具函数（分章、分段、时间推断…）
│   ├── yaml_io.py          # YAML 读写
│   └── cli.py              # 命令行入口
└── tests/
    └── test_pipeline.py    # 测试用例
```

## LangChain + LangGraph 使用说明

本项目使用的核心框架：

- **LangChain**：封装大模型调用（`ChatOpenAI`）、Prompt 模板（`ChatPromptTemplate`）、
  结构化输出（`with_structured_output` + Pydantic schema）
- **LangGraph**：把小说转剧本流水线建模为有向状态图（`StateGraph`），
  每个节点是一次大模型调用，节点之间通过共享 State 传递中间结果

```python
# 伪代码示意
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

graph = StateGraph(GraphState)
graph.add_node("extract_characters", characters_node)
graph.add_node("extract_locations", locations_node)
graph.add_node("segment_scenes", scenes_node)
graph.add_node("extract_beats", beats_node)
graph.add_edge(START, "extract_characters")
graph.add_edge("extract_characters", "extract_locations")
graph.add_edge("extract_locations", "segment_scenes")
graph.add_edge("segment_scenes", "extract_beats")
graph.add_edge("extract_beats", END)

compiled = graph.compile()
result = compiled.invoke({})
```

## 依赖说明

| 依赖库 | 用途 |
|--------|------|
| LangChain | 大模型调用封装、Prompt 模板、结构化输出 |
| LangGraph | 有向状态图流程编排 |
| langchain-openai | OpenAI 兼容 API 适配器 |
| Pydantic | 大模型输出结构约束 |
| PyYAML | YAML 读写 |
| jsonschema | Schema 校验 |
| python-dotenv | .env 环境变量加载 |

## 设计说明

详见 [docs/screenplay_yaml_schema_design.md](docs/screenplay_yaml_schema_design.md)。

## 注意事项

- 本项目生成的是"可编辑初稿"，不是最终专业剧本。
- 作者应重点检查：人物动机、对白口吻、场景节奏、原文是否遗漏。
- 大模型生成质量取决于所选模型和输入文本质量。
- 未配置 API Key 时自动使用规则引擎，保证离线可用。

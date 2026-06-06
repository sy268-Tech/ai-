# Demo 视频录制指南

## 视频要求

根据题目要求，Demo 视频需要：
- 用声音完整讲解
- 展示作品主要功能和效果
- 覆盖核心模块
- 上传至 B站/云盘等可访问平台
- 链接放到 README 中

## 推荐录制工具

- **OBS Studio**（免费）：https://obsproject.com/
- **Windows 自带录屏**：Win + G 打开 Game Bar 录制
- **Bandicam** / **ScreenToGif**

## 讲解大纲（建议 3~5 分钟）

### 开场（30s）
- 自我介绍 + 项目名称
- "这是一个 AI 小说转剧本工具，基于 LangChain + LangGraph 框架"

### 功能演示 - GUI（2min）
1. 打开 PyCharm，运行 `main.py`
2. 展示界面布局：左侧输入区 / 右侧输出区
3. 点击「载入示例」加载 3 章小说
4. 勾选「启用大模型」，观察状态指示器变绿
5. 点击「✦ 生成剧本」，观察进度条
6. 展示「可读剧本」Tab —— 标注了【角色】【对话】【环境】
7. 切换到「结构化 YAML」Tab —— 暗色主题代码视图
8. 演示保存功能

### 功能演示 - CLI（30s）
```bash
novel2script convert examples/novel_input.yaml -o output.yaml --readable
novel2script validate output.yaml
novel2script config
```

### 技术讲解（2~3min）

#### 1. 整体架构：双生成器策略
打开 `src/novel2script/adapters.py`，先讲解最顶层的设计：

- **抽象接口 `ScriptGenerator`**：定义了两个核心方法 `generate()`（从小说生成剧本）和 `extend()`（续写已有剧本），所有生成器都实现这个接口
- **大模型版 `LangGraphScriptGenerator`**：基于 LangChain + LangGraph 的四节点流水线
- **规则版 `RuleBasedGenerator`**：零依赖的正则+关键词引擎
- GUI/CLI 中自动切换：检测 `.env` 中的 `LLM_API_KEY` 是否已配置 → 有 Key 用大模型版，无 Key 自动回退规则版

#### 2. LangGraph 四节点流水线详解
继续在 `adapters.py`，定位到 `_build_graph()` 方法（约第 215 行）：

- **整体拓扑**：`START → extract_characters → extract_locations → segment_scenes → extract_beats → END`
- **状态管理**：使用 `_GraphState(TypedDict)` 在节点间流转共享数据——`characters`（OrderedDict）、`locations`（OrderedDict）、`scenes`（list[dict]），每个节点的 `return` 会被 LangGraph 自动 `merge` 进状态
- **节点1 `extract_characters`**：`_node_characters()` 方法，将小说章节拼接后发 Prompt 给大模型，用 `LLMCharacterList` 约束返回格式，解析出角色名、定位（protagonist/antagonist/supporting 等）、性别、年龄、目标（goal）、冲突（conflict），存入 OrderedDict
- **节点2 `extract_locations`**：`_node_locations()` 方法，同样发 Prompt 让大模型识别场景地点（如"旧火车站""林夏的办公室"），附带类型（interior/exterior/mixed）、描述和氛围（atmosphere）
- **节点3 `segment_scenes`**：`_node_scenes()` 方法，把小说段落按叙事节奏切分成场景。Prompt 中要求大模型在时间/地点变化或视角切换时切分，不要机械按段数切。每个场景标出段落区间 `paragraph_ranges`、heading（时间/内外景/氛围）、dramatic_function、在场角色。失败时回退到按 `max_paragraphs_per_scene` 等分
- **节点4 `extract_beats`**：`_node_beats()` 方法，对每个场景的文字进行粒度为"节拍"的改写。5 种 beat 类型——`action`（动作）、`dialogue`（对白，必须标 speaker）、`narration`（旁白/内心独白）、`sound`（音效）、`visual`（纯画面）。失败时兜底为一个 action beat

#### 3. Pydantic 结构化输出机制
打开 `src/novel2script/llm_schemas.py`：

- **为什么用 Pydantic**：大模型自由文本输出不可靠（格式不稳定、嵌套 JSON 难解析）。Pydantic BaseModel 通过 LangChain 的 `with_structured_output()` 直接约束大模型按固定字段输出 JSON，消除解析脆弱性
- **核心模型（6 组）**：
  - `LLMCharacter` → `LLMCharacterList`：角色，含 name/role/gender/age/description/goal/conflict
  - `LLMLocation` → `LLMLocationList`：地点，含 name/type/description/atmosphere
  - `LLMScene` → `LLMSceneList`：场景，含 location/time_of_day/interior_exterior/atmosphere/summary/dramatic_function/characters_present/paragraph_ranges
  - `LLMBeat` → `LLMBeatList`：节拍，含 type/speaker/text
  - `LLMChapterSegment` → `LLMChapterSegmentList`：章节边界（用于智能切分）
- **兼容性设计**：`with_structured_output(schema, method="function_calling")` 使用 function_calling 而非 response_format: json_schema，确保对 DeepSeek 等不原生支持 JSON Schema 约束的 API 兼容
- **Field description 的重要性**：description 不是注释——它会被 LangChain 原样注入 tool/function 的 JSON Schema，大模型据此生成字段内容。例如 `name: str = Field(description="角色的真实姓名，只要名字本身，不含'说/问/道'等动词")` 这个约束直接避免了大模型把"林夏说"当成角色名

#### 4. 输出 Schema 设计
打开 `schemas/screenplay.schema.yaml`：

- **层级结构**：`screenplay → script → {characters[], locations[], scenes[]}`
- **角色 (characters)**：id（下划线式如 `char_a1b2c3d4`）、name、role（protagonist/antagonist/supporting/mentor/love_interest 等）、age/gender、description、goal、conflict、relationships[]、source_chapters[]
- **地点 (locations)**：id、name、type（interior/exterior/mixed/unknown）、description、atmosphere、source_chapters
- **场景 (scenes)**：id（`scene_001`）、scene_number、heading（含 location_id/time_of_day/interior_exterior/atmosphere）、dramatic_function、summary、characters[]、beats[]、transition（CUT_TO/DISSOLVE_TO/FADE_IN 等）
- **节拍 (beats)**：type（action/dialogue/narration/sound/visual）、text、character_id、parenthetical、emotion、camera、source_text_ref
- **约束**：JSON Schema `required` 字段强制关键字段完整性；`enum` 限制枚举字段避免歧义；`pattern` 约束 id 格式；`minItems` 保证数组非空

#### 5. 规则引擎回退机制
打开 `src/novel2script/pipeline.py`，讲解 `RuleBasedGenerator`：

- **角色识别**：用正则匹配"名字+说话动词+冒号"模式（如 `林夏说：`、`顾言低声说：`）。`SPEAKER_PATTERNS` 定义了 3 级置信度——名+动+冒号（高）、名+动无冒号（高，用受限动词表）、名+裸冒号（低）。`_is_probable_name()` 维护了详细的黑名单（"他说""门外""什么"等）过滤误匹配
- **地点识别**：`COMMON_LOCATION_HINTS` 关键词匹配（火车站、办公室、咖啡馆等 24 个常见地点），根据上下文推断 interior/exterior
- **节拍生成**：`_paragraphs_to_beats()` 逐段分析——先检查是否对白（引号/冒号模式）→ 再检查是否内心独白（"想到""觉得""意识到"）→ 再检查音效（"响起""爆炸声"等）→ 默认归类为 action

#### 6. 配置管理与 API 兼容
打开 `src/novel2script/config.py`：

- `LLMConfig` dataclass 统一管理：api_key、base_url、model、temperature、max_tokens、max_chars_per_chapter
- `from_env()` 自动加载 `.env` 文件，兼容 `LLM_API_KEY` / `OPENAI_API_KEY` 双变量名
- `is_configured` 属性检测是否填写了真实 Key（排除占位符值 like `sk-your-api-key-here`）
- 默认 `base_url=https://api.openai.com/v1`，意味着兼容 OpenAI / DeepSeek / 硅基流动等所有 OpenAI 兼容 API

### 收尾（30s）
- 总结技术栈：LangChain + LangGraph + Pydantic + tkinter
- 说明项目可扩展性

## 录制后

1. 上传到 B站 或百度网盘
2. 将链接添加到 README.md 的顶部

## 快速录制命令行 Demo

如果只想快速录制终端效果，可以运行：

```bash
python demo/run_demo.py
```

这会自动演示所有核心功能的非交互版本。

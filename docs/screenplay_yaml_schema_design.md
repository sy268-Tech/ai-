# 剧本 YAML Schema 设计文档

## 1. 文档目的

本文档定义一套用于“小说自动改编剧本”的 YAML Schema。该 Schema 的目标是让 AI 能够将 3 个章节以上的小说文本转换为结构化、可编辑、可校验的剧本初稿。

该 Schema 主要服务于以下场景：

1. 小说作者快速获得剧本化初稿。
2. 编剧基于结构化内容继续打磨。
3. 前端编辑器按场景、人物、对白进行可视化编辑。
4. 系统通过 Schema 校验 AI 输出质量。
5. 后续导出为分场大纲、标准剧本、拍摄计划或字幕格式。

## 2. 设计原则

### 2.1 可编辑优先

剧本初稿不是最终稿，因此 Schema 不追求一次性生成完美剧本，而是强调可编辑性。人物、地点、场景、对白、动作都被拆成独立字段，方便作者局部修改。

### 2.2 可追溯原文

每个场景都保留 `source_chapters` 字段，用于标记该场景来源于小说的哪些章节。这样作者可以快速对照原文，判断 AI 是否误改、漏改或过度改编。

### 2.3 面向视听表达

小说中大量心理描写、背景说明和抽象叙述不适合直接进入剧本。因此 Schema 将内容拆分为：

- 动作 `action`
- 对白 `dialogue`
- 旁白 `narration`
- 声音 `sound`
- 画面 `visual`
- 转场 `transition`

这有助于 AI 把小说语言转换为可拍摄、可表演、可剪辑的剧本语言。

### 2.4 支持多种剧本形态

不同作者可能需要电影、网剧、短剧、动画或有声剧。因此 Schema 使用 `format` 字段标记作品类型，而不是固定为单一影视格式。

### 2.5 保持轻量但可扩展

Schema 保留必要字段，同时允许扩展字段 `notes`、`tags`、`metadata`，便于未来支持预算、镜头、服化道、演员调度等功能。

## 3. 顶层结构

```yaml
schema_version: "1.0"
script:
  title: ""
  format: ""
  language: "zh-CN"
  genre: []
  logline: ""
  synopsis: ""
  source: {}
  metadata: {}
  characters: []
  locations: []
  scenes: []
  notes: []
```

## 4. 核心字段说明

### 4.1 `schema_version`

用于标记当前 YAML 文件使用的 Schema 版本。

设计原因：剧本结构未来可能升级，例如增加镜头、分集、拍摄计划等字段。版本号可以保证旧数据兼容。

### 4.2 `script.title`

剧本标题。

设计原因：剧本标题可能不同于小说标题，因此单独设置。

### 4.3 `script.format`

可选值：

```yaml
film
web_series
short_drama
animation
audio_drama
stage_play
unknown
```

设计原因：不同媒介对场景长度、对白密度和叙事节奏要求不同。短剧更强调高频反转，电影更强调三幕结构，有声剧更依赖对白和声音设计。

### 4.4 `script.language`

推荐使用 BCP 47 语言标签，例如 `zh-CN`。

设计原因：便于多语言生成、翻译和本地化。

### 4.5 `script.source`

```yaml
source:
  novel_title: "小说标题"
  author: "原作者"
  adapted_chapters:
    - 1
    - 2
    - 3
  source_note: "根据前三章生成初稿"
```

设计原因：小说改编往往需要多轮处理。保留来源信息可以帮助作者知道当前剧本覆盖了哪些章节。

## 5. 人物表 `characters`

```yaml
characters:
  - id: "char_lin_xia"
    name: "林夏"
    role: "protagonist"
    age: "26"
    gender: "female"
    description: "年轻记者，敏锐但固执。"
    goal: "查明匿名来信背后的真相。"
    conflict: "她越接近真相，越发现案件与自己家族有关。"
    relationships:
      - character_id: "char_gu_yan"
        relation: "former_colleague"
    source_chapters:
      - 1
      - 2
```

设计原因：

1. 人物表独立于场景，有助于保持人物称谓、动机和关系的一致性。
2. 使用 `id` 而不是直接用姓名引用人物，可以避免重名、改名、别名造成混乱。
3. `goal` 和 `conflict` 字段帮助 AI 和作者关注戏剧驱动力，而不只是人物介绍。

## 6. 地点表 `locations`

```yaml
locations:
  - id: "loc_old_station"
    name: "旧火车站"
    type: "exterior"
    description: "废弃多年，夜晚雾气浓重。"
    atmosphere: "阴冷、神秘、不安"
    source_chapters:
      - 1
```

设计原因：

1. 地点表有利于后续生成拍摄计划、场景调度和美术设计。
2. 地点独立建模可以减少同一地点被重复命名的问题。
3. `atmosphere` 可以保留小说中的气氛信息，辅助视听化改写。

## 7. 场景列表 `scenes`

```yaml
scenes:
  - id: "scene_001"
    scene_number: 1
    source_chapters:
      - 1
    heading:
      location_id: "loc_old_station"
      time_of_day: "night"
      interior_exterior: "EXT"
    dramatic_function: "引出悬念"
    summary: "林夏在旧火车站收到一封没有署名的信。"
    characters:
      - "char_lin_xia"
    beats:
      - type: "action"
        text: "浓雾吞没站台。林夏撑着伞走进空无一人的候车区。"
      - type: "dialogue"
        character_id: "char_lin_xia"
        text: "谁约我来这里？"
      - type: "sound"
        text: "远处传来老式列车的汽笛声。"
    transition: "CUT_TO"
```

设计原因：

1. 剧本的基本编辑单位是“场景”。
2. 将小说章节转为多个场景，可以让作者按场景进行增删、重排和重写。
3. `source_chapters` 让场景与原文保持可追溯关系。
4. `dramatic_function` 让作者判断该场景存在的戏剧目的，避免流水账式改编。

## 8. 场景头 `heading`

```yaml
heading:
  location_id: "loc_old_station"
  time_of_day: "night"
  interior_exterior: "EXT"
```

设计原因：

1. 标准剧本通常需要标明内外景、地点和时间。
2. 这些字段也方便后续生成拍摄计划。
3. `location_id` 引用地点表，而不是重复写地点名称，可以避免不一致。

## 9. 内容单元 `beats`

```yaml
beats:
  - type: "action"
    text: "林夏停下脚步，望向候车厅深处。"

  - type: "dialogue"
    character_id: "char_lin_xia"
    text: "有人吗？"

  - type: "narration"
    text: "她不知道，这封信会改变她的一生。"
```

设计原因：

1. 使用 beats 可以将一个场景拆成更小的可编辑单元。
2. 这比整段剧本纯文本更适合 AI 修改和前端交互。
3. 不同 beat 类型可以服务不同媒介，例如有声剧更关注 `dialogue` 和 `sound`，影视剧更关注 `action` 和 `visual`。

## 10. 转场 `transition`

可选值：

```yaml
CUT_TO
FADE_IN
FADE_OUT
DISSOLVE_TO
MATCH_CUT
SMASH_CUT
CONTINUOUS
NONE
```

设计原因：转场不是每个场景都必须有，但保留该字段可以帮助作者进一步影视化处理。

## 11. 关键校验规则

### 11.1 章节数量校验

`source.adapted_chapters` 至少包含 3 个章节编号。

设计原因：需求要求工具能处理 3 个章节以上小说文本。少于 3 章时，故事结构、人物动机和冲突发展可能不足以生成稳定剧本初稿。

### 11.2 人物引用校验

所有 `dialogue.character_id` 应该能在 `characters.id` 中找到。

设计原因：避免对白角色不存在、角色名称不一致、同一人物多种称谓混乱。

### 11.3 地点引用校验

所有 `heading.location_id` 应该能在 `locations.id` 中找到。

设计原因：保证场景地点可统一管理，也便于后续生成拍摄计划。

### 11.4 场景编号校验

`scene_number` 应按正整数递增。

设计原因：方便作者阅读、重排和引用场景。

### 11.5 对白条件校验

当 `beat.type` 为 `dialogue` 时，应包含 `character_id`。

设计原因：对白必须归属于具体人物，否则无法编辑、排练或导出标准剧本。

## 12. 设计总结

该 YAML Schema 的核心设计目标是：让 AI 输出不只是“像剧本的文本”，而是一个可以被软件读取、校验、编辑和二次生成的结构化剧本对象。

它通过以下方式降低小说改编门槛：

1. 自动拆分人物、地点、场景和对白。
2. 保留原章节来源，方便作者回溯。
3. 使用统一字段减少格式混乱。
4. 允许作者按场景局部修改。
5. 便于后续导出为标准剧本、分场大纲或拍摄资料。

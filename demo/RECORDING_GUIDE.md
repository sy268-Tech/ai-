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

### 技术讲解（1~2min）
1. 打开 `src/novel2script/adapters.py`，讲解 LangGraph StateGraph 四节点流水线
2. 打开 `src/novel2script/llm_schemas.py`，讲解 Pydantic 结构化输出
3. 打开 `schemas/screenplay.schema.yaml`，讲解 Schema 设计
4. 说明离线回退机制：未配置 API Key → 自动使用规则引擎

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

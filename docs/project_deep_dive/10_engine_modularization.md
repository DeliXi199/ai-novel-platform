# 10_引擎模块化拆分说明

这次重构继续把 `openai_story_engine.py` 从“巨型杂物间”往“总装层 + 兼容层”推进。

## 当前拆分格局

- `openai_story_engine.py`
  - 继续保留正文生成、兼容 shim、少量历史导出
  - 不再承载 bootstrap / outline / diagnosis 的正式实现
- `openai_story_engine_selection.py`
  - selection 领域边界、payload、helper、正式入口
- `openai_story_engine_review.py`
  - stage/relation review 正式实现
- `openai_story_engine_arc.py`
  - arc casting layout review 正式实现
- `openai_story_engine_summary.py`
  - 摘要 / 标题精修正式实现
- `openai_story_engine_bootstrap.py`
  - 诊断、策略卡、总纲、弧线大纲、指令解析、flow template 选择与归一化

## 这一轮从主引擎搬出的内容

- `StoryAct`
- `GlobalOutlinePayload`
- `ArcOutlinePayload`
- `ParsedInstructionPayload`
- `generate_story_engine_strategy_bundle(...)`
- `generate_story_engine_diagnosis(...)`
- `generate_story_strategy_card(...)`
- `generate_global_outline(...)`
- `generate_arc_outline(...)`
- `parse_instruction_with_openai(...)`
- 以及与之配套的 flow template / 归一化 helper

## 设计意图

1. 主引擎更像总装层，而不是自己亲自负责所有子流程。
2. bootstrap / outline 和正文生成解耦，后续继续改建书链时不容易误伤章节生成。
3. 保留 shim，避免旧调用点和测试 monkeypatch 习惯直接炸掉。

## 后续建议

- 继续把 `openai_story_engine.py` 剩余的兼容 shim 做成更明确的“兼容出口区”。
- 为 `openai_story_engine_bootstrap.py` 增加更细的单测覆盖，尤其是：
  - flow template 选择
  - 大纲归一化
  - 章节类型推断
  - 指令解析

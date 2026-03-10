# Architecture (Layered Outline Edition)

## Goal

把长篇连载生成拆成稳定的多层流程，避免“直接写正文”导致的失忆、跑偏和重复模板。

核心链路：

1. Story Bible
2. Global Outline
3. Active Arc / Pending Arc
4. Chapter Draft
5. Chapter Summary

## Build flow

### On novel creation

创建小说时只做规划，不预生成正文：

- Build story bible
- Generate global outline
- Generate first arc outline (default 5 chapters)
- Save `outline_state`
- `current_chapter_no = 0`

### On next chapter request

生成下一章时按需推进：

- Lock the novel row to prevent concurrent writes
- Promote `pending_arc` if current arc has already ended
- Read the stored chapter plan
- If the plan is missing, generate a new arc just-in-time
- Build a light chapter context payload
- Generate chapter draft
- Validate chapter quality
- Extend / retry when draft is too short or ends abruptly
- Generate chapter summary
- Persist chapter + summary

### Batch generation

批量生成只是循环调用单章流程：

- 每章独立校验
- 某一章最终失败时立即停止
- 已成功入库的前面章节会保留
- SSE 接口实时推送进度事件

## Concurrency and rate protection

### Novel-level serialization

同一本书同一时间只允许一个章节生成任务：

- Database row lock with `FOR UPDATE NOWAIT`
- Conflicting request returns `CHAPTER_ALREADY_GENERATING`

### LLM call throttling

模型调用节流现在按 **provider + base_url + model** 维度隔离，而不是整个 Python 进程共享一个全局时间戳。

这意味着：

- 同一模型链路仍会自动留间隔
- 不同 provider / model 之间不会被同一个全局节流器硬串行化

## Summary strategy

`CHAPTER_SUMMARY_MODE` supports:

- `llm`: always use model summary, fail loudly on error
- `heuristic`: never call the model, use local summary extraction only
- `auto`: try model summary first, then fall back to heuristic if summary generation fails

## Service layout

为了减少超大文件，LLM 与章节上下文逻辑已拆分：

- `openai_story_engine.py`: high-level generation orchestration
- `llm_runtime.py`: provider config, client init, throttling, tracing, API call wrapper
- `llm_types.py`: shared Pydantic payload models
- `chapter_context.py`: chapter context serialization and prompt budget trimming
- `instruction_parser.py`: reader-instruction heuristic parser + merge logic

## Failure policy

项目不再使用静默 fallback 生成正文或大纲。

这些情况会直接抛出结构化错误：

- provider 未配置
- 鉴权失败
- 超时 / 限流 / 网络错误
- 模型 JSON 格式错误
- 章节质量不达标

失败章节不会入库。

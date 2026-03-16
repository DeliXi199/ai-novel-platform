## 2026-03-14 - Task management hardening

- Added async task retry / cancel / cleanup APIs, plus task-history payloads in workspace responses.
- Async task records now support retry lineage (`retry_of_task_id`) and cooperative cancellation markers (`cancel_requested_at`, `cancelled_at`).
- Batch generation can stop at safe boundaries and keep partial-result metadata instead of collapsing into a generic failure.
- Frontend now shows a task center with recent tasks, retry and cancel actions, and one-click cleanup for older terminal records.

## 2026-03-13 - Chapter repair pipeline split

- Added `chapter_repair_pipeline.py` to route chapter-quality failures into dedicated repair strategies instead of mixing all fixes inside one retry block.
- `CHAPTER_ENDING_INCOMPLETE` now uses a dedicated `llm_append_tail` repair path.
- `CHAPTER_TOO_SHORT` now routes to `regenerate_expanded_draft`, keeping length repair separate from tail repair.
- Weak chapter endings (`CHAPTER_PROGRESS_TOO_WEAK` with `ending_pattern`) now route to `regenerate_stronger_ending`, so "尾巴断掉" and "最后一段太虚" are no longer treated as the same fix.
- Added repair trace metadata and regression tests for tail repair and weak-ending retry routing.

# CHANGELOG

这个文件用于替代开发过程中分散在仓库根目录的多份补丁/优化说明，作为 GitHub 展示版的统一变更记录。

## 主要迭代方向

- 前后端同源工作台接入与加载稳定性优化
- 章节生成链路拆分、重试、超时与质量反馈优化
- 故事状态管理与硬事实守卫分层重构
- 数据库初始化、迁移基线与 CI 回归测试补齐
- DeepSeek / Groq / OpenAI 兼容接入修复

## 已合并的历史说明文件

- `AGENCY_MODE_ENGINE_NOTES.md`：Agency Mode Engine 更新说明
- `AGENCY_PATCH_NOTES.md`：主角主动性优化说明
- `FINAL_REVIEW_NOTES_20260313.md`：FINAL REVIEW NOTES — 2026-03-13
- `LIVE_REFRESH_STALL_FIX_NOTES.md`：Live Refresh Stall Fix Notes
- `OPTIMIZATION_NOTES_20260313.md`：优化说明（2026-03-13）
- `OPTIMIZATION_NOTES_20260313_ROUND2.md`：第二轮结构优化说明（2026-03-13）
- `OPTIMIZATION_NOTES_20260313_ROUND3.md`：Optimization Notes — 2026-03-13 Round 3
- `OPTIMIZATION_NOTES_20260313_ROUND4.md`：Optimization Notes — 2026-03-13 Round 4
- `OPTIMIZATION_NOTES_20260313_ROUND5.md`：OPTIMIZATION NOTES · 2026-03-13 · ROUND 5
- `OPTIMIZATION_NOTES_20260313_ROUND6.md`：Optimization Notes — Round 6 (2026-03-13)
- `OPTIMIZATION_NOTES_20260313_ROUND7.md`：2026-03-13 Round 7 隐藏问题修复说明
- `PATCH_NOTES.md`：Patch Notes
- `PROGRESS_RESULT_QUALITY_PATCH_NOTES.md`：Progress Result Quality Patch Notes
- `TIMEOUT_AND_FRONTEND_LOAD_FIX_NOTES.md`：Timeout & Frontend Load Fix Notes
- `TIMEOUT_AND_QUALITY_FEEDBACK_PATCH_NOTES.md`：Timeout & Quality Feedback Patch Notes

这些原始开发说明已从 GitHub 展示版仓库中移除，以减少根目录噪音；如需更细粒度的开发过程记录，建议改为 Git 提交历史或 Release Notes 管理。

# 12. 章节生成阶段模块继续拆分

这一轮把原先 `chapter_generation_stages.py` 里“编排 + 正文起草 + 终稿落库”混在一起的结构继续拆细，目标是让章节生成主链更像清晰的流水线，而不是一个中号杂物间。

## 拆分结果

现在章节生成相关职责分成三层：

- `chapter_generation_stages.py`
  - 保留轻量编排与入口职责
  - 负责准备上下文、串起 draft 与 finalize、处理已存在章节的快速返回

- `chapter_generation_draft.py`
  - 承接正文起草阶段
  - 负责调用 `_attempt_generate_validated_chapter(...)`
  - 负责本地与 AI 的 payoff delivery 复核
  - 负责起草完成后的 runtime snapshot 更新

- `chapter_generation_finalize.py`
  - 承接摘要标题联调、硬事实登记、连续性桥接、持久化与发布后处理
  - 负责 generation report 拼装
  - 负责下一章入口刷新与 story workspace 快照归档

## 这样拆的好处

1. `chapter_generation_stages.py` 重新变薄，回到“阶段编排器”的角色。
2. 正文起草与终稿落库各自可单测、可局部重构，不必每次都动总入口。
3. 后续继续拆 `finalize` 内部时，不会影响起草阶段。
4. 出现生成问题时，更容易判断故障发生在：
   - 准备阶段
   - 正文起草阶段
   - 终稿与发布阶段

## 当前结构建议

如果后面继续优化，优先顺序建议是：

1. 继续把 `chapter_generation_finalize.py` 里的“标题摘要联合后处理”和“发布后 runtime 刷新”拆成更小 helper。
2. 为 draft/finalize 各补一组更窄的定向测试，减少未来重构回归风险。
3. 把 runtime snapshot / generation report 的公共拼装逻辑进一步抽到共享 support 模块。

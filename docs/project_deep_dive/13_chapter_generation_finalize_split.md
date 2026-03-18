# 章节生成终稿阶段拆分（v19）

这次把 `chapter_generation_finalize.py` 从“终稿后处理 + 入库发布 + 下一章入口刷新”的混合模块，拆成了更清楚的两段。

## 新结构

- `chapter_generation_finalize.py`
  - 只保留总入口 `finalize_chapter(...)`
  - 负责串联 prepare → commit

- `chapter_generation_finalize_prepare.py`
  - 负责终稿前置整理
  - 包括：
    - AI 摘要与联合标题精修
    - 标题候选整理与冷却词处理
    - 硬事实校验与登记
    - 章节后长期状态更新
    - continuity bridge 构建
    - scene handoff 提示写回 story workspace
    - 生成时长统计

- `chapter_generation_finalize_commit.py`
  - 负责持久化与发布后刷新
  - 包括：
    - chapter generation meta 组装
    - 入库与 serial delivery 标记
    - generation report 写回
    - intervention applied 标记
    - future planning 自动补齐
    - next entry runtime 刷新
    - workspace snapshot 归档
    - 最终 commit / refresh / success log

## 为什么这次拆分有价值

原来的 `chapter_generation_finalize.py` 同时承担三类职责：

1. AI 后处理与校验
2. 发布与入库
3. 运行时收尾与下一章入口刷新

这会导致：

- 改标题摘要逻辑时，容易碰到发布链
- 改 serial delivery 或 planning 刷新时，容易碰到硬事实校验
- 文件会继续长胖，后续补测试也不方便

拆分后，终稿阶段变成：

- prepare：把“这一章现在最终长什么样”整理出来
- commit：把“这一章如何落库、如何发布、如何刷新系统状态”处理完

## 当前结果

- `chapter_generation_finalize.py`：30 行
- `chapter_generation_finalize_prepare.py`：282 行
- `chapter_generation_finalize_commit.py`：221 行

## 下一步建议

下一步最适合继续拆的是：

1. 把 `chapter_generation_finalize_prepare.py` 里的 continuity bridge / scene handoff 组装，再抽成一个小 helper 模块。
2. 给 finalize prepare / commit 分别补更窄的测试，避免未来继续重构时只能依赖大链路测试。

# Manual Architecture V3

这版主要解决 `arc_outline_generation` 容易因为模型返回超长 JSON 而失败的问题。

## 关键改动

1. `arc outline` 改成紧凑 schema
   - 只强制模型输出短字段：`chapter_no / title / chapter_type / goal / conflict / ending_hook / hook_style / main_scene`
   - `opening_beat / mid_turn / discovery / closing_image / writing_note` 改为后端默认补全

2. `arc outline` 改成分块生成
   - 新增配置 `arc_outline_chunk_size`
   - 一个 7 章窗口不再一次生成完整大 JSON，而是按 2 章一个小块生成，再在后端合并

3. 新增 JSON 修复重试
   - 新增 `json_repair_system_prompt / json_repair_user_prompt`
   - 当模型返回 JSON 非法时，先进入 repair 流程，再决定是否报错

4. 新增 JSON 无效后的重新生成
   - 新增 `json_invalid_regeneration_attempts`
   - repair 失败后，会再重新请求一次原始 JSON 生成

## 新增配置

- `ARC_OUTLINE_CHUNK_SIZE=2`
- `JSON_REPAIR_ATTEMPTS=1`
- `JSON_INVALID_REGENERATION_ATTEMPTS=1`
- `JSON_REPAIR_MAX_OUTPUT_TOKENS=2200`

## 预期效果

- `prepare-next-window` 与 `next-chapter(s)` 在 DeepSeek 下更稳
- `count=2~3` 的批量请求稳定性明显高于旧版
- 若仍失败，会继续按既有策略直接报错，不会偷偷 fallback

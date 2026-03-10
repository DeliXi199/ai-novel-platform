# Architecture (Layered Outline Edition)

## Goal

将小说生成从“直接写一章”改成分层规划：

1. Story Bible
2. Global Outline
3. Arc Outline
4. Chapter Draft
5. Chapter Summary

## Build Flow

### On novel creation

- Build story bible
- Generate global outline
- Generate first arc outline (default 5 chapters)
- Pre-generate first 3 chapters

### On next chapter request

- Read current active arc
- Use stored chapter plan directly
- Generate chapter draft
- Summarize chapter
- If active arc remaining chapters <= threshold, prefetch next arc outline
- Promote pending arc when current arc is exhausted

## Why this is faster

The system no longer pre-generates 10 full chapters on novel creation.
It only pre-generates:

- 1 global outline
- 1 first arc outline
- 3 chapter drafts

This reduces latency while preserving long-range coherence.

## Anti-repetition strategy

- Arc outline gives each chapter distinct scene / goal / conflict
- Draft step includes anti-repetition instruction
- Simple similarity check retries once if chapter is too similar to previous chapter

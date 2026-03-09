from app.core.config import settings
from app.schemas.novel import NovelCreate
from app.services.openai_story_engine import generate_bootstrap_chapter, is_openai_enabled


def build_story_bible(payload: NovelCreate) -> dict:
    genre = payload.genre.strip()
    premise = payload.premise.strip()
    protagonist = payload.protagonist_name.strip()

    return {
        "genre": genre,
        "premise": premise,
        "protagonist": protagonist,
        "narrative_style": payload.style_preferences.get("tone", "连载小说风格"),
        "reader_preferences": payload.style_preferences,
        "core_conflict": f"围绕‘{premise}’展开的主线冲突。",
        "forbidden_rules": payload.style_preferences.get("forbidden", []),
        "target_words_per_chapter": settings.chapter_target_words,
    }


def generate_title(payload: NovelCreate) -> str:
    genre_prefix_map = {
        "都市悬疑": "迷雾档案",
        "校园恋爱": "青春回声",
        "仙侠成长": "问道长歌",
        "西幻冒险": "灰烬王冠",
        "末世生存": "余烬之城",
    }
    prefix = genre_prefix_map.get(payload.genre, "命运序章")
    return f"{prefix}：{payload.protagonist_name}的故事"


def generate_first_chapter(payload: NovelCreate, story_bible: dict) -> tuple[str, str, dict, dict]:
    if is_openai_enabled():
        chapter = generate_bootstrap_chapter(payload.model_dump(mode="python"), story_bible)
        return (
            chapter.title,
            chapter.content,
            chapter.generation_meta,
            {
                "event_summary": chapter.event_summary,
                "character_updates": chapter.character_updates,
                "new_clues": chapter.new_clues,
                "open_hooks": chapter.open_hooks,
                "closed_hooks": chapter.closed_hooks,
            },
        )

    title = "第1章 开端"
    content = (
        f"{payload.protagonist_name}第一次意识到不对劲，是在那个普通得不能再普通的夜晚。\n\n"
        f"这座世界的底色来自这样一个设定：{payload.premise}。\n\n"
        f"作为故事的主角，{payload.protagonist_name}并不知道自己即将被卷入怎样的命运，"
        f"但读者已经能从空气里嗅到危险、秘密和某种缓慢逼近的变化。\n\n"
        f"这一章的任务，是把读者带入{payload.genre}的氛围中，并埋下主线的第一枚钩子。\n\n"
        f"当{payload.protagonist_name}看向远处时，他/她意识到，真正的故事，从这一刻才开始。"
    )
    generation_meta = {
        "generator": "mock_bootstrap_generator",
        "story_mode": "chapter_serial",
        "version": "0.1.0",
    }
    summary = {
        "event_summary": f"{payload.protagonist_name}在故事开端察觉异常，主线冲突被引入。",
        "character_updates": {payload.protagonist_name: {"stage": "introduced"}},
        "new_clues": [story_bible["core_conflict"]],
        "open_hooks": ["主角即将接触真正的谜团"],
        "closed_hooks": [],
    }
    return title, content, generation_meta, summary

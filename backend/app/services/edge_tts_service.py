from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import settings
from app.models.chapter import Chapter
from app.models.time_utils import utcnow_naive

try:
    import edge_tts
except Exception:  # pragma: no cover - graceful fallback when dependency is missing
    edge_tts = None


_VOICE_OPTIONS = [
    {"value": "zh-CN-YunxiNeural", "label": "云希（男声，沉稳）"},
    {"value": "zh-CN-XiaoxiaoNeural", "label": "晓晓（女声，通用）"},
    {"value": "zh-CN-YunjianNeural", "label": "云健（男声，明亮）"},
    {"value": "zh-CN-XiaoyiNeural", "label": "晓伊（女声，叙述感）"},
    {"value": "zh-CN-liaoning-XiaobeiNeural", "label": "晓北（女声，东北口音）"},
    {"value": "zh-CN-shaanxi-XiaoniNeural", "label": "晓妮（女声，陕西口音）"},
]
_VOICE_LABELS = {item["value"]: item["label"] for item in _VOICE_OPTIONS}
_PERCENT_PATTERN = re.compile(r"^[+-]?\d+%$")
_HZ_PATTERN = re.compile(r"^[+-]?\d+Hz$", re.IGNORECASE)
_LOCK_GUARD = Lock()
_TTS_LOCKS: dict[str, Lock] = {}


class EdgeTtsError(RuntimeError):
    pass


class EdgeTtsBusyError(EdgeTtsError):
    pass


class EdgeTtsUnavailableError(EdgeTtsError):
    pass


class EdgeTtsBadRequestError(EdgeTtsError):
    pass


def list_voice_options() -> list[dict[str, str]]:
    return [dict(item) for item in _VOICE_OPTIONS]


def get_voice_label(voice: str | None) -> str:
    voice = (voice or "").strip()
    return _VOICE_LABELS.get(voice, voice or "未知音色")


def ensure_tts_available() -> None:
    if not settings.tts_enabled:
        raise EdgeTtsUnavailableError("Edge TTS 当前已禁用，请检查 TTS_ENABLED 配置。")
    if edge_tts is None:
        raise EdgeTtsUnavailableError("缺少 edge-tts 依赖，请先执行 pip install -r backend/requirements.txt。")


def _normalize_percent(value: str | None, *, default: str, field_name: str) -> str:
    final = (value or default or "").strip()
    if not _PERCENT_PATTERN.fullmatch(final):
        raise EdgeTtsBadRequestError(f"{field_name} 格式不合法，示例：+0%、-15%、+20%")
    return final


def _normalize_pitch(value: str | None, *, default: str) -> str:
    final = (value or default or "").strip()
    if not _HZ_PATTERN.fullmatch(final):
        raise EdgeTtsBadRequestError("pitch 格式不合法，示例：+0Hz、-40Hz、+80Hz")
    return final


def _normalize_voice(value: str | None) -> str:
    voice = (value or settings.tts_default_voice or "").strip()
    valid = {item["value"] for item in _VOICE_OPTIONS}
    if voice not in valid:
        raise EdgeTtsBadRequestError("不支持的音色，请从下拉列表中选择。")
    return voice


def normalize_tts_options(payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    return {
        "voice": _normalize_voice(payload.get("voice")),
        "rate": _normalize_percent(payload.get("rate"), default=settings.tts_default_rate, field_name="rate"),
        "volume": _normalize_percent(payload.get("volume"), default=settings.tts_default_volume, field_name="volume"),
        "pitch": _normalize_pitch(payload.get("pitch"), default=settings.tts_default_pitch),
    }


def _content_hash(content: str) -> str:
    compact = str(content or "").strip().replace("\r\n", "\n")
    return hashlib.sha1(compact.encode("utf-8")).hexdigest()


def _tts_fingerprint(chapter: Chapter, options: dict[str, str]) -> str:
    data = {
        "novel_id": chapter.novel_id,
        "chapter_no": chapter.chapter_no,
        "title": chapter.title,
        "content_hash": _content_hash(chapter.content),
        **options,
    }
    return hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]


def _tts_text(chapter: Chapter) -> str:
    title_line = f"第 {chapter.chapter_no} 章，{chapter.title}" if chapter.title else f"第 {chapter.chapter_no} 章"
    content = str(chapter.content or "").strip()
    if not content:
        raise EdgeTtsBadRequestError("当前章节正文为空，无法生成朗读音频。")
    return f"{title_line}\n\n{content}"


def _chapter_dir(chapter: Chapter) -> Path:
    return settings.media_root_path / "tts" / f"novel-{chapter.novel_id}" / f"chapter-{chapter.chapter_no}"


def _voice_slug(voice: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", voice.lower()).strip("-") or "voice"


def _relative_audio_path(chapter: Chapter, options: dict[str, str], fingerprint: str) -> str:
    return f"tts/novel-{chapter.novel_id}/chapter-{chapter.chapter_no}/chapter-{chapter.chapter_no}-{_voice_slug(options['voice'])}-{fingerprint}.mp3"


def _relative_subtitle_path(relative_audio_path: str) -> str:
    return str(Path(relative_audio_path).with_suffix(".vtt"))


def _absolute_path(relative_path: str) -> Path:
    return settings.media_root_path / relative_path


def _build_media_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return f"/app/media/{relative_path}"


def _get_lock(lock_key: str) -> Lock:
    with _LOCK_GUARD:
        lock = _TTS_LOCKS.get(lock_key)
        if lock is None:
            lock = Lock()
            _TTS_LOCKS[lock_key] = lock
        return lock


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _chapter_meta(chapter: Chapter) -> dict[str, Any]:
    return (chapter.generation_meta or {}) if isinstance(chapter.generation_meta, dict) else {}


def _tts_meta(chapter: Chapter) -> dict[str, Any]:
    raw = _chapter_meta(chapter).get("tts") or {}
    return raw if isinstance(raw, dict) else {}


def _extract_variants(tts_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}
    raw_variants = tts_meta.get("variants") if isinstance(tts_meta, dict) else None
    if not isinstance(raw_variants, dict):
        return variants
    for key, item in raw_variants.items():
        if not isinstance(item, dict):
            continue
        voice = str(item.get("voice") or key or "").strip()
        if not voice:
            continue
        variants[voice] = {**item, "voice": voice}
    return variants


def _variant_matches_current_content(variant: dict[str, Any], current_content_hash: str) -> bool:
    return str(variant.get("content_hash") or "").strip() == current_content_hash


def _variant_payload_from_meta(variant: dict[str, Any]) -> dict[str, Any] | None:
    relative_path = str(variant.get("relative_path") or "").strip()
    subtitle_relative_path = str(variant.get("subtitle_relative_path") or "").strip()
    if not relative_path:
        return None
    audio_path = _absolute_path(relative_path)
    if not audio_path.exists():
        return None
    subtitle_path = _absolute_path(subtitle_relative_path) if subtitle_relative_path else None
    file_size_bytes = variant.get("file_size_bytes") if isinstance(variant.get("file_size_bytes"), int) else None
    subtitle_file_size_bytes = variant.get("subtitle_file_size_bytes") if isinstance(variant.get("subtitle_file_size_bytes"), int) else None
    if file_size_bytes is None:
        try:
            file_size_bytes = audio_path.stat().st_size
        except OSError:
            file_size_bytes = None
    if subtitle_path and subtitle_path.exists() and subtitle_file_size_bytes is None:
        try:
            subtitle_file_size_bytes = subtitle_path.stat().st_size
        except OSError:
            subtitle_file_size_bytes = None
    voice = str(variant.get("voice") or "").strip()
    return {
        "voice": voice,
        "voice_label": get_voice_label(voice),
        "rate": str(variant.get("rate") or settings.tts_default_rate),
        "volume": str(variant.get("volume") or settings.tts_default_volume),
        "pitch": str(variant.get("pitch") or settings.tts_default_pitch),
        "audio_url": _build_media_url(relative_path),
        "subtitle_url": _build_media_url(subtitle_relative_path) if subtitle_path and subtitle_path.exists() else None,
        "file_size_bytes": file_size_bytes,
        "subtitle_file_size_bytes": subtitle_file_size_bytes,
        "generated_at": _parse_datetime(variant.get("generated_at")),
    }


def _collect_generated_variants(chapter: Chapter) -> list[dict[str, Any]]:
    tts_meta = _tts_meta(chapter)
    current_content_hash = _content_hash(chapter.content)
    variants_by_voice = _extract_variants(tts_meta)
    items: list[dict[str, Any]] = []
    for option in _VOICE_OPTIONS:
        voice = option["value"]
        variant = variants_by_voice.get(voice)
        if not variant or not _variant_matches_current_content(variant, current_content_hash):
            continue
        payload = _variant_payload_from_meta(variant)
        if payload:
            items.append(payload)
    return items


def _find_variant(generated_variants: list[dict[str, Any]], voice: str) -> dict[str, Any] | None:
    for item in generated_variants:
        if item.get("voice") == voice:
            return item
    return None


def get_chapter_tts_status(chapter: Chapter, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    options = normalize_tts_options(payload)
    generated_variants = _collect_generated_variants(chapter)
    selected_variant = _find_variant(generated_variants, options["voice"])
    ready = selected_variant is not None
    stale = False
    reason = None
    if ready:
        reason = f"{get_voice_label(options['voice'])} 的 MP3 已生成，可直接播放。"
    elif generated_variants:
        existing = "、".join(item["voice_label"] for item in generated_variants)
        reason = f"{get_voice_label(options['voice'])} 的 MP3 还没生成，当前已生成：{existing}。"
    else:
        reason = "还没有生成本章朗读音频。"

    if not settings.tts_enabled:
        reason = "朗读功能已关闭。"
    elif edge_tts is None:
        reason = "edge-tts 依赖未安装。"

    return {
        "novel_id": chapter.novel_id,
        "chapter_no": chapter.chapter_no,
        "title": chapter.title,
        "enabled": bool(settings.tts_enabled and edge_tts is not None),
        "ready": ready,
        "generating": False,
        "stale": stale,
        "voice": options["voice"],
        "rate": options["rate"],
        "volume": options["volume"],
        "pitch": options["pitch"],
        "audio_url": selected_variant.get("audio_url") if selected_variant else None,
        "subtitle_url": selected_variant.get("subtitle_url") if selected_variant else None,
        "file_size_bytes": selected_variant.get("file_size_bytes") if selected_variant else None,
        "subtitle_file_size_bytes": selected_variant.get("subtitle_file_size_bytes") if selected_variant else None,
        "generated_at": selected_variant.get("generated_at") if selected_variant else None,
        "reason": reason,
        "voice_options": list_voice_options(),
        "generated_variants": generated_variants,
    }


def _format_vtt_timestamp_from_100ns(value: int | float | None) -> str:
    raw = max(0, int(value or 0))
    total_ms = raw // 10_000
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    seconds = (total_ms % 60_000) // 1_000
    milliseconds = total_ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _render_webvtt(boundary_events: list[dict[str, Any]], fallback_text: str) -> str:
    lines = ["WEBVTT", ""]
    usable_events: list[dict[str, Any]] = []
    for event in boundary_events:
        cue_text = str(event.get("text") or "").strip()
        if not cue_text:
            continue
        start = max(0, int(event.get("offset") or 0))
        duration = max(0, int(event.get("duration") or 0))
        end = start + duration
        usable_events.append({"text": cue_text, "start": start, "end": end})

    if not usable_events:
        clean_text = " ".join(str(fallback_text or "").split()) or "字幕生成中没有捕获到边界事件。"
        lines.extend([
            "1",
            "00:00:00.000 --> 00:00:10.000",
            clean_text,
            "",
        ])
        return "\n".join(lines)

    for index, event in enumerate(usable_events, start=1):
        lines.extend([
            str(index),
            f"{_format_vtt_timestamp_from_100ns(event['start'])} --> {_format_vtt_timestamp_from_100ns(event['end'])}",
            event["text"],
            "",
        ])
    return "\n".join(lines)


async def _save_audio_and_subtitles_async(text: str, audio_path: Path, subtitle_path: Path, options: dict[str, str]) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=options["voice"],
        rate=options["rate"],
        volume=options["volume"],
        pitch=options["pitch"],
    )
    boundary_events: list[dict[str, Any]] = []
    with audio_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            chunk_type = chunk.get("type")
            if chunk_type == "audio":
                audio_file.write(chunk["data"])
            elif chunk_type in {"WordBoundary", "SentenceBoundary"}:
                boundary_events.append(
                    {
                        "offset": chunk.get("offset"),
                        "duration": chunk.get("duration"),
                        "text": chunk.get("text"),
                        "type": chunk_type,
                    }
                )
    subtitle_path.write_text(_render_webvtt(boundary_events, text), encoding="utf-8")


def _persist_variant_meta(chapter: Chapter, options: dict[str, str], *, audio_relative_path: str, subtitle_relative_path: str, fingerprint: str) -> None:
    meta = dict(_chapter_meta(chapter))
    tts_meta = dict(_tts_meta(chapter))
    variants = _extract_variants(tts_meta)
    audio_path = _absolute_path(audio_relative_path)
    subtitle_path = _absolute_path(subtitle_relative_path)
    variant_meta = {
        "voice": options["voice"],
        "rate": options["rate"],
        "volume": options["volume"],
        "pitch": options["pitch"],
        "fingerprint": fingerprint,
        "relative_path": audio_relative_path,
        "subtitle_relative_path": subtitle_relative_path,
        "generated_at": utcnow_naive().isoformat(timespec="seconds") + "Z",
        "content_hash": _content_hash(chapter.content),
        "file_size_bytes": audio_path.stat().st_size if audio_path.exists() else None,
        "subtitle_file_size_bytes": subtitle_path.stat().st_size if subtitle_path.exists() else None,
    }
    variants[options["voice"]] = variant_meta
    tts_meta.update(
        {
            "default_voice": settings.tts_default_voice,
            "last_voice": options["voice"],
            "variants": variants,
            **variant_meta,
        }
    )
    meta["tts"] = tts_meta
    chapter.generation_meta = meta


def generate_chapter_tts(chapter: Chapter, payload: dict[str, Any] | None = None, *, force_regenerate: bool = False) -> dict[str, Any]:
    ensure_tts_available()
    options = normalize_tts_options(payload)
    status = get_chapter_tts_status(chapter, options)
    if status["ready"] and not force_regenerate:
        return status

    lock = _get_lock(f"{chapter.novel_id}:{chapter.chapter_no}")
    if not lock.acquire(blocking=False):
        raise EdgeTtsBusyError("当前章节朗读音频正在生成，请稍候刷新。")

    try:
        chapter_dir = _chapter_dir(chapter)
        chapter_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = _tts_fingerprint(chapter, options)
        audio_relative_path = _relative_audio_path(chapter, options, fingerprint)
        subtitle_relative_path = _relative_subtitle_path(audio_relative_path)
        audio_path = _absolute_path(audio_relative_path)
        subtitle_path = _absolute_path(subtitle_relative_path)
        temp_audio_path = audio_path.with_suffix(".tmp.mp3")
        temp_subtitle_path = subtitle_path.with_suffix(".tmp.vtt")
        text = _tts_text(chapter)
        asyncio.run(_save_audio_and_subtitles_async(text, temp_audio_path, temp_subtitle_path, options))
        temp_audio_path.replace(audio_path)
        temp_subtitle_path.replace(subtitle_path)
        _persist_variant_meta(
            chapter,
            options,
            audio_relative_path=audio_relative_path,
            subtitle_relative_path=subtitle_relative_path,
            fingerprint=fingerprint,
        )
        return get_chapter_tts_status(chapter, options)
    except EdgeTtsError:
        raise
    except Exception as exc:  # pragma: no cover - depends on network/runtime
        raise EdgeTtsError(f"Edge TTS 生成失败：{exc}") from exc
    finally:
        lock.release()

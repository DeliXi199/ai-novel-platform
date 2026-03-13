from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

REALM_TERMS = [
    "炼体", "炼气", "筑基", "结丹", "金丹", "元婴", "化神", "炼虚", "返虚", "合体", "大乘", "渡劫", "真仙",
]
REALM_SUFFIX = r"(?:境|期|层|重|阶|初期|中期|后期|圆满)?"
REALM_PATTERN = re.compile(r"(?:炼体|炼气|筑基|结丹|金丹|元婴|化神|炼虚|返虚|合体|大乘|渡劫|真仙)" + REALM_SUFFIX)
BREAKTHROUGH_MARKERS = ("突破", "晋升", "晋入", "踏入", "迈入", "冲开", "晋阶", "凝成", "结成", "升到")
REGRESSION_MARKERS = ("跌落", "跌回", "被废", "修为尽失", "境界大损", "跌境")
REVIVAL_MARKERS = ("复生", "复活", "还魂", "借尸还魂", "夺舍", "假死", "诈死", "救回", "苏醒")
RECOVERY_MARKERS = ("痊愈", "恢复", "养好", "好转", "稳住", "止血", "接骨", "疗伤", "服药", "伤势尽复")
CONCEAL_MARKERS = ("掩饰", "伪装", "假身份", "灭口", "封口", "洗清嫌疑", "遮掩")
TRANSFER_MARKERS = ("交给", "递给", "卖给", "献给", "被夺", "被抢", "夺走", "丢失", "失去", "换给", "归还", "送给", "夺回", "收回", "找回")
ITEM_TERMS = ["令牌", "玉佩", "古镜", "残页", "灵草", "钥匙", "骨片", "戒指", "玉简", "阵盘", "丹炉", "法器", "飞剑", "符箓", "地图", "卷轴", "石板", "药瓶", "储物袋", "丹药"]
DEAD_TERMS = ("身死", "死去", "毙命", "陨落", "断气", "尸体", "被杀", "被斩", "杀死", "斩杀")
ALIVE_TERMS = ("活着", "未死", "没死", "还活着", "苏醒", "睁开眼", "仍活着")
FALSE_DEAD_PATTERNS = (
    "堵死", "堵死了", "气死", "累死", "困死", "吓死", "烦死", "笑死", "恨死", "急死", "死路", "活要见人，死要见尸",
)
SEVERE_INJURY_TERMS = ("重伤", "断臂", "断骨", "吐血", "失血", "昏迷", "中毒", "废了", "伤势极重", "濒死")
LIGHT_INJURY_TERMS = ("轻伤", "擦伤", "青肿", "刀口", "伤口", "伤势", "负伤")
HEALTHY_TERMS = ("无伤", "完好", "痊愈", "恢复如初", "精神尚可")
EXPOSED_TERMS = ("身份暴露", "被识破", "认出", "知道了.*身份", "看穿.*来历", "暴露了.*来历")
HIDDEN_TERMS = ("身份未暴露", "没人知道.*身份", "仍未暴露", "隐藏身份", "掩住来历")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _text_blob(*parts: Any) -> str:
    merged = "\n".join(str(part or "") for part in parts if part)
    return merged.replace("\r\n", "\n").replace("\r", "\n")


def _window(text: str, start: int, end: int, span: int = 36) -> str:
    left = max(0, start - span)
    right = min(len(text), end + span)
    return text[left:right]


def _split_sentences(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(?<=[。！？!?；;\n])", normalized)
    return [part.strip() for part in parts if part and part.strip()]


def _name_context_snippets(text: str, name: str, *, radius: int = 1) -> list[str]:
    sentences = _split_sentences(text)
    snippets: list[str] = []
    for idx, sentence in enumerate(sentences):
        if name not in sentence:
            continue
        left = max(0, idx - radius)
        right = min(len(sentences), idx + radius + 1)
        snippet = "".join(sentences[left:right]).strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    if snippets:
        return snippets
    fallback: list[str] = []
    for match in re.finditer(re.escape(name), text):
        snippet = _window(text, match.start(), match.end(), span=28).strip()
        if snippet and snippet not in fallback:
            fallback.append(snippet)
    return fallback


class HardFactConflict(ValueError):
    def __init__(self, report: dict[str, Any]):
        super().__init__(report.get("summary") or "hard fact conflict")
        self.report = report


def empty_hard_fact_guard() -> dict[str, Any]:
    return {
        "enabled": True,
        "protected_categories": ["realm", "life_status", "injury_status", "identity_exposure", "item_ownership"],
        "published_state": {"realm": {}, "life_status": {}, "injury_status": {}, "identity_exposure": {}, "item_ownership": {}},
        "stock_state": {"realm": {}, "life_status": {}, "injury_status": {}, "identity_exposure": {}, "item_ownership": {}},
        "last_checked_chapter": 0,
        "last_conflict_report": None,
        "chapter_reports": [],
    }


def ensure_hard_fact_guard(story_bible: dict[str, Any]) -> dict[str, Any]:
    guard = story_bible.setdefault("hard_fact_guard", empty_hard_fact_guard())
    guard.setdefault("enabled", True)
    guard.setdefault("protected_categories", ["realm", "life_status", "injury_status", "identity_exposure", "item_ownership"])
    for key in ("published_state", "stock_state"):
        state = guard.setdefault(key, {})
        state.setdefault("realm", {})
        state.setdefault("life_status", {})
        state.setdefault("injury_status", {})
        state.setdefault("identity_exposure", {})
        state.setdefault("item_ownership", {})
    guard.setdefault("last_checked_chapter", 0)
    guard.setdefault("last_conflict_report", None)
    guard.setdefault("chapter_reports", [])
    return guard


def build_hard_fact_guard_rules() -> dict[str, Any]:
    return {
        "enabled": True,
        "check_before_persist": True,
        "check_before_publish": True,
        "reference_priority": ["published_state", "stock_state", "recent_bridge"],
        "protected_categories": ["realm", "life_status", "injury_status", "identity_exposure", "item_ownership"],
        "conflict_policy": "高风险硬事实冲突时停止入库/发布，优先修正后续稿与结构，不回改已发布正文。对语义歧义项优先走大模型复核，不靠单纯关键词硬拦。",
    }

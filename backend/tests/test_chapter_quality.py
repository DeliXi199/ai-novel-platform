import pytest

from app.services.chapter_quality import validate_chapter_content
from app.services.generation_exceptions import ErrorCodes, GenerationError


GOOD_TEXT = """
林玄推开药铺后门时，先用指节轻轻敲了两下木框，确认无人应声，才侧身钻进雨后的潮气里。
院角那口旧缸沿着裂痕往下渗水，他蹲下去摸了一把，指腹立刻觉出一丝不该有的温差，像是缸底另藏着什么东西。
他没有立刻动手，而是先把门栓重新卡紧，又把案上的药包换了个位置，免得掌柜回来后一眼看出院里有人翻找过。
等脚步声彻底远了，他才把缸挪开半寸，果然在青砖缝里摸到一张被油纸裹住的薄页；纸面发硬，边角却残留着新近折开的痕迹。
他刚把薄页抽出来，外头巷口便传来短促的犬吠，紧跟着又是一阵压得很低的说话声，让他立刻意识到这东西未必只是旧物那么简单。
""".strip()


BAD_DUPLICATE = """
林玄蹲在墙角摸索砖缝时，先抬手按住呼吸，再把袖口往里一卷，免得灰末沾到掌心的湿汗。
林玄蹲在墙角摸索砖缝时，先抬手按住呼吸，再把袖口往里一卷，免得灰末沾到掌心的湿汗。
他听见门外木板被风吹得轻轻一响，却没有立刻退开，只是顺着缝隙继续往里摸，想确认那点异样到底是什么。
他听见门外木板被风吹得轻轻一响，却没有立刻退开，只是顺着缝隙继续往里摸，想确认那点异样到底是什么。
""".strip()


def test_validate_chapter_content_accepts_complete_text() -> None:
    validate_chapter_content(
        title="第1章",
        content=GOOD_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=400,
        hook_style="危险逼近",
    )


def test_validate_chapter_content_rejects_duplicate_paragraphs() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第2章",
            content=BAD_DUPLICATE,
            min_visible_chars=20,
            hard_min_visible_chars=20,
            target_visible_chars_max=300,
            hook_style="危险逼近",
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_DUPLICATED_PARAGRAPHS

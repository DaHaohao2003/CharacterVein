from character_vein_api.document_processing import analyze_document_text, extract_document_text
from character_vein_providers import DeterministicTextProvider, DeterministicVisionProvider


async def test_generic_request_does_not_guess_first_han_character() -> None:
    spec = await DeterministicTextProvider().parse_task("请根据这张古文字拓片制作课堂讲解")

    assert spec.target_characters == []


async def test_explicit_target_is_still_parsed() -> None:
    spec = await DeterministicTextProvider().parse_task("请制作一份关于鼎字演化的讲解")

    assert spec.target_characters == ["鼎"]


def test_markdown_document_is_extracted_locally() -> None:
    content = "# 展签资料\n\n目标字：鼎\n时代：商代晚期\n来源：某博物馆展签".encode()

    text = extract_document_text(content, "text/markdown", "label.md")
    analysis = analyze_document_text(text)

    assert analysis.target_characters == ["鼎"]
    assert analysis.explicit_periods == ["商代晚期"]
    assert analysis.user_sources == ["来源：某博物馆展签"]
    assert analysis.model == "local-document-parser"


async def test_image_fallback_requires_confirmation_without_guessing() -> None:
    analysis = await DeterministicVisionProvider().analyze_image(b"image", "image/png")

    assert analysis.target_characters == []
    assert analysis.uncertain_glyphs is True
    assert analysis.requires_target_confirmation is True
    assert analysis.fallback_used is True

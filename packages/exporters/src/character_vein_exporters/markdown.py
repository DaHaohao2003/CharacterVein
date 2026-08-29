from character_vein_domain import EvolutionPackage, GeneratedContent, SourceOrigin


def export_markdown(content: GeneratedContent, evolution: EvolutionPackage) -> str:
    questions = "\n".join(
        f"{index}. {question}" for index, question in enumerate(content.interaction_questions, 1)
    )
    sources = "\n".join(
        (
            f"- [{item.authority_level}] {item.title}，{item.author_or_org}，{item.locator}"
            f"（许可：{item.license}）" + (f"：[来源链接]({item.url})" if item.url else "")
        )
        for item in evolution.evidence
        if (
            item.origin in {SourceOrigin.WEB, SourceOrigin.USER_UPLOAD}
            or (
                item.origin == SourceOrigin.FIXTURE
                and item.metadata.get("kind") == "evolution_framework"
            )
        )
        and "jiezi"
        not in " ".join([item.evidence_id, item.source_id, item.title, item.url or ""]).lower()
        and item.metadata.get("kind")
        not in {"glyph_dataset", "glyph_stage", "glyph_context"}
    )
    return f"{content.body_markdown}\n\n## 互动题\n{questions}\n\n## 来源\n{sources}\n"

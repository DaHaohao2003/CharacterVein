import html
import json
from typing import Any

from character_vein_domain import (
    CommunicationAsset,
    CulturalMotif,
    InteractiveStoryContent,
    ShortVideoScriptContent,
    SocialCardsContent,
)


def export_communication_package_markdown(
    motif: CulturalMotif,
    assets: dict[str, CommunicationAsset],
) -> str:
    lines = [
        f"# {motif.title}",
        "",
        f"> {motif.core_message}",
        "",
        f"**开场钩子：** {motif.opening_hook}",
        "",
        "## 互动文化长页",
        "",
    ]
    story = assets.get("interactive_story")
    if story and isinstance(story.content, InteractiveStoryContent):
        lines.extend([f"### {story.content.title}", "", story.content.lede, ""])
        for section in story.content.sections:
            lines.extend([f"#### {section.title}", "", section.narrative, ""])
            if section.interaction_prompt:
                lines.extend([f"> 互动：{section.interaction_prompt}", ""])
        lines.extend([story.content.closing, ""])

    lines.extend(["## 五张图文卡片", ""])
    cards = assets.get("social_cards")
    if cards and isinstance(cards.content, SocialCardsContent):
        for card in cards.content.cards:
            lines.extend(
                [
                    f"### {card.index}. {card.headline}",
                    "",
                    card.body,
                    "",
                    f"画面建议：{card.visual_direction}",
                    "",
                ]
            )
        lines.extend([f"发布文案：{cards.content.posting_caption}", ""])

    lines.extend(["## 60 秒短视频脚本", ""])
    video = assets.get("short_video_script")
    if video and isinstance(video.content, ShortVideoScriptContent):
        lines.extend([f"### {video.content.title}", "", video.content.opening_hook, ""])
        for scene in video.content.scenes:
            lines.extend(
                [
                    f"#### {scene.start_second}s—{scene.end_second}s · {scene.subtitle}",
                    "",
                    f"- 画面：{scene.visual}",
                    f"- 旁白：{scene.narration}",
                    "",
                ]
            )
        lines.extend([f"结尾互动：{video.content.closing_cta}", ""])
    return "\n".join(lines).strip() + "\n"


def export_communication_package_html(
    motif: CulturalMotif,
    assets: dict[str, CommunicationAsset],
) -> str:
    markdown = export_communication_package_markdown(motif, assets)
    body = "\n".join(f"<p>{html.escape(line)}</p>" for line in markdown.splitlines())
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{html.escape(motif.title)}</title>"
        "<style>body{max-width:880px;margin:40px auto;padding:0 24px;font:16px/1.8 serif;}"
        "p{white-space:pre-wrap;margin:.35rem 0;}</style></head><body>"
        f"{body}</body></html>"
    )


def export_communication_package_json(
    *,
    task_id: str,
    motif: CulturalMotif,
    assets: dict[str, CommunicationAsset],
    evaluation: dict[str, Any] | None,
) -> str:
    return json.dumps(
        {
            "task_id": task_id,
            "cultural_motif": motif.model_dump(mode="json"),
            "communication_assets": {
                key: value.model_dump(mode="json") for key, value in assets.items()
            },
            "artifact_evaluation": evaluation,
        },
        ensure_ascii=False,
        indent=2,
    )

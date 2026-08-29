from __future__ import annotations

import re
from typing import Literal
from urllib.parse import quote

from character_vein_domain import (
    CreativeArtifactDraft,
    RichArtifactDocument,
    RichBlockKind,
    RichContentBlock,
    RichContentPage,
)

ExportFormat = Literal["docx", "html", "txt", "pdf", "pptx"]
PageLayout = Literal["cover", "feature", "split", "text", "gallery"]
SUPPORTED_EXPORT_FORMATS: list[ExportFormat] = ["docx", "html", "txt", "pdf", "pptx"]
GLYPH_SCRIPT_LABELS = {
    "J": "甲骨文",
    "B": "金文",
    "G": "战国文字",
    "S": "篆书",
    "L": "隶书",
    "K": "楷书",
    "C": "草书",
}


def build_rich_document(
    draft: CreativeArtifactDraft,
    parent: RichArtifactDocument | None = None,
) -> RichArtifactDocument:
    """Build the canonical visual document used by preview and all exporters."""

    if draft.rich_document is not None:
        document = draft.rich_document.model_copy(deep=True)
        document.supported_formats = list(SUPPORTED_EXPORT_FORMATS)
        return _lock_registered_glyphs(document, set(draft.visual_hook_ids))

    parsed_pages = _split_large_pages(
        _parse_markdown(draft.title, draft.summary, draft.content_markdown)
    )
    pages: list[RichContentPage] = []
    for page_index, (title, layout, blocks) in enumerate(parsed_pages):
        parent_page = (
            parent.pages[page_index] if parent and page_index < len(parent.pages) else None
        )
        page_id = parent_page.page_id if parent_page else f"page-{page_index + 1}"
        normalized_blocks: list[RichContentBlock] = []
        for block_index, block in enumerate(blocks):
            parent_block = (
                parent_page.blocks[block_index]
                if parent_page and block_index < len(parent_page.blocks)
                else None
            )
            block.block_id = (
                parent_block.block_id
                if parent_block and parent_block.kind == block.kind
                else f"{page_id}-block-{block_index + 1}"
            )
            normalized_blocks.append(block)
        pages.append(
            RichContentPage(
                page_id=page_id,
                title=title,
                layout=layout,
                blocks=normalized_blocks,
            )
        )

    _attach_glyph_images(pages, draft.visual_hook_ids)
    return RichArtifactDocument(
        title=draft.title,
        pages=pages,
        supported_formats=list(SUPPORTED_EXPORT_FORMATS),
    )


def _parse_markdown(
    title: str,
    summary: str,
    markdown: str,
) -> list[tuple[str, PageLayout, list[RichContentBlock]]]:
    pages: list[tuple[str, PageLayout, list[RichContentBlock]]] = []
    current_title = title
    current_blocks: list[RichContentBlock] = [
        RichContentBlock(block_id="pending", kind=RichBlockKind.HEADING, text=title, level=1),
        RichContentBlock(block_id="pending", kind=RichBlockKind.PARAGRAPH, text=summary),
    ]
    paragraph_lines: list[str] = []
    list_lines: list[str] = []

    def flush_text() -> None:
        nonlocal paragraph_lines, list_lines
        if paragraph_lines:
            text = "\n".join(paragraph_lines).strip()
            if text:
                current_blocks.append(
                    RichContentBlock(block_id="pending", kind=RichBlockKind.PARAGRAPH, text=text)
                )
            paragraph_lines = []
        if list_lines:
            current_blocks.append(
                RichContentBlock(
                    block_id="pending", kind=RichBlockKind.LIST, text="\n".join(list_lines)
                )
            )
            list_lines = []

    def flush_page() -> None:
        if current_blocks:
            layout: PageLayout = (
                "cover" if not pages else ("split" if len(current_blocks) <= 5 else "text")
            )
            pages.append((current_title, layout, list(current_blocks)))

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_text()
            level = len(heading.group(1))
            heading_text = _clean_markdown(heading.group(2))
            if (
                heading_text == title
                and len(current_blocks) == 2
                and current_blocks[0].kind == RichBlockKind.HEADING
            ):
                continue
            has_body = any(block.kind != RichBlockKind.HEADING for block in current_blocks)
            starts_new_page = level <= 2 or (level == 3 and has_body)
            if starts_new_page and current_blocks and heading_text != title:
                flush_page()
                current_title = heading_text
                current_blocks = []
            current_blocks.append(
                RichContentBlock(
                    block_id="pending",
                    kind=RichBlockKind.HEADING,
                    text=heading_text,
                    level=level,
                )
            )
            continue
        if re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            if paragraph_lines:
                flush_text()
            list_lines.append(_clean_markdown(re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line)))
            continue
        if not line:
            flush_text()
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            flush_text()
            continue
        if line.startswith(">"):
            flush_text()
            current_blocks.append(
                RichContentBlock(
                    block_id="pending",
                    kind=RichBlockKind.QUOTE,
                    text=_clean_markdown(line.lstrip("> ")),
                )
            )
            continue
        paragraph_lines.append(_clean_markdown(line))

    flush_text()
    flush_page()
    return pages or [
        (
            title,
            "cover",
            [
                RichContentBlock(
                    block_id="pending", kind=RichBlockKind.HEADING, text=title, level=1
                ),
                RichContentBlock(block_id="pending", kind=RichBlockKind.PARAGRAPH, text=summary),
            ],
        )
    ]


def _attach_glyph_images(pages: list[RichContentPage], image_ids: list[str]) -> None:
    if not pages:
        return
    for image_index, image_id in enumerate(image_ids[: min(8, max(1, len(pages) * 2))]):
        page = pages[image_index % len(pages)]
        block_id = f"{page.page_id}-glyph-{image_index + 1}"
        script_label = _glyph_script_label(image_id)
        page.blocks.append(
            RichContentBlock(
                block_id=block_id,
                kind=RichBlockKind.IMAGE,
                image_id=image_id,
                image_url=f"/backend/api/v1/glyph-images/{quote(image_id, safe='/+.-')}",
                alt_text=f"{page.title}相关{script_label}字形",
                caption=f"{script_label}代表字形",
                source_kind="glyph",
                locked=True,
            )
        )


def _glyph_script_label(image_id: str) -> str:
    parts = image_id.replace("\\", "/").split("/")
    return GLYPH_SCRIPT_LABELS.get(parts[1].upper(), "历史") if len(parts) > 1 else "历史"


def _lock_registered_glyphs(
    document: RichArtifactDocument,
    allowed_image_ids: set[str],
) -> RichArtifactDocument:
    for page in document.pages:
        for block in page.blocks:
            if block.image_id in allowed_image_ids:
                block.source_kind = "glyph"
                block.locked = True
                block.image_url = (
                    f"/backend/api/v1/glyph-images/{quote(block.image_id or '', safe='/+.-')}"
                )
    return document


def _split_large_pages(
    pages: list[tuple[str, PageLayout, list[RichContentBlock]]],
    max_blocks: int = 6,
) -> list[tuple[str, PageLayout, list[RichContentBlock]]]:
    result: list[tuple[str, PageLayout, list[RichContentBlock]]] = []
    for title, layout, blocks in pages:
        if len(blocks) <= max_blocks:
            result.append((title, layout, blocks))
            continue
        for continuation, page_blocks in enumerate(
            _balanced_block_chunks(blocks, max_blocks=max_blocks)
        ):
            page_title = title if continuation == 0 else f"{title}（续{continuation + 1}）"
            page_layout: PageLayout = layout if continuation == 0 else "text"
            result.append((page_title, page_layout, page_blocks))
    return result


def _balanced_block_chunks(
    blocks: list[RichContentBlock],
    *,
    max_blocks: int,
) -> list[list[RichContentBlock]]:
    page_count = (len(blocks) + max_blocks - 1) // max_blocks
    prefix_weights = [0]
    for block in blocks:
        prefix_weights.append(prefix_weights[-1] + max(1, len(block.text.strip())))

    unreachable = float("inf")
    costs = [[unreachable] * (len(blocks) + 1) for _ in range(page_count + 1)]
    previous = [[-1] * (len(blocks) + 1) for _ in range(page_count + 1)]
    costs[0][0] = 0
    for pages_used in range(1, page_count + 1):
        for block_count in range(pages_used, len(blocks) + 1):
            for chunk_size in range(1, min(max_blocks, block_count) + 1):
                start = block_count - chunk_size
                if costs[pages_used - 1][start] == unreachable:
                    continue
                chunk_weight = prefix_weights[block_count] - prefix_weights[start]
                candidate = max(costs[pages_used - 1][start], chunk_weight)
                if candidate < costs[pages_used][block_count]:
                    costs[pages_used][block_count] = candidate
                    previous[pages_used][block_count] = start

    chunks: list[list[RichContentBlock]] = []
    end = len(blocks)
    for pages_used in range(page_count, 0, -1):
        start = previous[pages_used][end]
        if start < 0:
            return [blocks[offset : offset + max_blocks] for offset in range(0, end, max_blocks)]
        chunks.append(blocks[start:end])
        end = start
    chunks.reverse()
    return chunks


def _clean_markdown(value: str) -> str:
    return re.sub(r"\[([^]]+)]\([^)]+\)|[*_`]", lambda match: match.group(1) or "", value)

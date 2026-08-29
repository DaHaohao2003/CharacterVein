"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { richArtifactExportUrl } from "@/lib/api";
import { toPublicCopy } from "@/lib/public-copy";
import type { CreativeArtifact, RichContentBlock } from "@/lib/types";

const FORMAT_LABELS = {
  docx: "Word",
  html: "HTML",
  txt: "TXT",
  pdf: "PDF",
  pptx: "PPT",
} as const;

type PreviewMode = "document" | "slides";

export function RichDocumentPreview({
  artifact,
  selectedBlockId,
  selectedPageId,
  onSelect,
}: {
  artifact: CreativeArtifact;
  selectedBlockId: string;
  selectedPageId: string;
  onSelect: (pageId: string, blockId: string) => void;
}) {
  const [mode, setMode] = useState<PreviewMode>("document");
  const pages = artifact.rich_document.pages;
  const currentPage =
    pages.find((page) => page.page_id === selectedPageId) ?? pages[0];
  const selectedBlock = currentPage?.blocks.find(
    (block) => block.block_id === selectedBlockId,
  );
  const visibleBlocks =
    mode === "slides"
      ? blocksForSlidePreview(currentPage?.blocks ?? [])
      : (currentPage?.blocks ?? []);

  useEffect(() => {
    if (currentPage && currentPage.page_id !== selectedPageId) {
      onSelect(currentPage.page_id, "");
    }
  }, [currentPage, onSelect, selectedPageId]);

  if (!currentPage) return null;

  return (
    <div className={`rich-document-workspace is-${mode}`}>
      <header className="rich-document-toolbar">
        <div>
          <button
            className={mode === "document" ? "is-active" : ""}
            onClick={() => setMode("document")}
            type="button"
          >
            分页文档
          </button>
          <button
            className={mode === "slides" ? "is-active" : ""}
            onClick={() => setMode("slides")}
            type="button"
          >
            幻灯片
          </button>
        </div>
        <nav aria-label="导出当前作品">
          {artifact.rich_document.supported_formats.map((format) => (
            <a
              href={richArtifactExportUrl(
                artifact.task_id,
                artifact.id,
                format,
              )}
              key={format}
            >
              {FORMAT_LABELS[format]}
            </a>
          ))}
        </nav>
      </header>

      <div className="rich-document-layout">
        <nav className="rich-page-thumbnails" aria-label="作品页面">
          {pages.map((page, index) => (
            <button
              className={
                page.page_id === currentPage.page_id ? "is-active" : ""
              }
              key={page.page_id}
              onClick={() => onSelect(page.page_id, "")}
              type="button"
            >
              <span>{index + 1}</span>
              <strong>{toPublicCopy(page.title)}</strong>
              <small>
                {page.blocks.filter((block) => block.kind === "image").length}{" "}
                图
              </small>
            </button>
          ))}
        </nav>

        <section className="rich-page-stage">
          <article className={`rich-page-canvas layout-${currentPage.layout}`}>
            {visibleBlocks.map((block) => (
              <RichBlock
                block={block}
                key={block.block_id}
                onSelect={() => onSelect(currentPage.page_id, block.block_id)}
                selected={block.block_id === selectedBlockId}
              />
            ))}
            <footer>
              <span>{artifact.rich_document.title}</span>
              <span>
                {pages.findIndex(
                  (page) => page.page_id === currentPage.page_id,
                ) + 1}{" "}
                / {pages.length}
              </span>
            </footer>
          </article>
          {mode === "slides" &&
            visibleBlocks.length < currentPage.blocks.length && (
              <p className="rich-slide-preview-note">
                缩略预览已折叠部分长文，导出文件保留完整内容
              </p>
            )}
          <p className="rich-selection-hint">
            {selectedBlock?.kind === "image" && selectedBlock.locked
              ? "已选中真实历史字形。可以在右侧要求调整大小、位置、图注或周边文案，原始字形不会被改画。"
              : selectedBlock?.kind === "image"
                ? "已选中图片。可以在右侧要求替换图片，或调整大小、位置和图注。"
                : selectedBlockId
                  ? "已选中内容块。现在可以在右侧说“修改这里”或“把这里改短一点”。"
                  : "点击页面中的标题、正文或图片，再在右侧用语言描述修改要求。"}
          </p>
        </section>
      </div>
    </div>
  );
}

function blocksForSlidePreview(blocks: RichContentBlock[]): RichContentBlock[] {
  const result: RichContentBlock[] = [];
  const hasImage = blocks.some((block) => block.kind === "image");
  const maxTextBlocks = hasImage ? 1 : 3;
  const maxTextCharacters = hasImage ? 90 : 220;
  let textCharacters = 0;
  let textBlocks = 0;
  let imageAdded = false;

  for (const block of blocks) {
    if (block.kind === "image") {
      if (!imageAdded) {
        result.push(block);
        imageAdded = true;
      }
      continue;
    }
    if (block.kind === "heading") {
      result.push(block);
      continue;
    }
    if (textBlocks >= maxTextBlocks || textCharacters >= maxTextCharacters)
      continue;
    result.push(block);
    textCharacters += block.text.length;
    textBlocks += 1;
  }
  return result;
}

function RichBlock({
  block,
  onSelect,
  selected,
}: {
  block: RichContentBlock;
  onSelect: () => void;
  selected: boolean;
}) {
  const className = `rich-content-block is-${block.kind}${selected ? " is-selected" : ""}`;
  if (block.kind === "image" && block.image_url) {
    return (
      <button className={className} onClick={onSelect} type="button">
        <span className="rich-image-frame">
          <Image
            alt={block.alt_text || block.caption || "文化配图"}
            fill
            sizes="(max-width: 900px) 80vw, 420px"
            src={block.image_url}
            style={{ objectFit: "contain" }}
            unoptimized
          />
        </span>
        <small>{block.caption || block.alt_text}</small>
        {block.locked && <em>真实字形 · 已锁定</em>}
      </button>
    );
  }
  const content = toPublicCopy(block.text);
  return (
    <button className={className} onClick={onSelect} type="button">
      {block.kind === "heading" ? (
        block.level === 1 ? (
          <h1>{content}</h1>
        ) : (
          <h2>{content}</h2>
        )
      ) : block.kind === "list" ? (
        <ul>
          {content.split("\n").map((item, index) => (
            <li key={`${index}-${item}`}>{item}</li>
          ))}
        </ul>
      ) : block.kind === "quote" ? (
        <blockquote>{content}</blockquote>
      ) : (
        <p>{content}</p>
      )}
    </button>
  );
}

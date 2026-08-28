"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppNavigation } from "@/components/app-navigation";
import {
  activateContentVersion,
  exportCommunicationPackage,
  exportContent,
  getContentVersions,
  getTask,
  regenerateCommunicationFragment,
  regenerateContent,
  saveContent,
} from "@/lib/api";
import type {
  ContentVersion,
  GeneratedContent,
  Task,
  TaskSpec,
} from "@/lib/types";

const checkLabels: Record<string, string> = {
  target_character: "目标汉字一致",
  historical_stages: "历史阶段数量",
  interaction_count: "互动题数量",
  evidence_bound: "旧任务：陈述证据绑定",
  audit_approved: "旧任务：引用检查",
  reference_context: "已提供生成参考资料",
  audience: "受众匹配",
  duration: "时长匹配",
};

export default function ContentPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<Task | null>(null);
  const [versions, setVersions] = useState<ContentVersion[]>([]);
  const [draft, setDraft] = useState<GeneratedContent | null>(null);
  const [audience, setAudience] = useState("");
  const [duration, setDuration] = useState(4);
  const [outputType, setOutputType] =
    useState<TaskSpec["output_type"]>("interactive_lesson");
  const [interactionCount, setInteractionCount] = useState(2);
  const [mode, setMode] = useState<"full" | "body" | "interactions">("full");
  const [changeSummary, setChangeSummary] = useState("调整讲解表达");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [packageTab, setPackageTab] = useState<
    "interactive_story" | "social_cards" | "short_video_script"
  >("interactive_story");
  const [fragmentInstruction, setFragmentInstruction] = useState(
    "表达得更生动、更适合年轻用户，并保留文化信息与图片引用",
  );
  const [fragmentBusy, setFragmentBusy] = useState("");
  const [agentInput, setAgentInput] = useState("");
  const [agentMessages, setAgentMessages] = useState<
    Array<{ id: number; role: "user" | "assistant"; content: string }>
  >([]);

  async function refresh() {
    const [taskResult, versionResult] = await Promise.all([
      getTask(id),
      getContentVersions(id),
    ]);
    setTask(taskResult);
    setVersions(versionResult);
    setDraft(taskResult.generated_content);
    setAudience(taskResult.spec.audience);
    setDuration(taskResult.spec.duration_minutes);
    setOutputType(taskResult.spec.output_type);
    setInteractionCount(taskResult.spec.interaction_count);
  }

  useEffect(() => {
    Promise.all([getTask(id), getContentVersions(id)])
      .then(([taskResult, versionResult]) => {
        setTask(taskResult);
        setVersions(versionResult);
        setDraft(taskResult.generated_content);
        setAudience(taskResult.spec.audience);
        setDuration(taskResult.spec.duration_minutes);
        setOutputType(taskResult.spec.output_type);
        setInteractionCount(taskResult.spec.interaction_count);
      })
      .catch((reason: Error) => setError(reason.message));
  }, [id]);

  async function runRegeneration() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const version = await regenerateContent(id, {
        audience,
        duration_minutes: duration,
        output_type: outputType,
        interaction_count: interactionCount,
        mode,
      });
      await refresh();
      setNotice(`已复用参考上下文并生成 v${version.version}，没有重新检索。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "局部再生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!task || !draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const version = await saveContent(
        id,
        task.current_content_version,
        draft,
        changeSummary,
      );
      await refresh();
      setNotice(`编辑已保存为 v${version.version}，旧版本仍然保留。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function restoreVersion(version: number) {
    setBusy(true);
    setError("");
    try {
      const restored = await activateContentVersion(id, version);
      await refresh();
      setNotice(`已从 v${version} 恢复并创建 v${restored.version}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复失败");
    } finally {
      setBusy(false);
    }
  }

  async function download(format: "markdown" | "html" | "json") {
    setError("");
    try {
      const result = await exportContent(id, format);
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败");
    }
  }

  async function downloadPackage(format: "markdown" | "html" | "json") {
    setError("");
    try {
      const result = await exportCommunicationPackage(id, format);
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(`传播成品包已导出为 ${format.toUpperCase()}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "传播包导出失败");
    }
  }

  async function copyMarkdown() {
    try {
      const result = await exportContent(id, "markdown");
      await navigator.clipboard.writeText(await result.blob.text());
      setNotice("Markdown 已复制。 ");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "复制失败");
    }
  }

  async function rewriteFragment(
    assetType: "interactive_story" | "social_cards" | "short_video_script",
    targetIndex: number,
    instructionOverride?: string,
  ) {
    const effectiveInstruction =
      instructionOverride?.trim() || fragmentInstruction.trim();
    if (effectiveInstruction.length < 2) {
      setError("请先填写至少两个字的改写要求");
      return;
    }
    const key = `${assetType}-${targetIndex}`;
    setFragmentBusy(key);
    setError("");
    setNotice("");
    try {
      const version = await regenerateCommunicationFragment(
        id,
        assetType,
        targetIndex,
        effectiveInstruction,
      );
      await refresh();
      setNotice(
        `只改写了第 ${targetIndex} 个片段，${assetType} 已保存为 v${version.version}；其他片段和检索上下文未变。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "片段改写失败");
    } finally {
      setFragmentBusy("");
    }
  }

  async function handleAgentInstruction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const instruction = agentInput.trim();
    if (!instruction || fragmentBusy) return;
    const now = Date.now();
    setAgentMessages((current) => [
      ...current,
      { id: now, role: "user", content: instruction },
    ]);
    setAgentInput("");

    const indexMatch = instruction.match(/第\s*(\d+)\s*(段|张|镜|个)/);
    const targetIndex = indexMatch ? Number(indexMatch[1]) : 0;
    const assetType = /卡片|第\s*\d+\s*张/.test(instruction)
      ? "social_cards"
      : /视频|分镜|第\s*\d+\s*镜/.test(instruction)
        ? "short_video_script"
        : /长页|段落|第\s*\d+\s*段/.test(instruction)
          ? "interactive_story"
          : packageTab;

    if (!targetIndex) {
      setFragmentInstruction(instruction);
      setAgentMessages((current) => [
        ...current,
        {
          id: now + 1,
          role: "assistant",
          content:
            "我已经理解改写方向。请再告诉我要改第几段、哪张卡片或第几镜，例如“把第 2 张卡片写得更年轻”。",
        },
      ]);
      return;
    }

    setFragmentInstruction(instruction);
    setPackageTab(assetType);
    setAgentMessages((current) => [
      ...current,
      {
        id: now + 1,
        role: "assistant",
        content: `我会只改写第 ${targetIndex} 项，并保留其他片段和现有参考上下文。`,
      },
    ]);
    await rewriteFragment(assetType, targetIndex, instruction);
  }

  if (!task || !draft) {
    return <main className="loading">{error || "正在载入文化传播内容…"}</main>;
  }

  const storyAsset = task.communication_assets.interactive_story;
  const cardsAsset = task.communication_assets.social_cards;
  const videoAsset = task.communication_assets.short_video_script;
  const imageUrlById = new Map(
    (task.evolution_package?.glyph_stages ?? [])
      .filter((stage) => stage.image_id && stage.image_url)
      .map((stage) => [stage.image_id as string, stage.image_url as string]),
  );

  function VisualHookImage({ imageId }: { imageId: string | null }) {
    const source = imageId ? imageUrlById.get(imageId) : undefined;
    if (!source) return null;
    return (
      <span className="package-glyph">
        <Image
          alt="传播成品使用的历史字形"
          fill
          sizes="120px"
          src={source}
          style={{ objectFit: "contain" }}
          unoptimized
        />
      </span>
    );
  }

  return (
    <main className="agent-app-shell content-agent-shell">
      <AppNavigation
        active="content"
        character={task.spec.target_characters.join("")}
        status={task.status}
        taskId={id}
      />
      <section className="agent-canvas content-agent-canvas">
        <div className="content-shell content-shell--embedded">
          <header className="content-header no-print">
            <div>
              <p className="eyebrow">
                文化传播工作室
                {storyAsset && cardsAsset && videoAsset
                  ? ` · 长页 v${storyAsset.version} / 卡片 v${cardsAsset.version} / 视频 v${videoAsset.version}`
                  : ` · 兼容内容 v${task.current_content_version}`}
              </p>
              <h1>{draft.title}</h1>
              <p>
                检索与上传资料保持不变；这里的操作只重新调用模型调整传播表达。
              </p>
            </div>
            <Link
              className="button-link button-link--secondary"
              href={`/tasks/${id}/workspace`}
            >
              返回工作台
            </Link>
          </header>

          {error && <p className="error no-print">{error}</p>}
          {notice && <p className="notice no-print">{notice}</p>}

          {task.cultural_motif && storyAsset && cardsAsset && videoAsset && (
            <section className="communication-package">
              <header className="package-motif">
                <p className="eyebrow">CULTURAL MOTIF · 统一文化母题</p>
                <h2>{task.cultural_motif.title}</h2>
                <p className="package-core-message">
                  {task.cultural_motif.core_message}
                </p>
                <p>{task.cultural_motif.audience_promise}</p>
                <div className="motif-beats">
                  {task.cultural_motif.story_beats.map((beat, index) => (
                    <span key={beat}>
                      {index + 1}. {beat}
                    </span>
                  ))}
                </div>
              </header>

              <nav aria-label="传播成品类型" className="package-tabs">
                <button
                  aria-pressed={packageTab === "interactive_story"}
                  onClick={() => setPackageTab("interactive_story")}
                >
                  互动文化长页
                </button>
                <button
                  aria-pressed={packageTab === "social_cards"}
                  onClick={() => setPackageTab("social_cards")}
                >
                  五张图文卡片
                </button>
                <button
                  aria-pressed={packageTab === "short_video_script"}
                  onClick={() => setPackageTab("short_video_script")}
                >
                  60 秒短视频
                </button>
              </nav>

              <div className="package-export-actions no-print">
                <strong>整套交付</strong>
                <button onClick={() => downloadPackage("markdown")}>
                  导出 Markdown
                </button>
                <button onClick={() => downloadPackage("html")}>
                  导出 HTML
                </button>
                <button onClick={() => downloadPackage("json")}>
                  导出 JSON
                </button>
              </div>

              {task.artifact_evaluation && (
                <div className="artifact-evaluation-strip">
                  <strong>
                    {task.artifact_evaluation.passed
                      ? "三类成品已通过独立验收"
                      : "成品验收存在未满足项"}
                  </strong>
                  {Object.entries(task.artifact_evaluation.assets).map(
                    ([assetType, evaluation]) =>
                      evaluation && (
                        <span
                          className={evaluation.passed ? "is-pass" : "is-fail"}
                          key={assetType}
                        >
                          {evaluation.passed ? "✓" : "!"} {assetType} · v
                          {task.communication_assets[
                            assetType as keyof typeof task.communication_assets
                          ]?.version ?? 1}
                        </span>
                      ),
                  )}
                </div>
              )}

              <div className="fragment-rewrite-toolbar no-print">
                <label>
                  <strong>片段改写要求</strong>
                  <input
                    maxLength={500}
                    value={fragmentInstruction}
                    onChange={(event) =>
                      setFragmentInstruction(event.target.value)
                    }
                  />
                </label>
                <p>
                  点击任一段落、卡片或分镜下方的“只改写这一项”，系统不会重新检索，也不会改动其他片段。
                </p>
              </div>

              {packageTab === "interactive_story" &&
                storyAsset.asset_type === "interactive_story" && (
                  <article className="package-story">
                    <header>
                      <p className="asset-kicker">INTERACTIVE STORY</p>
                      <h2>{storyAsset.content.title}</h2>
                      <p>{storyAsset.content.lede}</p>
                    </header>
                    <div className="story-section-list">
                      {storyAsset.content.sections.map((section, index) => (
                        <section
                          className="story-section"
                          key={section.section_id}
                        >
                          <span className="story-index">{index + 1}</span>
                          <VisualHookImage imageId={section.visual_hook_id} />
                          <div>
                            <h3>{section.title}</h3>
                            <p>{section.narrative}</p>
                            {section.interaction_prompt && (
                              <blockquote>
                                {section.interaction_prompt}
                              </blockquote>
                            )}
                            <button
                              className="fragment-rewrite-button no-print"
                              disabled={Boolean(fragmentBusy)}
                              onClick={() =>
                                rewriteFragment("interactive_story", index + 1)
                              }
                            >
                              {fragmentBusy === `interactive_story-${index + 1}`
                                ? "正在改写…"
                                : "只改写这一段"}
                            </button>
                          </div>
                        </section>
                      ))}
                    </div>
                    <p className="asset-closing">
                      {storyAsset.content.closing}
                    </p>
                  </article>
                )}

              {packageTab === "social_cards" &&
                cardsAsset.asset_type === "social_cards" && (
                  <article className="package-cards">
                    <header>
                      <p className="asset-kicker">SOCIAL CARDS · 5</p>
                      <h2>{cardsAsset.content.title}</h2>
                    </header>
                    <div className="social-card-grid">
                      {cardsAsset.content.cards.map((card) => (
                        <section className="social-card" key={card.index}>
                          <div className="social-card-number">
                            0{card.index}
                          </div>
                          <VisualHookImage imageId={card.visual_hook_id} />
                          <h3>{card.headline}</h3>
                          <p>{card.body}</p>
                          <small>画面：{card.visual_direction}</small>
                          <button
                            className="fragment-rewrite-button no-print"
                            disabled={Boolean(fragmentBusy)}
                            onClick={() =>
                              rewriteFragment("social_cards", card.index)
                            }
                          >
                            {fragmentBusy === `social_cards-${card.index}`
                              ? "正在改写…"
                              : "只改写这一张"}
                          </button>
                        </section>
                      ))}
                    </div>
                    <p className="asset-closing">
                      发布文案：{cardsAsset.content.posting_caption}
                    </p>
                  </article>
                )}

              {packageTab === "short_video_script" &&
                videoAsset.asset_type === "short_video_script" && (
                  <article className="package-video">
                    <header>
                      <p className="asset-kicker">SHORT VIDEO · 60 SECONDS</p>
                      <h2>{videoAsset.content.title}</h2>
                      <p>{videoAsset.content.opening_hook}</p>
                    </header>
                    <ol className="video-timeline">
                      {videoAsset.content.scenes.map((scene, index) => (
                        <li key={`${scene.start_second}-${scene.end_second}`}>
                          <time>
                            {scene.start_second}s—{scene.end_second}s
                          </time>
                          <VisualHookImage imageId={scene.visual_hook_id} />
                          <div>
                            <strong>{scene.subtitle}</strong>
                            <p>画面：{scene.visual}</p>
                            <p>旁白：{scene.narration}</p>
                            <button
                              className="fragment-rewrite-button no-print"
                              disabled={Boolean(fragmentBusy)}
                              onClick={() =>
                                rewriteFragment("short_video_script", index + 1)
                              }
                            >
                              {fragmentBusy ===
                              `short_video_script-${index + 1}`
                                ? "正在改写…"
                                : "只改写这一镜"}
                            </button>
                          </div>
                        </li>
                      ))}
                    </ol>
                    <p className="asset-closing">
                      结尾互动：{videoAsset.content.closing_cta}
                    </p>
                  </article>
                )}
            </section>
          )}

          <details className="legacy-editor-disclosure" open={!storyAsset}>
            <summary>
              <strong>旧版单篇内容编辑器</strong>
              <span>
                兼容历史任务与单篇讲解导出，新的跨媒介传播包不会受这里的修改影响。
              </span>
            </summary>
            <div className="content-editor-grid">
              <aside className="panel content-controls no-print">
                <h2>传播设置</h2>
                <label>
                  目标受众
                  <input
                    value={audience}
                    onChange={(event) => setAudience(event.target.value)}
                  />
                </label>
                <label>
                  时长（分钟）
                  <input
                    min={1}
                    max={30}
                    type="number"
                    value={duration}
                    onChange={(event) =>
                      setDuration(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  输出形式
                  <select
                    value={outputType}
                    onChange={(event) =>
                      setOutputType(
                        event.target.value as TaskSpec["output_type"],
                      )
                    }
                  >
                    <option value="interactive_lesson">互动讲解</option>
                    <option value="culture_card">文化卡</option>
                    <option value="article_outline">文章提纲</option>
                  </select>
                </label>
                <label>
                  互动题数量
                  <input
                    min={0}
                    max={10}
                    type="number"
                    value={interactionCount}
                    onChange={(event) =>
                      setInteractionCount(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  再生成范围
                  <select
                    value={mode}
                    onChange={(event) =>
                      setMode(event.target.value as typeof mode)
                    }
                  >
                    <option value="full">完整传播版本</option>
                    <option value="body">只重建正文</option>
                    <option value="interactions">只重建互动题</option>
                  </select>
                </label>
                <button disabled={busy} onClick={runRegeneration}>
                  {busy ? "处理中…" : "局部再生成"}
                </button>
                <p className="fact-lock">
                  🔒 复用相同的网络与用户资料上下文，不重新执行检索。
                </p>

                <h2>版本记录</h2>
                <ol className="version-list">
                  {versions.map((version) => (
                    <li
                      className={
                        version.version === task.current_content_version
                          ? "is-current"
                          : ""
                      }
                      key={version.version}
                    >
                      <div>
                        <strong>v{version.version}</strong> · {version.origin}
                      </div>
                      <small>
                        {version.change_summary}
                        <br />
                        参考上下文 {version.evolution_hash.slice(0, 10)}…
                      </small>
                      {version.version !== task.current_content_version && (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => restoreVersion(version.version)}
                        >
                          恢复此版本
                        </button>
                      )}
                    </li>
                  ))}
                </ol>
              </aside>

              <section className="panel content-draft no-print">
                <h2>内容编辑</h2>
                <label>
                  标题
                  <input
                    value={draft.title}
                    onChange={(event) =>
                      setDraft({ ...draft, title: event.target.value })
                    }
                  />
                </label>
                <label>
                  正文（Markdown）
                  <textarea
                    rows={24}
                    value={draft.body_markdown}
                    onChange={(event) =>
                      setDraft({ ...draft, body_markdown: event.target.value })
                    }
                  />
                </label>
                <label>
                  互动题（每行一题）
                  <textarea
                    rows={6}
                    value={draft.interaction_questions.join("\n")}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        interaction_questions: event.target.value
                          .split("\n")
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <label>
                  修改说明
                  <input
                    value={changeSummary}
                    onChange={(event) => setChangeSummary(event.target.value)}
                  />
                </label>
                <button disabled={busy} onClick={saveDraft}>
                  保存为新版本
                </button>
              </section>

              <aside className="panel content-preview-panel">
                <div className="preview-toolbar no-print">
                  <h2>实时预览</h2>
                  <div>
                    <button className="text-button" onClick={copyMarkdown}>
                      复制 Markdown
                    </button>
                    <button
                      className="text-button"
                      onClick={() => download("html")}
                    >
                      HTML
                    </button>
                    <button
                      className="text-button"
                      onClick={() => download("json")}
                    >
                      JSON
                    </button>
                    <button
                      className="text-button"
                      onClick={() => window.print()}
                    >
                      打印 / PDF
                    </button>
                  </div>
                </div>
                <article className="print-content">
                  <h1>{draft.title}</h1>
                  <p className="preview-meta">
                    面向 {audience} · {duration} 分钟
                  </p>
                  <pre>{draft.body_markdown}</pre>
                  <h2>互动题</h2>
                  <ol>
                    {draft.interaction_questions.map((question) => (
                      <li key={question}>{question}</li>
                    ))}
                  </ol>
                </article>
                {task.constraint_result && (
                  <section className="constraint-list no-print">
                    <h2>约束检查</h2>
                    {Object.entries(task.constraint_result.checks).map(
                      ([key, passed]) => (
                        <p
                          className={
                            passed ? "constraint-pass" : "constraint-fail"
                          }
                          key={key}
                        >
                          {passed ? "✓" : "!"} {checkLabels[key] ?? key}
                        </p>
                      ),
                    )}
                  </section>
                )}
              </aside>
            </div>
          </details>
        </div>
      </section>

      <aside
        className="agent-chat-panel content-agent-panel no-print"
        aria-label="内容改写智能体"
      >
        <header className="agent-chat-header">
          <div className="agent-avatar">脉</div>
          <div>
            <strong>内容改写助手</strong>
            <small>
              <span
                className={
                  fragmentBusy
                    ? "status-pulse"
                    : "status-dot status-dot--online"
                }
              />{" "}
              {fragmentBusy ? "正在改写" : "保持参考上下文"}
            </small>
          </div>
          <span className="agent-model-label">EDITOR AGENT</span>
        </header>
        <div className="agent-conversation">
          <article className="chat-message chat-message--assistant">
            <span className="chat-message-avatar">脉</span>
            <div>
              <strong>传播成品已经准备好</strong>
              <p>
                你可以直接告诉我要改哪一段、哪张卡片或哪一镜。只会重新生成指定片段，不会重新检索，也不会改动其他内容。
              </p>
            </div>
          </article>
          <article className="agent-reasoning-card">
            <header>
              <span>当前上下文</span>
              <small>{packageTab}</small>
            </header>
            <strong>{task.cultural_motif?.title ?? draft.title}</strong>
            <p>
              受众：{task.spec.audience} · 当前查看：
              {packageTab === "interactive_story"
                ? "互动文化长页"
                : packageTab === "social_cards"
                  ? "五张图文卡片"
                  : "60 秒短视频"}
            </p>
          </article>
          <article className="agent-suggestion-card">
            <span>试试这样说</span>
            <p>“把第 2 张卡片写得更年轻一些，开头更有悬念。”</p>
          </article>
          {agentMessages.map((message) => (
            <article
              className={`chat-message chat-message--${message.role}`}
              key={message.id}
            >
              {message.role === "assistant" && (
                <span className="chat-message-avatar">脉</span>
              )}
              <div>
                <p>{message.content}</p>
              </div>
            </article>
          ))}
          {fragmentBusy && (
            <article className="chat-message chat-message--assistant is-working">
              <span className="chat-message-avatar">脉</span>
              <div>
                <strong>正在局部改写</strong>
                <p>保留文化母题、图片引用和其他片段，只更新你指定的内容。</p>
                <span className="thinking-dots">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </article>
          )}
          {notice && (
            <article className="chat-message chat-message--tool">
              <span className="chat-message-avatar">✓</span>
              <div>
                <strong>操作完成</strong>
                <p>{notice}</p>
              </div>
            </article>
          )}
          {error && <p className="agent-chat-error">{error}</p>}
        </div>
        <form
          className="agent-composer agent-composer--compact"
          onSubmit={handleAgentInstruction}
        >
          <label className="sr-only" htmlFor="content-agent-input">
            告诉智能体如何修改内容
          </label>
          <textarea
            id="content-agent-input"
            onChange={(event) => setAgentInput(event.target.value)}
            placeholder="例如：把第 3 张卡片改得更有画面感…"
            rows={4}
            value={agentInput}
          />
          <div className="composer-toolbar">
            <span className="composer-hint">请说明类型、序号和改写方向</span>
            <button
              className="composer-send"
              disabled={Boolean(fragmentBusy) || agentInput.trim().length < 2}
              type="submit"
            >
              {fragmentBusy ? "…" : "↑"}
              <span className="sr-only">发送改写要求</span>
            </button>
          </div>
        </form>
      </aside>
    </main>
  );
}

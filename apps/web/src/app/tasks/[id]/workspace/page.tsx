"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  acknowledgeLimitations,
  exportUrl,
  getEvents,
  getTask,
  resumeTask,
  runTask,
  searchGlyphImages,
} from "@/lib/api";
import type {
  GlyphImageSearchResult,
  GlyphStage,
  Task,
  WorkflowEvent,
} from "@/lib/types";

const SCRIPT_CODES: Record<string, string> = {
  甲骨文: "J",
  金文: "B",
  战国文字: "G",
  篆书: "S",
  隶书: "L",
  楷书: "K",
  草书: "C",
};

function scriptCodeOf(stage: GlyphStage): string {
  return (
    stage.script_code ??
    stage.image_id?.match(/\/([JBGSLKC])\//)?.[1] ??
    SCRIPT_CODES[stage.script_type] ??
    ""
  );
}

function withoutExtension(value: string): string {
  return value.replace(/\.[^.]+$/, "");
}

function ContainedGlyphImage({
  alt,
  sizes,
  src,
}: {
  alt: string;
  sizes: string;
  src: string;
}) {
  return (
    <span className="contained-glyph-image">
      <Image
        alt={alt}
        fill
        sizes={sizes}
        src={src}
        style={{ objectFit: "contain", objectPosition: "center" }}
        unoptimized
      />
    </span>
  );
}

function StageGlyph({
  stage,
  large = false,
}: {
  stage: GlyphStage;
  large?: boolean;
}) {
  if (stage.availability !== "available" || !stage.image_url) {
    return (
      <span className={large ? "glyph-gap glyph-gap--large" : "glyph-gap"}>
        <strong>暂无样本</strong>
        <small>JieZi 数据缺口</small>
      </span>
    );
  }
  const size = large ? 112 : 84;
  return (
    <Image
      alt={`${stage.character}字${stage.script_type}代表字形${stage.image_id ? `（${stage.image_id}）` : ""}`}
      height={size}
      src={stage.image_url}
      unoptimized
      width={size}
    />
  );
}

function StageButton({
  stage,
  active,
  onSelect,
}: {
  stage: GlyphStage;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      aria-label={`查看${stage.period}${stage.script_type}${stage.availability === "dataset_gap" ? "资料缺口" : `代表字形${stage.image_id ? ` ${stage.image_id}` : ""}`}`}
      aria-pressed={active}
      className={active ? "timeline-step is-active" : "timeline-step"}
      onClick={onSelect}
    >
      <span className="timeline-glyph">
        <StageGlyph stage={stage} />
      </span>
      <small>
        {stage.period}
        <br />
        {stage.script_type}
      </small>
      <em className="glyph-id">{stage.image_id ?? "DATASET GAP"}</em>
    </button>
  );
}

function GlyphVariantExplorer({
  stage,
  stages,
}: {
  stage: GlyphStage;
  stages: GlyphStage[];
}) {
  const [galleryState, setGalleryState] = useState<{
    key: string;
    results: GlyphImageSearchResult[];
    error: string;
  }>({ key: "", results: [], error: "" });
  const [selectedVariantId, setSelectedVariantId] = useState("");
  const [compareStageId, setCompareStageId] = useState("");
  const [expandedGalleryKey, setExpandedGalleryKey] = useState("");
  const scriptCode = scriptCodeOf(stage);
  const galleryKey = `${stage.character}:${scriptCode}`;
  const galleryReady = galleryState.key === galleryKey;
  const variants = galleryReady ? galleryState.results : [];
  const galleryExpanded = expandedGalleryKey === galleryKey;
  const visibleVariants = galleryExpanded ? variants : variants.slice(0, 6);
  const galleryError = galleryReady ? galleryState.error : "";
  const loading =
    Boolean(scriptCode) && stage.availability === "available" && !galleryReady;
  const availableStages = stages.filter(
    (item) => item.availability === "available" && item.image_url,
  );

  useEffect(() => {
    if (!scriptCode || stage.availability !== "available") return;
    let active = true;
    searchGlyphImages({
      character: stage.character,
      scriptCode,
      scriptType: stage.script_type,
      limit: 200,
    })
      .then((results) => {
        if (!active) return;
        setGalleryState({ key: galleryKey, results, error: "" });
        const representative = results.find(
          (item) =>
            item.metadata.is_representative ||
            (stage.image_id &&
              withoutExtension(item.id) === withoutExtension(stage.image_id)),
        );
        setSelectedVariantId(representative?.id ?? results[0]?.id ?? "");
      })
      .catch((reason: Error) => {
        if (!active) return;
        setGalleryState({
          key: galleryKey,
          results: [],
          error: reason.message,
        });
      });
    return () => {
      active = false;
    };
  }, [
    galleryKey,
    scriptCode,
    stage.availability,
    stage.character,
    stage.image_id,
    stage.script_type,
  ]);

  const selectedVariant =
    variants.find((item) => item.id === selectedVariantId) ?? variants[0];
  const selectedIndex = availableStages.findIndex(
    (item) => item.stage_id === stage.stage_id,
  );
  const defaultComparison =
    availableStages[selectedIndex - 1] ??
    availableStages[selectedIndex + 1] ??
    availableStages.find((item) => item.stage_id !== stage.stage_id);
  const effectiveCompareStageId = availableStages.some(
    (item) =>
      item.stage_id === compareStageId && item.stage_id !== stage.stage_id,
  )
    ? compareStageId
    : (defaultComparison?.stage_id ?? "");
  const compareStage = availableStages.find(
    (item) => item.stage_id === effectiveCompareStageId,
  );

  return (
    <section
      className="variant-explorer"
      aria-labelledby="variant-gallery-title"
    >
      <div className="variant-heading">
        <div>
          <p className="eyebrow">JIEZI GLYPH CATALOG</p>
          <h3 id="variant-gallery-title">{stage.script_type}字形图库</h3>
        </div>
        <span className="variant-count">
          {loading ? "检索中…" : `${variants.length} 张候选`}
        </span>
      </div>
      <p className="variant-disclaimer">
        同一文体可能有多个写法。代表字形用于时间线展示，其余图片作为异体样本；并列不表示它们彼此直接演变。
        图片按原图完整缩放；若字形仍贴边或缺笔，属于数据源原图裁切，系统不补绘。
      </p>
      {variants.length > 6 && (
        <div className="variant-actions">
          <span>
            {galleryExpanded
              ? `正在浏览全部 ${variants.length} 张`
              : "先展示代表字形与前 5 张异体"}
          </span>
          <button
            aria-expanded={galleryExpanded}
            className="text-button"
            onClick={() =>
              setExpandedGalleryKey(galleryExpanded ? "" : galleryKey)
            }
            type="button"
          >
            {galleryExpanded ? "收起图库" : `查看全部 ${variants.length} 张`}
          </button>
        </div>
      )}
      {galleryError && (
        <p className="error">字形图库加载失败：{galleryError}</p>
      )}
      {!loading && !galleryError && variants.length === 0 && (
        <p className="empty">该文体暂无可检索的候选图片。</p>
      )}
      {variants.length > 0 && (
        <div
          className="variant-grid"
          aria-label={`${stage.script_type}候选字形`}
        >
          {visibleVariants.map((variant) => {
            const representative = Boolean(variant.metadata.is_representative);
            return (
              <button
                aria-label={`查看${stage.script_type}${representative ? "代表字形" : `异体 ${variant.metadata.variant_index ?? ""}`} ${variant.id}`}
                aria-pressed={variant.id === selectedVariant?.id}
                className={
                  variant.id === selectedVariant?.id
                    ? "variant-card is-active"
                    : "variant-card"
                }
                key={variant.id}
                onClick={() => setSelectedVariantId(variant.id)}
              >
                <span className="variant-image">
                  <ContainedGlyphImage
                    alt={`${stage.character}字${stage.script_type}${representative ? "代表字形" : "异体字形"}`}
                    sizes="8rem"
                    src={variant.content_url}
                  />
                </span>
                <strong>{representative ? "代表字形" : "异体样本"}</strong>
                <small>{withoutExtension(variant.id).split("/").at(-1)}</small>
              </button>
            );
          })}
        </div>
      )}

      {selectedVariant && (
        <div className="variant-preview">
          <div className="variant-preview-image">
            <ContainedGlyphImage
              alt={`${stage.character}字${stage.script_type}放大字形 ${selectedVariant.id}`}
              sizes="11rem"
              src={selectedVariant.content_url}
            />
          </div>
          <div>
            <p className="stage-meta">当前查看 · {stage.script_type}</p>
            <h3>
              {selectedVariant.metadata.is_representative
                ? "时间线代表字形"
                : "同文体异体样本"}
            </h3>
            <dl className="variant-facts">
              <dt>图片编号</dt>
              <dd>{selectedVariant.id}</dd>
              <dt>原始路径</dt>
              <dd>{selectedVariant.source_path}</dd>
              <dt>图库序号</dt>
              <dd>
                第{" "}
                {variants.findIndex((item) => item.id === selectedVariant.id) +
                  1}{" "}
                / {variants.length}
              </dd>
            </dl>
          </div>
        </div>
      )}

      {selectedVariant && compareStage && (
        <section
          className="glyph-comparison"
          aria-labelledby="glyph-comparison-title"
        >
          <div className="comparison-heading">
            <div>
              <p className="eyebrow">OBSERVATION VIEW</p>
              <h3 id="glyph-comparison-title">两阶段观察对比</h3>
            </div>
            <label>
              对比阶段
              <select
                onChange={(event) => setCompareStageId(event.target.value)}
                value={effectiveCompareStageId}
              >
                {availableStages
                  .filter((item) => item.stage_id !== stage.stage_id)
                  .map((item) => (
                    <option key={item.stage_id} value={item.stage_id}>
                      {item.script_type} ·{" "}
                      {item.historical_period ?? item.period}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="comparison-cards">
            <article>
              <span className="comparison-image">
                <ContainedGlyphImage
                  alt={`${stage.script_type}当前所选字形`}
                  sizes="10rem"
                  src={selectedVariant.content_url}
                />
              </span>
              <strong>{stage.script_type}</strong>
              <small>{selectedVariant.id}</small>
            </article>
            <span className="comparison-mark" aria-hidden="true">
              ⇄
            </span>
            <article>
              <span className="comparison-image">
                {compareStage.availability === "available" &&
                compareStage.image_url ? (
                  <ContainedGlyphImage
                    alt={`${compareStage.character}字${compareStage.script_type}代表字形${compareStage.image_id ? `（${compareStage.image_id}）` : ""}`}
                    sizes="10rem"
                    src={compareStage.image_url}
                  />
                ) : (
                  <StageGlyph large stage={compareStage} />
                )}
              </span>
              <strong>{compareStage.script_type}</strong>
              <small>{compareStage.image_id}</small>
            </article>
          </div>
          <div className="observation-guide">
            <strong>观察提示</strong>
            <ul>
              <li>比较外部轮廓、构件位置、笔画连接与疏密。</li>
              <li>
                这里只记录图像上可见的不同，不据此推断精确年代或直接传承关系。
              </li>
              <li>左侧可切换异体样本，右侧始终采用另一阶段的代表字形。</li>
            </ul>
          </div>
        </section>
      )}
    </section>
  );
}

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [acknowledging, setAcknowledging] = useState(false);
  const autoRunStarted = useRef(false);
  const [selectedStageId, setSelectedStageId] = useState("");
  const [evolutionView, setEvolutionView] = useState<
    "shape" | "meaning" | "culture"
  >("shape");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function refresh() {
      const [taskResult, eventResult] = await Promise.all([
        getTask(id),
        getEvents(id),
      ]);
      if (cancelled) return;
      setTask(taskResult);
      setEvents(eventResult);
      if (taskResult.status !== "running" && timer) {
        clearInterval(timer);
        timer = undefined;
        setRunning(false);
      }
      const shouldAutoRun =
        taskResult.status === "confirmed" &&
        new URLSearchParams(window.location.search).get("autorun") === "1" &&
        !autoRunStarted.current;
      if (shouldAutoRun) {
        autoRunStarted.current = true;
        void execute(false);
      } else if (taskResult.status === "running" && !timer) {
        setRunning(true);
        timer = setInterval(() => void refresh().catch(() => undefined), 1000);
      }
    }

    void refresh().catch((reason: Error) => setError(reason.message));
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
    // execute deliberately reads the stable route id; including it would recreate polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function execute(resume = false) {
    setRunning(true);
    setError("");
    try {
      let latest = await (resume ? resumeTask(id) : runTask(id));
      setTask(latest);
      while (latest.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 900));
        const [taskResult, eventResult] = await Promise.all([
          getTask(id),
          getEvents(id),
        ]);
        latest = taskResult;
        setTask(taskResult);
        setEvents(eventResult);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "执行失败");
    } finally {
      setRunning(false);
    }
  }

  async function confirmEvidenceBoundary() {
    setAcknowledging(true);
    setError("");
    try {
      setTask(await acknowledgeLimitations(id));
      setEvents(await getEvents(id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
    } finally {
      setAcknowledging(false);
    }
  }

  if (!task)
    return <main className="loading">{error || "正在载入工作台…"}</main>;

  const evolution = task.evolution_package;
  const content = task.generated_content;
  const mainlineStages =
    evolution?.glyph_stages.filter(
      (stage) => stage.lineage_role !== "branch",
    ) ?? [];
  const branchStages =
    evolution?.glyph_stages.filter(
      (stage) => stage.lineage_role === "branch",
    ) ?? [];
  const selectedStage =
    evolution?.glyph_stages.find(
      (stage) => stage.stage_id === selectedStageId,
    ) ?? mainlineStages.find((stage) => stage.availability === "available");
  const availableMainlineCount = mainlineStages.filter(
    (stage) => stage.availability === "available",
  ).length;
  const evidenceById = new Map(
    evolution?.evidence.map((item) => [item.evidence_id, item]) ?? [],
  );
  const sourceById = new Map(
    evolution?.sources.map((item) => [item.source_id, item]) ?? [],
  );
  const selectedStageSource = selectedStage
    ? sourceById.get(selectedStage.source_id)
    : undefined;

  return (
    <main className="workspace-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">智能体工作台 · {task.status}</p>
          <h1>“{task.spec.target_characters.join("")}”字演化任务</h1>
        </div>
        {task.status === "confirmed" && (
          <button disabled={running} onClick={() => execute(false)}>
            {running ? "执行中…" : "开始执行"}
          </button>
        )}
        {(task.status === "failed" || task.status === "running") && (
          <button disabled={running} onClick={() => execute(true)}>
            {running ? "恢复中…" : "从最近检查点恢复"}
          </button>
        )}
        {content && (
          <Link className="button-link" href={`/tasks/${id}/content`}>
            编辑传播内容
          </Link>
        )}
        {content && (
          <a
            className="button-link button-link--secondary"
            href={exportUrl(id)}
          >
            导出 Markdown
          </a>
        )}
      </header>
      {error && <p className="error">{error}</p>}
      {task.error_message && <p className="error">{task.error_message}</p>}
      {task.requires_user_confirmation && (
        <section className="confirmation-banner" role="alert">
          <div>
            <strong>需要确认资料边界</strong>
            <p>
              两次定向检索后仍有陈述缺少直接证据。系统已隐藏这些陈述，不会把推测写成事实。
            </p>
          </div>
          <button
            disabled={acknowledging}
            onClick={() => void confirmEvidenceBoundary()}
          >
            {acknowledging ? "确认中…" : "接受边界并保留降级结果"}
          </button>
        </section>
      )}

      <div className="workspace-grid">
        <aside className="panel">
          <h2>任务与执行</h2>
          <dl className="task-facts">
            <dt>受众</dt>
            <dd>{task.spec.audience}</dd>
            <dt>时长</dt>
            <dd>{task.spec.duration_minutes} 分钟</dd>
            <dt>阶段</dt>
            <dd>
              主干 {availableMainlineCount} 个可用 · 要求至少{" "}
              {task.spec.required_stages} 个
            </dd>
          </dl>
          {task.plan && (
            <>
              <h3>Agent 计划</h3>
              <ol className="plan-list">
                {task.plan.map((step) => (
                  <li
                    className={`plan-step plan-step--${step.status}`}
                    key={step.id}
                  >
                    <span>{step.status}</span>
                    <strong>{step.title}</strong>
                    <small>{step.agent}</small>
                    {step.summary && <p>{step.summary}</p>}
                    {step.tool_names.length > 0 && (
                      <small>工具：{step.tool_names.join(" · ")}</small>
                    )}
                    <details>
                      <summary>验收与失败动作</summary>
                      <small>完成标准：{step.completion_criteria}</small>
                      <small>失败动作：{step.failure_action}</small>
                      {step.depends_on.length > 0 && (
                        <small>依赖：{step.depends_on.join(" → ")}</small>
                      )}
                    </details>
                  </li>
                ))}
              </ol>
            </>
          )}
          <h3>运行记录</h3>
          <ol className="event-list">
            {events
              .slice(-30)
              .reverse()
              .map((event) => (
                <li key={event.id}>
                  <span>{event.status}</span>
                  {event.summary}
                </li>
              ))}
          </ol>
          {task.tool_calls.length > 0 && (
            <div className="tool-trace">
              <h3>工具调用轨迹</h3>
              {task.tool_calls
                .slice(-14)
                .reverse()
                .map((call) => (
                  <article key={call.tool_call_id}>
                    <header>
                      <code>{call.tool_name}</code>
                      <span>{call.status}</span>
                    </header>
                    <p>{call.input_summary}</p>
                    <small>
                      {call.result_summary} · {call.duration_ms.toFixed(0)} ms ·
                      第 {call.attempt} 次
                    </small>
                  </article>
                ))}
            </div>
          )}
          {task.retrieval_summary && (
            <div className="retrieval-summary">
              <h3>检索问题与三路召回</h3>
              {task.retrieval_summary.map((summary, index) => (
                <details
                  key={`${summary.query_id}-${summary.attempt}-${index}`}
                >
                  <summary>
                    {summary.purpose || summary.query_id} · 选出{" "}
                    {summary.selected_count} 条
                  </summary>
                  <small>
                    结构化 {summary.structured_matches} · 关键词{" "}
                    {summary.keyword_matches} · 向量 {summary.semantic_matches}{" "}
                    · 第 {summary.attempt} 次
                  </small>
                  <p>{summary.query}</p>
                </details>
              ))}
            </div>
          )}
        </aside>

        <section className="panel panel--main">
          <h2>演化认知</h2>
          {!evolution && <p className="empty">确认任务后点击“开始执行”。</p>}
          {evolution && (
            <>
              <div className="timeline-wrap">
                <div className="timeline-heading">
                  <div>
                    <p className="eyebrow">HISTORICAL MAINLINE</p>
                    <h3>历史主时间线</h3>
                  </div>
                  <small>秦篆、秦隶是古文字与今文字的重要分界</small>
                </div>
                <nav className="timeline" aria-label="汉字历史主时间线">
                  {mainlineStages.map((stage, index) => (
                    <div className="timeline-node" key={stage.stage_id}>
                      <StageButton
                        active={stage.stage_id === selectedStage?.stage_id}
                        onSelect={() => setSelectedStageId(stage.stage_id)}
                        stage={stage}
                      />
                      {index < mainlineStages.length - 1 && (
                        <span className="timeline-arrow" aria-hidden="true">
                          →
                        </span>
                      )}
                    </div>
                  ))}
                </nav>
                <p className="timeline-caption">
                  甲骨文、金文是资料与书体分类，年代可能重叠；单图没有可靠断代时不作推测。
                </p>
              </div>
              {branchStages.length > 0 && (
                <section className="branch-lane" aria-labelledby="branch-title">
                  <div className="branch-connector" aria-hidden="true">
                    ↳
                  </div>
                  <div className="branch-content">
                    <div className="timeline-heading">
                      <div>
                        <p className="eyebrow">WRITING BRANCH</p>
                        <h3 id="branch-title">草书支线</h3>
                      </div>
                      <small>
                        从隶书快速书写发展，并参与行书形成，不是楷书的下一阶段
                      </small>
                    </div>
                    <div className="branch-stages">
                      {branchStages.map((stage) => (
                        <StageButton
                          active={stage.stage_id === selectedStage?.stage_id}
                          key={stage.stage_id}
                          onSelect={() => setSelectedStageId(stage.stage_id)}
                          stage={stage}
                        />
                      ))}
                    </div>
                  </div>
                </section>
              )}
              <div className="view-tabs" role="tablist" aria-label="演化视图">
                <button
                  className={evolutionView === "shape" ? "is-active" : ""}
                  onClick={() => setEvolutionView("shape")}
                >
                  字形
                </button>
                <button
                  className={evolutionView === "meaning" ? "is-active" : ""}
                  onClick={() => setEvolutionView("meaning")}
                >
                  字义
                </button>
                <button
                  className={evolutionView === "culture" ? "is-active" : ""}
                  onClick={() => setEvolutionView("culture")}
                >
                  文化
                </button>
              </div>
              {selectedStage && evolutionView === "shape" && (
                <>
                  <article className="stage-focus">
                    <div className="stage-mark stage-mark--large">
                      <StageGlyph large stage={selectedStage} />
                    </div>
                    <div>
                      <p className="stage-meta">
                        {selectedStage.historical_period ??
                          selectedStage.period}{" "}
                        · {selectedStage.script_type} ·{" "}
                        {selectedStage.sample_date ??
                          selectedStage.approximate_date}
                      </p>
                      <span className="variant-badge">
                        {selectedStage.availability === "dataset_gap"
                          ? "数据集缺口"
                          : selectedStage.lineage_role === "branch"
                            ? "书写支线"
                            : selectedStage.lineage_role === "transition"
                              ? "古今文字过渡"
                              : "历史主干代表字形"}
                      </span>
                      {selectedStage.region_or_system && (
                        <span className="variant-badge variant-badge--secondary">
                          {selectedStage.region_or_system}
                        </span>
                      )}
                      <h3>{selectedStage.structure_description}</h3>
                      {selectedStage.change_from_previous && (
                        <p>{selectedStage.change_from_previous}</p>
                      )}
                      <p className="glyph-source">
                        <small>
                          来源：{selectedStage.source_label}
                          {selectedStage.image_attribution && (
                            <>
                              <br />
                              {selectedStage.image_attribution}
                            </>
                          )}
                          {selectedStage.source_path && (
                            <>
                              <br />
                              原始路径：{selectedStage.source_path}
                            </>
                          )}
                        </small>
                        {selectedStageSource?.url && (
                          <a
                            href={selectedStageSource.url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            查看 JieZi 数据集 ↗
                          </a>
                        )}
                      </p>
                    </div>
                  </article>
                  <GlyphVariantExplorer
                    stage={selectedStage}
                    stages={evolution.glyph_stages}
                  />
                </>
              )}
              {evolutionView === "meaning" && (
                <ul className="evolution-notes">
                  {evolution.meaning_changes.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
              {evolutionView === "culture" && (
                <ul className="evolution-notes">
                  {evolution.cultural_contexts.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
              {evolutionView === "shape" && (
                <ol className="evolution-notes">
                  {evolution.shape_changes.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              )}
            </>
          )}
          {content && (
            <article className="content-preview">
              <h2>{content.title}</h2>
              <pre>{content.body_markdown}</pre>
              <h3>互动题</h3>
              <ol>
                {content.interaction_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ol>
            </article>
          )}
        </section>

        <aside className="panel">
          <h2>证据与审校</h2>
          {evolution?.claims.map((claim) => (
            <details className="evidence-card" key={claim.claim_id}>
              <summary>
                <span className="grade">{claim.evidence_grade}</span>
                <span>{claim.content}</span>
                <small>
                  {claim.claim_type} · {claim.audit_status}
                </small>
              </summary>
              <div className="evidence-detail">
                {claim.evidence_ids.length === 0 && (
                  <p className="empty">系统归纳，没有作为文献事实发布。</p>
                )}
                {claim.evidence_ids.map((evidenceId) => {
                  const evidence = evidenceById.get(evidenceId);
                  if (!evidence) return null;
                  return (
                    <article className="source-card" key={evidenceId}>
                      <p>
                        <strong>{evidence.title}</strong>
                        <span className="source-grade">
                          {evidence.authority_level} 级
                        </span>
                      </p>
                      <blockquote>{evidence.quote_or_summary}</blockquote>
                      <small>
                        {evidence.author_or_org}
                        {evidence.publication_date
                          ? ` · ${evidence.publication_date}`
                          : ""}
                        <br />
                        定位：{evidence.locator}
                        <br />
                        许可：{evidence.license}
                      </small>
                      {evidence.url && (
                        <a
                          className="source-link"
                          href={evidence.url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          查看来源 ↗
                        </a>
                      )}
                    </article>
                  );
                })}
              </div>
            </details>
          ))}
          {evolution && evolution.controversies.length > 0 && (
            <section className="controversy-box">
              <h3>争议与边界</h3>
              {evolution.controversies.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </section>
          )}
          {task.audit_report && (
            <section
              className={
                task.audit_report.status === "approved"
                  ? "audit-box audit-box--pass"
                  : "audit-box audit-box--warn"
              }
            >
              <h3>审校结论</h3>
              <p>{task.audit_report.summary}</p>
              <small>
                {task.audit_report.model} · {task.audit_report.prompt_version} ·
                第{task.audit_report.attempt} 次
                {task.audit_report.fallback_used ? " · 已启用本地降级" : ""}
              </small>
              {task.audit_report.issues.map((issue) => (
                <p
                  className="audit-issue"
                  key={`${issue.issue_code}-${issue.claim_id}`}
                >
                  {issue.message}
                </p>
              ))}
            </section>
          )}
          {task.constraint_result && (
            <div
              className={
                task.constraint_result.passed ? "check-pass" : "check-fail"
              }
            >
              约束检查：
              {task.constraint_result.passed ? "全部通过" : "存在未满足项"}
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}

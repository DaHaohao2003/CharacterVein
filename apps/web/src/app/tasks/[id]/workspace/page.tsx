"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AppNavigation, type WorkspaceView } from "@/components/app-navigation";
import { WorkspaceAgentPanel } from "@/components/workspace-agent-panel";
import {
  acknowledgeLimitations,
  createTask,
  creativeArtifactExportUrl,
  exportUrl,
  getCreativeArtifacts,
  getEvents,
  getTask,
  resumeTask,
  runTask,
  searchGlyphImages,
  selectNarrativeRoute,
} from "@/lib/api";
import { toPublicCopy, toPublicToolName } from "@/lib/public-copy";
import type {
  ConversationTurn,
  CreativeArtifact,
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
        <small>当前资料暂未收录</small>
      </span>
    );
  }
  const size = large ? 112 : 84;
  return (
    <Image
      alt={`${stage.character}字${stage.script_type}代表字形`}
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
      aria-label={`查看${stage.period}${stage.script_type}${stage.availability === "dataset_gap" ? "资料缺口" : "代表字形"}`}
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
          <p className="eyebrow">HISTORICAL GLYPH LIBRARY</p>
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
                aria-label={`查看${stage.script_type}${representative ? "代表字形" : "异体样本"}`}
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
              </button>
            );
          })}
        </div>
      )}

      {selectedVariant && (
        <div className="variant-preview">
          <div className="variant-preview-image">
            <ContainedGlyphImage
              alt={`${stage.character}字${stage.script_type}放大字形`}
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
            <p className="variant-description">
              图片仅作为该书体的视觉样本，用于观察轮廓、构件位置和线条形态。
            </p>
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
              <small>当前所选字形</small>
            </article>
            <span className="comparison-mark" aria-hidden="true">
              ⇄
            </span>
            <article>
              <span className="comparison-image">
                {compareStage.availability === "available" &&
                compareStage.image_url ? (
                  <ContainedGlyphImage
                    alt={`${compareStage.character}字${compareStage.script_type}代表字形`}
                    sizes="10rem"
                    src={compareStage.image_url}
                  />
                ) : (
                  <StageGlyph large stage={compareStage} />
                )}
              </span>
              <strong>{compareStage.script_type}</strong>
              <small>时间线代表字形</small>
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [artifacts, setArtifacts] = useState<CreativeArtifact[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [running, setRunning] = useState(false);
  const [acknowledging, setAcknowledging] = useState(false);
  const [selectingRoute, setSelectingRoute] = useState("");
  const autoRunStarted = useRef(false);
  const [selectedStageId, setSelectedStageId] = useState("");
  const [evolutionView, setEvolutionView] = useState<
    "shape" | "meaning" | "culture"
  >("shape");
  const requestedView = searchParams.get("view");
  const [currentView, setCurrentView] = useState<WorkspaceView>(
    requestedView === "evolution" ||
      requestedView === "sources" ||
      requestedView === "output" ||
      requestedView === "task"
      ? requestedView
      : "output",
  );
  const bootstrapConversation = searchParams.get("chat") === "1";
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function refresh() {
      const [taskResult, eventResult, artifactResult] = await Promise.all([
        getTask(id),
        getEvents(id),
        getCreativeArtifacts(id),
      ]);
      if (cancelled) return;
      setTask(taskResult);
      setEvents(eventResult);
      setArtifacts(artifactResult);
      setSelectedArtifactId(
        (current) => current || artifactResult[0]?.id || "",
      );
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

  async function chooseNarrativeRoute(routeId: string) {
    setSelectingRoute(routeId);
    setError("");
    try {
      let latest = await selectNarrativeRoute(id, routeId);
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
      setError(reason instanceof Error ? reason.message : "路线选择失败");
    } finally {
      setSelectingRoute("");
    }
  }

  async function startNewTask(requirement: string) {
    if (!task) return;
    const created = await createTask(
      requirement,
      task.input_asset_ids,
      task.spec.web_search_enabled,
    );
    router.push(`/tasks/${created.id}/workspace?chat=1`);
  }

  async function handleConversationTurn(turn: ConversationTurn) {
    const [latestTask, latestEvents, latestArtifacts] = await Promise.all([
      getTask(id),
      getEvents(id),
      getCreativeArtifacts(id),
    ]);
    setTask(latestTask);
    setEvents(latestEvents);
    setArtifacts(latestArtifacts);
    if (turn.artifact) setSelectedArtifactId(turn.artifact.id);
    const viewMap: Record<ConversationTurn["workspace_view"], WorkspaceView> = {
      conversation: "task",
      evolution: "evolution",
      sources: "sources",
      artifact: "output",
    };
    setCurrentView(viewMap[turn.workspace_view]);
  }

  if (!task)
    return <main className="loading">{error || "正在载入工作台…"}</main>;

  const evolution = task.evolution_package;
  const content = task.generated_content;
  const selectedArtifact =
    artifacts.find((item) => item.id === selectedArtifactId) ?? artifacts[0];
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
  const visualAnalysis = evolution?.visual_analysis;
  const selectedVisualObservation = selectedStage
    ? visualAnalysis?.stage_observations.find(
        (item) =>
          item.image_id.replace(/\.[^.]+$/, "") === selectedStage.image_id,
      )
    : undefined;

  return (
    <main className="agent-app-shell workspace-agent-shell">
      <AppNavigation
        active="workspace"
        character={task.spec.target_characters.join("")}
        currentView={currentView}
        onViewChange={setCurrentView}
        status={task.status}
        taskId={id}
      />

      <section className="agent-canvas workspace-canvas">
        <header className="workspace-canvas-header">
          <div>
            <p className="eyebrow">CULTURAL COMMUNICATION WORKSPACE</p>
            <h1>
              {task.spec.target_characters.length
                ? `“${task.spec.target_characters.join("")}”字文化创作空间`
                : "汉字文化创作空间"}
            </h1>
            <p>
              通过右侧对话提问、研究、生成任意传播内容，并持续修改或转换形式。
            </p>
          </div>
          <div className="workspace-canvas-actions">
            {selectedArtifact && (
              <a
                className="button-link button-link--secondary"
                href={creativeArtifactExportUrl(id, selectedArtifact.id)}
              >
                导出当前作品
              </a>
            )}
            {!selectedArtifact && content && (
              <Link
                className="button-link button-link--secondary"
                href={`/tasks/${id}/content`}
              >
                编辑内容
              </Link>
            )}
            {!selectedArtifact && content && (
              <a
                className="button-link button-link--secondary"
                href={exportUrl(id)}
              >
                导出
              </a>
            )}
          </div>
        </header>

        <div className="workspace-view-stack">
          {currentView === "task" && (
            <section className="panel workspace-overview-panel">
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
              {task.agent_runtime.decision_summary && (
                <section className="agent-decision-card">
                  <small>当前决策 · {task.agent_runtime.current_phase}</small>
                  <strong>{task.agent_runtime.next_action}</strong>
                  <p>{toPublicCopy(task.agent_runtime.decision_summary)}</p>
                </section>
              )}
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
                        {step.summary && <p>{toPublicCopy(step.summary)}</p>}
                        {(step.tool_names?.length ?? 0) > 0 && (
                          <small>
                            工具：
                            {step.tool_names.map(toPublicToolName).join(" · ")}
                          </small>
                        )}
                        <details>
                          <summary>验收与失败动作</summary>
                          <small>完成标准：{step.completion_criteria}</small>
                          <small>失败动作：{step.failure_action}</small>
                          {(step.depends_on?.length ?? 0) > 0 && (
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
                      {toPublicCopy(event.summary)}
                    </li>
                  ))}
              </ol>
              {(task.tool_calls?.length ?? 0) > 0 && (
                <div className="tool-trace">
                  <h3>工具调用轨迹</h3>
                  {(task.tool_calls ?? [])
                    .slice(-14)
                    .reverse()
                    .map((call) => (
                      <article key={call.tool_call_id}>
                        <header>
                          <code>{call.tool_name}</code>
                          <span>{call.status}</span>
                        </header>
                        <p>{toPublicCopy(call.input_summary)}</p>
                        <small>
                          {toPublicCopy(call.result_summary)} ·{" "}
                          {call.duration_ms.toFixed(0)} ms · 第 {call.attempt}{" "}
                          次
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
                        {summary.keyword_matches} · 向量{" "}
                        {summary.semantic_matches} · 第 {summary.attempt} 次
                      </small>
                      <p>{toPublicCopy(summary.query)}</p>
                    </details>
                  ))}
                </div>
              )}
            </section>
          )}

          {currentView === "evolution" && (
            <section className="panel panel--main workspace-evolution-panel">
              <h2>演化认知</h2>
              {!evolution && (
                <p className="empty">确认任务后点击“开始执行”。</p>
              )}
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
                    <section
                      className="branch-lane"
                      aria-labelledby="branch-title"
                    >
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
                              active={
                                stage.stage_id === selectedStage?.stage_id
                              }
                              key={stage.stage_id}
                              onSelect={() =>
                                setSelectedStageId(stage.stage_id)
                              }
                              stage={stage}
                            />
                          ))}
                        </div>
                      </div>
                    </section>
                  )}
                  {visualAnalysis && (
                    <section
                      className="visual-analysis"
                      aria-labelledby="visual-analysis-title"
                    >
                      <div className="timeline-heading">
                        <div>
                          <p className="eyebrow">MULTIMODAL OBSERVATION</p>
                          <h3 id="visual-analysis-title">多模态字形观察</h3>
                        </div>
                        <small>
                          {visualAnalysis.model}
                          {visualAnalysis.fallback_used
                            ? " · 已降级"
                            : " · 已读取代表图"}
                        </small>
                      </div>
                      {visualAnalysis.overall_summary && (
                        <p>{toPublicCopy(visualAnalysis.overall_summary)}</p>
                      )}
                      {selectedVisualObservation ? (
                        <article className="visual-observation-card">
                          <strong>
                            {selectedVisualObservation.script_type} ·
                            当前图片观察
                          </strong>
                          {selectedVisualObservation.composition && (
                            <p>{selectedVisualObservation.composition}</p>
                          )}
                          {selectedVisualObservation.stroke_form && (
                            <p>{selectedVisualObservation.stroke_form}</p>
                          )}
                          <ul>
                            {selectedVisualObservation.visible_features.map(
                              (feature) => (
                                <li key={feature}>{feature}</li>
                              ),
                            )}
                          </ul>
                        </article>
                      ) : (
                        <p className="empty">
                          {visualAnalysis.fallback_used
                            ? "本次多模态调用未成功，系统没有补写视觉细节。"
                            : "当前阶段暂无结构化视觉观察。"}
                        </p>
                      )}
                      {visualAnalysis.comparisons.length > 0 && (
                        <details className="visual-comparisons">
                          <summary>
                            查看 {visualAnalysis.comparisons.length}{" "}
                            组阶段图像对比
                          </summary>
                          {visualAnalysis.comparisons.map((comparison) => (
                            <article
                              key={`${comparison.from_image_id}-${comparison.to_image_id}`}
                            >
                              <strong>
                                {evolution.glyph_stages.find(
                                  (stage) =>
                                    stage.image_id ===
                                    withoutExtension(comparison.from_image_id),
                                )?.script_type ?? "前一阶段"}{" "}
                                →{" "}
                                {evolution.glyph_stages.find(
                                  (stage) =>
                                    stage.image_id ===
                                    withoutExtension(comparison.to_image_id),
                                )?.script_type ?? "后一阶段"}
                              </strong>
                              <p>{comparison.summary}</p>
                              <small>
                                {comparison.visible_changes.join("；")}
                              </small>
                            </article>
                          ))}
                        </details>
                      )}
                      {visualAnalysis.warnings.map((warning) => (
                        <p className="visual-warning" key={warning}>
                          {toPublicCopy(warning)}
                        </p>
                      ))}
                      <small>
                        这里只描述图片可见特征，不根据图像判断年代、出处或直接传承关系。
                      </small>
                    </section>
                  )}
                  <div
                    className="view-tabs"
                    role="tablist"
                    aria-label="演化视图"
                  >
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
                          <h3>
                            {toPublicCopy(selectedStage.structure_description)}
                          </h3>
                          {selectedStage.change_from_previous && (
                            <p>
                              {toPublicCopy(selectedStage.change_from_previous)}
                            </p>
                          )}
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
                        <li key={item}>{toPublicCopy(item)}</li>
                      ))}
                    </ul>
                  )}
                  {evolutionView === "culture" && (
                    <ul className="evolution-notes">
                      {evolution.cultural_contexts.map((item) => (
                        <li key={item}>{toPublicCopy(item)}</li>
                      ))}
                    </ul>
                  )}
                  {evolutionView === "shape" && (
                    <ol className="evolution-notes">
                      {evolution.shape_changes.map((item) => (
                        <li key={item}>{toPublicCopy(item)}</li>
                      ))}
                    </ol>
                  )}
                </>
              )}
            </section>
          )}

          {currentView === "sources" && (
            <section className="panel workspace-sources-panel">
              <div className="workspace-section-heading">
                <div>
                  <p className="eyebrow">REFERENCE CONTEXT</p>
                  <h2>本次生成参考</h2>
                </div>
                <span>{evolution?.evidence.length ?? 0} 条内容</span>
              </div>
              <p className="panel-note">
                以下网络内容和用户资料会作为大模型的生成上下文，用于减少无依据补写；系统不执行逐句引用或事实核验。
              </p>
              <div className="workspace-source-grid">
                {evolution?.evidence.length ? (
                  evolution.evidence.map((item) => (
                    <article className="source-card" key={item.evidence_id}>
                      <p>
                        <strong>{item.title}</strong>
                        <span className="source-grade">
                          {item.origin === "web"
                            ? "网络"
                            : item.origin === "user_upload"
                              ? "我的资料"
                              : "开发参考"}
                        </span>
                      </p>
                      <blockquote>{item.quote_or_summary}</blockquote>
                      <small>
                        {item.author_or_org}
                        {item.publication_date
                          ? ` · ${item.publication_date}`
                          : ""}
                        <br />
                        位置：{item.locator}
                      </small>
                      {item.url && (
                        <a
                          className="source-link"
                          href={item.url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          查看原内容 ↗
                        </a>
                      )}
                    </article>
                  ))
                ) : (
                  <p className="empty">当前没有检索到可用参考资料。</p>
                )}
              </div>
              {task.retrieval_summary && task.retrieval_summary.length > 0 && (
                <section className="retrieval-overview">
                  <h3>检索过程摘要</h3>
                  {task.retrieval_summary.map((summary, index) => (
                    <article
                      key={`${summary.query_id}-${summary.attempt}-${index}`}
                    >
                      <strong>{summary.purpose || summary.query_id}</strong>
                      <p>{summary.query}</p>
                      <small>
                        候选 {summary.candidate_count} · 最终选用{" "}
                        {summary.selected_count} · 结构化{" "}
                        {summary.structured_matches} · 关键词{" "}
                        {summary.keyword_matches} · 向量{" "}
                        {summary.semantic_matches}
                      </small>
                    </article>
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
            </section>
          )}

          {currentView === "output" && (
            <section className="panel workspace-output-panel">
              <div className="workspace-section-heading">
                <div>
                  <p className="eyebrow">CREATIVE ARTIFACTS</p>
                  <h2>创作作品</h2>
                </div>
                {!selectedArtifact && content && (
                  <Link className="button-link" href={`/tasks/${id}/content`}>
                    打开旧版内容编辑器
                  </Link>
                )}
              </div>
              {selectedArtifact ? (
                <div className="creative-artifact-workspace">
                  <nav
                    aria-label="本次对话生成的作品"
                    className="creative-artifact-list"
                  >
                    {artifacts.map((artifact) => (
                      <button
                        className={
                          artifact.id === selectedArtifact.id ? "is-active" : ""
                        }
                        key={artifact.id}
                        onClick={() => setSelectedArtifactId(artifact.id)}
                        type="button"
                      >
                        <span>{artifact.format_label}</span>
                        <strong>{artifact.title}</strong>
                        <small>版本 {artifact.version}</small>
                      </button>
                    ))}
                  </nav>
                  <article className="creative-artifact-preview">
                    <header>
                      <div>
                        <span>{selectedArtifact.format_label}</span>
                        <h2>{toPublicCopy(selectedArtifact.title)}</h2>
                        <p>{toPublicCopy(selectedArtifact.summary)}</p>
                      </div>
                      <small>版本 {selectedArtifact.version}</small>
                    </header>
                    <pre>{toPublicCopy(selectedArtifact.content_markdown)}</pre>
                    <footer>
                      <span>
                        继续在右侧告诉智能体要修改的段落或新的传播形式。
                      </span>
                      <a
                        href={creativeArtifactExportUrl(
                          id,
                          selectedArtifact.id,
                        )}
                      >
                        导出 Markdown
                      </a>
                    </footer>
                  </article>
                </div>
              ) : content ? (
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
              ) : (
                <div className="workspace-empty-state">
                  <span>稿</span>
                  <h3>这里是动态作品工作区</h3>
                  <p>
                    在右侧直接说“写一篇公众号文章”“生成课堂活动”或任何你需要的内容；生成后还可以继续修改和转换形式。
                  </p>
                </div>
              )}
            </section>
          )}
        </div>
      </section>

      <WorkspaceAgentPanel
        activeArtifactId={selectedArtifact?.id}
        acknowledging={acknowledging}
        error={error}
        events={events}
        bootstrapConversation={bootstrapConversation}
        onAcknowledge={confirmEvidenceBoundary}
        onConversationTurn={handleConversationTurn}
        onExecute={execute}
        onSelectRoute={chooseNarrativeRoute}
        onStartNewTask={startNewTask}
        running={running}
        selectingRoute={selectingRoute}
        task={task}
      />
    </main>
  );
}

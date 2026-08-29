"use client";

import { ChangeEvent, FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { AppNavigation } from "@/components/app-navigation";
import { createTask, uploadAsset } from "@/lib/api";
import { COMMUNICATION_FORMATS } from "@/lib/communication-formats";
import type { Asset } from "@/lib/types";

type SectionMode = "research" | "communication";

const RESEARCH_CASES = [
  {
    character: "云",
    label: "天象意象",
    prompt: "研究“云”字的历史字形和天象文化意象。",
  },
  {
    character: "雷",
    label: "声音想象",
    prompt: "研究“雷”字的字形结构、历史变化和声音想象。",
  },
  {
    character: "礼",
    label: "礼仪生活",
    prompt: "研究“礼”字如何连接古代礼仪与社会生活。",
  },
  {
    character: "明",
    label: "光明认知",
    prompt: "研究“明”字的可见构形与文化语义。",
  },
] as const;

const COPY = {
  research: {
    eyebrow: "HANZI RESEARCH",
    title: "从一个字，进入它的历史与文化语境",
    description:
      "让智能体调取真实字形、网络内容和上传资料，比较历史书写，整理可继续追问的研究上下文。",
    placeholder: "告诉我想研究哪个汉字，以及最关心的问题…",
    greeting: "这里是汉字研究空间。",
    guidance:
      "输入一个现代汉字或具体问题。我会先明确研究对象，再按需观察字形、搜索网络并阅读你上传的资料。",
    suggestion: "研究“雷”字的甲骨文和金文，只描述图片中能直接看到的区别。",
  },
  communication: {
    eyebrow: "CULTURAL COMMUNICATION",
    title: "把汉字研究，转化成真正能够传播的内容",
    description:
      "作品形式由你决定。智能体可以生成、修改和转换文章、讲稿、图文方案、教育内容与视频脚本，并在对话中持续调整内容与交付形式。",
    placeholder: "告诉我传播对象、使用场景和想生成的内容…",
    greeting: "这里是文化传播空间。",
    guidance:
      "可以直接提出创作需求，也可以先从汉字研究开始。生成后继续说“改短一点”或“换成播客稿”即可。",
    suggestion: "根据“雷”字研究，写一篇面向中学生的校园广播稿。",
  },
} as const;

export function SectionLanding({ mode }: { mode: SectionMode }) {
  const router = useRouter();
  const copy = COPY[mode];
  const [rawInput, setRawInput] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [error, setError] = useState("");

  async function begin(requirement: string) {
    const content = requirement.trim();
    if (content.length < 2 || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const task = await createTask(
        content,
        assets.map((asset) => asset.id),
        webSearchEnabled,
      );
      const view = mode === "research" ? "evolution" : "output";
      router.push(
        `/tasks/${task.id}/workspace?space=${mode}&view=${view}&chat=1`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建任务失败");
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await begin(rawInput);
  }

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setUploading(true);
    setError("");
    try {
      const uploaded: Asset[] = [];
      for (const file of files) uploaded.push(await uploadAsset(file));
      setAssets((current) => [...current, ...uploaded]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传资料失败");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  return (
    <main className="agent-app-shell section-landing-shell">
      <AppNavigation active={mode} />

      <section className="agent-canvas section-landing-canvas">
        <header className="canvas-toolbar">
          <div>
            <p className="eyebrow">{copy.eyebrow}</p>
            <h1>{mode === "research" ? "汉字研究" : "文化传播"}</h1>
          </div>
          <span className="canvas-mode-badge">
            {mode === "research" ? "研究模式" : "创作模式"}
          </span>
        </header>

        <section className={`section-landing-hero is-${mode}`}>
          <span className="section-landing-mark" aria-hidden="true">
            {mode === "research" ? "研" : "传"}
          </span>
          <p className="eyebrow">
            {mode === "research" ? "先理解，再表达" : "从研究走向传播"}
          </p>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </section>

        {mode === "research" ? (
          <section
            className="section-entry-block"
            aria-labelledby="research-cases-title"
          >
            <div className="canvas-section-heading">
              <div>
                <p className="eyebrow">RESEARCH STARTERS</p>
                <h2 id="research-cases-title">
                  选择演示字，或在右侧输入任意汉字
                </h2>
              </div>
              <p>
                有本地字形数据时展示完整时间线；暂无图片时仍可结合网络与文档继续研究。
              </p>
            </div>
            <div className="research-entry-grid">
              {RESEARCH_CASES.map((item) => (
                <button
                  disabled={submitting}
                  key={item.character}
                  onClick={() => void begin(item.prompt)}
                  type="button"
                >
                  <span>{item.character}</span>
                  <strong>{item.label}</strong>
                  <small>进入研究空间 →</small>
                </button>
              ))}
            </div>
            <div className="section-process-row">
              <article>
                <span>01</span>
                <strong>明确研究对象</strong>
                <small>从自然语言中识别目标字和问题范围</small>
              </article>
              <article>
                <span>02</span>
                <strong>调取多源材料</strong>
                <small>结合真实字形、网络搜索和上传文档</small>
              </article>
              <article>
                <span>03</span>
                <strong>形成研究上下文</strong>
                <small>保留结果，随时交给文化传播继续使用</small>
              </article>
            </div>
          </section>
        ) : (
          <section
            className="section-entry-block"
            aria-labelledby="communication-cases-title"
          >
            <div className="canvas-section-heading">
              <div>
                <p className="eyebrow">CREATE WITHOUT TEMPLATES</p>
                <h2 id="communication-cases-title">
                  形式不设限，内容可以持续修改
                </h2>
              </div>
              <p>
                以下只是示例，不是固定模板；在右侧直接说出你的真实传播需求。
              </p>
            </div>
            <div className="communication-entry-grid">
              {COMMUNICATION_FORMATS.map((item) => (
                <button
                  disabled={submitting}
                  key={item.id}
                  onClick={() => setRawInput(item.prompt)}
                  type="button"
                >
                  <span>{item.icon}</span>
                  <div>
                    <small>{item.category}</small>
                    <strong>{item.title}</strong>
                    <p>{item.description}</p>
                    <em>{item.deliverable}</em>
                  </div>
                  <small>填入需求 ↗</small>
                </button>
              ))}
            </div>
            <div className="section-process-row">
              <article>
                <span>01</span>
                <strong>选择作品形式</strong>
                <small>说明受众、场景、语气和交付内容</small>
              </article>
              <article>
                <span>02</span>
                <strong>对话生成作品</strong>
                <small>按需参考字形、网络与上传资料</small>
              </article>
              <article>
                <span>03</span>
                <strong>预览并继续修改</strong>
                <small>保留版本，支持续写、缩短或转换形式</small>
              </article>
            </div>
          </section>
        )}
      </section>

      <aside
        className="agent-chat-panel section-agent-panel"
        aria-label="字脉智能体对话"
      >
        <header className="agent-chat-header">
          <div className="agent-avatar">脉</div>
          <div>
            <strong>字脉智能体</strong>
            <small>
              <span className="status-dot status-dot--online" /> 等待你的需求
            </small>
          </div>
          <span className="agent-model-label">AGENT</span>
        </header>
        <div className="agent-conversation" aria-live="polite">
          <article className="chat-message chat-message--assistant">
            <span className="chat-message-avatar">脉</span>
            <div>
              <strong>{copy.greeting}</strong>
              <p>{copy.guidance}</p>
            </div>
          </article>
          <article className="agent-suggestion-card">
            <span>可以这样告诉我</span>
            <p>“{copy.suggestion}”</p>
          </article>
          {assets.length > 0 && (
            <article className="chat-message chat-message--tool">
              <span className="chat-message-avatar">✓</span>
              <div>
                <strong>已读取 {assets.length} 份资料</strong>
                <p>{assets.map((asset) => asset.filename).join("、")}</p>
              </div>
            </article>
          )}
          {submitting && (
            <article className="chat-message chat-message--assistant is-working">
              <span className="chat-message-avatar">脉</span>
              <div>
                <strong>正在建立任务</strong>
                <p>正在识别目标字、需求范围与可用资料…</p>
                <span className="thinking-dots">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </article>
          )}
          {error && <p className="agent-chat-error">{error}</p>}
        </div>
        <form className="agent-composer" onSubmit={handleSubmit}>
          {assets.length > 0 && (
            <div className="composer-assets">
              {assets.map((asset) => (
                <button
                  key={asset.id}
                  onClick={() =>
                    setAssets((items) =>
                      items.filter((item) => item.id !== asset.id),
                    )
                  }
                  type="button"
                >
                  {asset.filename} ×
                </button>
              ))}
            </div>
          )}
          <textarea
            onChange={(event) => setRawInput(event.target.value)}
            placeholder={copy.placeholder}
            value={rawInput}
          />
          <div className="composer-toolbar">
            <div>
              <label className="composer-tool-button" title="上传资料">
                ＋
                <input
                  accept=".txt,.md,.pdf,.doc,.docx,image/*"
                  disabled={uploading || submitting}
                  multiple
                  onChange={handleFiles}
                  type="file"
                />
              </label>
              <button
                aria-pressed={webSearchEnabled}
                className={
                  webSearchEnabled
                    ? "composer-tool-button is-active"
                    : "composer-tool-button"
                }
                onClick={() => setWebSearchEnabled((value) => !value)}
                title="切换网络搜索"
                type="button"
              >
                搜
              </button>
              <span className="composer-hint">
                {uploading
                  ? "正在读取资料…"
                  : webSearchEnabled
                    ? "网络搜索已开启"
                    : "仅使用已有上下文"}
              </span>
            </div>
            <button
              aria-label="开始"
              className="composer-send"
              disabled={submitting || rawInput.trim().length < 2}
              type="submit"
            >
              ↑
            </button>
          </div>
        </form>
      </aside>
    </main>
  );
}

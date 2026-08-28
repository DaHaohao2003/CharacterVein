"use client";

import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useState } from "react";

import { AppNavigation } from "@/components/app-navigation";
import { createTask, uploadAsset } from "@/lib/api";
import type { Asset } from "@/lib/types";

const DEMO_CASES = [
  {
    character: "云",
    theme: "天象如何成为文化意象",
    description: "观察卷曲、层叠与结构整理，再由你决定要讨论或创作什么。",
    prompt:
      "我想面向小学六年级传播“云”字文化。先和我讨论字形与天象意象，再一起决定做成什么内容。",
  },
  {
    character: "雷",
    theme: "从构形进入声音想象",
    description: "比较历代构件变化，把复杂字形转化为可理解的视觉故事。",
    prompt:
      "研究“雷”字的字形结构和声音想象，面向中学生。先提出几个有趣的传播切口。",
  },
  {
    character: "礼",
    theme: "礼仪实践与社会生活",
    description: "从字形构件进入礼仪观念，连接古代生活与当代文化表达。",
    prompt:
      "和我一起探索“礼”字怎样连接古代礼仪与当代生活，之后我会告诉你需要的作品形式。",
  },
  {
    character: "明",
    theme: "光明、构形与认知引申",
    description: "辨认构件布局，用清晰叙事区分字形观察与文化联想。",
    prompt:
      "围绕“明”字做一项博物馆公共教育创作，先分析可见字形，再根据我们的讨论生成内容。",
  },
] as const;

const PROMPT_STARTERS = [
  "和我研究一个汉字",
  "写一篇面向中学生的文化文章",
  "把当前作品改成播客稿",
] as const;

export default function Home() {
  const router = useRouter();
  const [rawInput, setRawInput] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [demoCharacter, setDemoCharacter] = useState("");
  const [demoStatus, setDemoStatus] = useState("");
  const [error, setError] = useState("");

  async function startDemo(demo: (typeof DEMO_CASES)[number]) {
    setDemoCharacter(demo.character);
    setDemoStatus("正在理解你的传播目标并建立任务…");
    setError("");
    try {
      const task = await createTask(demo.prompt);
      setDemoStatus("已识别主题和受众，正在进入对话创作空间…");
      router.push(`/tasks/${task.id}/workspace?chat=1`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "案例启动失败");
      setDemoCharacter("");
      setDemoStatus("");
    }
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
      setError(reason instanceof Error ? reason.message : "上传材料失败");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rawInput.trim().length < 2) return;
    setSubmitting(true);
    setError("");
    try {
      const task = await createTask(
        rawInput,
        assets.map((asset) => asset.id),
        webSearchEnabled,
      );
      router.push(`/tasks/${task.id}/workspace?chat=1`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建任务失败");
      setSubmitting(false);
    }
  }

  return (
    <main className="agent-app-shell agent-app-shell--home">
      <AppNavigation active="home" />

      <section className="agent-canvas home-canvas">
        <header className="canvas-toolbar">
          <div>
            <p className="eyebrow">CULTURAL COMMUNICATION STUDIO</p>
            <h1>文化传播创作台</h1>
          </div>
          <span className="canvas-mode-badge">AI Agent 模式</span>
        </header>

        <div className="home-welcome">
          <span className="home-welcome-mark" aria-hidden="true">
            字
          </span>
          <p className="eyebrow">从一个汉字开始</p>
          <h2>把字形、历史资料和你的想法，变成真正能传播的文化内容</h2>
          <p>
            在右侧和智能体持续对话：可以提问、研究真实字形、参考网络和上传资料，也可以要求它生成、修改或转换任意汉字文化传播内容。
          </p>
          <div className="prompt-starters" aria-label="需求示例">
            {PROMPT_STARTERS.map((starter) => (
              <button
                key={starter}
                onClick={() => setRawInput(starter)}
                type="button"
              >
                {starter} <span>↗</span>
              </button>
            ))}
          </div>
        </div>

        <section className="home-demo-section" aria-labelledby="demo-title">
          <div className="canvas-section-heading">
            <div>
              <p className="eyebrow">DEMONSTRATION TASKS</p>
              <h2 id="demo-title">从一个汉字开始对话</h2>
            </div>
            <p>四个案例都包含真实字形；可以先研究，也可以直接提出创作要求。</p>
          </div>
          <div className="agent-demo-grid">
            {DEMO_CASES.map((demo) => (
              <button
                className="agent-demo-card"
                disabled={Boolean(demoCharacter)}
                key={demo.character}
                onClick={() => void startDemo(demo)}
                type="button"
              >
                <span className="agent-demo-character">{demo.character}</span>
                <span className="agent-demo-copy">
                  <small>多轮对话案例</small>
                  <strong>{demo.theme}</strong>
                  <span>{demo.description}</span>
                </span>
                <span className="agent-demo-arrow">→</span>
              </button>
            ))}
          </div>
        </section>

        <section className="agent-capability-row" aria-label="智能体能力">
          <article>
            <span>01</span>
            <strong>持续对话与理解</strong>
            <small>承接上下文，区分问答、研究、创作与改稿</small>
          </article>
          <article>
            <span>02</span>
            <strong>自主检索与观察</strong>
            <small>结合网络、上传文档和真实字形</small>
          </article>
          <article>
            <span>03</span>
            <strong>自由创作与转换</strong>
            <small>作品形式由你决定，并保留每次修改版本</small>
          </article>
        </section>
      </section>

      <aside
        className="agent-chat-panel home-agent-panel"
        aria-label="字脉智能体对话"
      >
        <header className="agent-chat-header">
          <div className="agent-avatar">脉</div>
          <div>
            <strong>字脉智能体</strong>
            <small>
              <span className="status-dot status-dot--online" /> 随时可以开始
            </small>
          </div>
          <span className="agent-model-label">MULTIMODAL</span>
        </header>

        <div className="agent-conversation" aria-live="polite">
          <article className="chat-message chat-message--assistant">
            <span className="chat-message-avatar">脉</span>
            <div>
              <strong>你好，我是字脉。</strong>
              <p>
                可以直接问我一个问题，也可以告诉我想研究哪个汉字、生成什么内容。之后继续说“改短一点”或“换成另一种形式”就可以。
              </p>
            </div>
          </article>
          <article className="agent-suggestion-card">
            <span>可以这样告诉我</span>
            <p>
              “先比较‘雷’字不同历史字形的可见特点，再和我讨论适合中学生的传播切口。”
            </p>
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
          {(submitting || demoStatus) && (
            <article className="chat-message chat-message--assistant is-working">
              <span className="chat-message-avatar">脉</span>
              <div>
                <strong>正在建立创作任务</strong>
                <p>{demoStatus || "正在解析目标、受众和传播渠道…"}</p>
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
                  aria-label={`移除 ${asset.filename}`}
                  key={asset.id}
                  onClick={() =>
                    setAssets((current) =>
                      current.filter((item) => item.id !== asset.id),
                    )
                  }
                  type="button"
                >
                  {asset.filename} ×
                </button>
              ))}
            </div>
          )}
          <label className="sr-only" htmlFor="agent-requirement">
            告诉字脉你的需求
          </label>
          <textarea
            id="agent-requirement"
            onChange={(event) => setRawInput(event.target.value)}
            placeholder="告诉我你想创作什么…"
            rows={5}
            value={rawInput}
          />
          <div className="composer-toolbar">
            <div>
              <label className="composer-tool-button" title="上传图片或文档">
                <span>＋</span>
                <input
                  accept=".jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.md,.markdown"
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
                title="使用网络搜索"
                type="button"
              >
                搜
              </button>
              <span className="composer-hint">
                {uploading
                  ? "正在读取资料…"
                  : webSearchEnabled
                    ? "网络搜索已开启"
                    : "仅使用内置与上传资料"}
              </span>
            </div>
            <button
              className="composer-send"
              disabled={submitting || uploading || rawInput.trim().length < 2}
              type="submit"
            >
              {submitting ? "…" : "↑"}
              <span className="sr-only">发送需求</span>
            </button>
          </div>
        </form>
      </aside>
    </main>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useState } from "react";

import { confirmTask, createTask, uploadAsset } from "@/lib/api";
import type { Asset } from "@/lib/types";

const DEMO_CASES = [
  {
    character: "云",
    theme: "天象观察与文化意象",
    description: "比较历代字形中的卷曲、层叠与结构整理。",
    prompt:
      "为小学六年级制作一份4分钟的“云”字文化讲解，展示至少3个历史阶段，争议观点不要写成定论，并生成2道互动题。",
  },
  {
    character: "雷",
    theme: "构形与声音想象",
    description: "观察复杂构件在不同历史阶段的组合与简化。",
    prompt:
      "为小学六年级制作一份4分钟的“雷”字文化讲解，展示至少3个历史阶段，争议观点不要写成定论，并生成2道互动题。",
  },
  {
    character: "礼",
    theme: "礼仪实践与社会秩序",
    description: "从字形构件进入礼仪观念及其历史表达。",
    prompt:
      "为小学六年级制作一份4分钟的“礼”字文化讲解，展示至少3个历史阶段，争议观点不要写成定论，并生成2道互动题。",
  },
  {
    character: "明",
    theme: "光明、构形与认知引申",
    description: "辨认构件布局，并区分字形事实与文化联想。",
    prompt:
      "为小学六年级制作一份4分钟的“明”字文化讲解，展示至少3个历史阶段，争议观点不要写成定论，并生成2道互动题。",
  },
] as const;

export default function Home() {
  const router = useRouter();
  const [rawInput, setRawInput] = useState(
    "为小学六年级制作一份 4 分钟的“云”字文化讲解，展示至少 3 个历史阶段，争议观点不要写成定论，并生成 2 道互动题。",
  );
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [demoCharacter, setDemoCharacter] = useState("");
  const [demoStatus, setDemoStatus] = useState("");
  const [error, setError] = useState("");

  async function startDemo(demo: (typeof DEMO_CASES)[number]) {
    setDemoCharacter(demo.character);
    setDemoStatus("正在理解任务要求…");
    setError("");
    try {
      const task = await createTask(demo.prompt);
      setDemoStatus("正在确认演化范围…");
      const confirmed = await confirmTask(task.id, task.spec);
      setDemoStatus("正在进入智能体工作台…");
      router.push(`/tasks/${confirmed.id}/workspace?autorun=1`);
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
    setSubmitting(true);
    setError("");
    try {
      const task = await createTask(
        rawInput,
        assets.map((asset) => asset.id),
      );
      router.push(`/tasks/${task.id}/confirm`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建任务失败");
      setSubmitting(false);
    }
  }

  return (
    <main className="home-shell">
      <section className="product-hero">
        <div>
          <p className="eyebrow">CHARACTER VEIN · 字脉</p>
          <h1>沿着真实字形，读懂一个汉字的历史脉络</h1>
          <p className="summary">
            以可信公开字形和可追溯证据为基础，观察汉字在历史主线与书写支线中的变化。系统负责检索、组织与讲解，不替代古文字释读。
          </p>
        </div>
        <div className="product-principles" aria-label="产品原则">
          <p>
            <strong>328</strong>
            <span>张真实字形</span>
          </p>
          <p>
            <strong>7</strong>
            <span>类历史书体</span>
          </p>
          <p>
            <strong>可追溯</strong>
            <span>来源与证据</span>
          </p>
        </div>
      </section>

      <section className="demo-section" aria-labelledby="demo-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">START WITH A CHARACTER</p>
            <h2 id="demo-title">选择一个字，开始观察</h2>
          </div>
          <p>四个案例均覆盖甲骨、金文、战国、篆、隶、楷、草七类字形。</p>
        </div>
        <div className="demo-grid">
          {DEMO_CASES.map((demo) => (
            <button
              className="demo-card"
              disabled={Boolean(demoCharacter)}
              key={demo.character}
              onClick={() => startDemo(demo)}
              type="button"
            >
              <span className="demo-character">{demo.character}</span>
              <span className="demo-copy">
                <strong>{demo.theme}</strong>
                <small>{demo.description}</small>
              </span>
              <span className="demo-action">
                {demoCharacter === demo.character ? "生成中…" : "进入演化 →"}
              </span>
            </button>
          ))}
        </div>
        {demoStatus && (
          <p className="demo-status" aria-live="polite">
            “{demoCharacter}”字 · {demoStatus}
          </p>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      <details className="custom-task">
        <summary>
          <span>
            <strong>自定义创作任务</strong>
            <small>调整受众、时长和互动要求，或添加现代展签与资料文档。</small>
          </span>
          <span aria-hidden="true">展开设置 ＋</span>
        </summary>
        <form className="task-form" onSubmit={handleSubmit}>
          <label htmlFor="task-input">任务描述</label>
          <textarea
            id="task-input"
            value={rawInput}
            onChange={(event) => setRawInput(event.target.value)}
            rows={5}
          />
          <label className="upload-zone" htmlFor="asset-input">
            <strong>{uploading ? "正在提取材料…" : "添加图片或文档"}</strong>
            <span>用于提取现代展签或资料文字，不识别未知古文字。</span>
            <input
              id="asset-input"
              accept=".jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.md,.markdown"
              disabled={uploading || submitting}
              multiple
              onChange={handleFiles}
              type="file"
            />
          </label>
          {assets.length > 0 && (
            <section className="asset-list" aria-label="用户提供材料">
              <h2>用户提供材料</h2>
              {assets.map((asset) => (
                <article className="asset-card" key={asset.id}>
                  <div>
                    <strong>{asset.filename}</strong>
                    <small>
                      {asset.kind === "image" ? "图片" : "文档"} ·{" "}
                      {(asset.size_bytes / 1024).toFixed(1)} KB ·{" "}
                      {asset.analysis.model}
                    </small>
                  </div>
                  <button
                    className="text-button"
                    onClick={() =>
                      setAssets((current) =>
                        current.filter((item) => item.id !== asset.id),
                      )
                    }
                    type="button"
                  >
                    移除
                  </button>
                  {asset.extracted_text && (
                    <p>{asset.extracted_text.slice(0, 180)}</p>
                  )}
                  {asset.analysis.warnings.map((warning) => (
                    <p className="asset-warning" key={warning}>
                      {warning}
                    </p>
                  ))}
                </article>
              ))}
            </section>
          )}
          <div className="form-footer">
            <span>当前完整支持：云、雷、礼、明</span>
            <button
              disabled={submitting || uploading || rawInput.trim().length < 2}
              type="submit"
            >
              {submitting ? "正在解析…" : "检查并确认任务"}
            </button>
          </div>
        </form>
      </details>
    </main>
  );
}

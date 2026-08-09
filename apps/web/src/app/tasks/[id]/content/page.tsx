"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  activateContentVersion,
  exportContent,
  getContentVersions,
  getTask,
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
  evidence_bound: "事实陈述绑定证据",
  audit_approved: "证据审校通过",
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
      setNotice(`已复用事实层并生成 v${version.version}，没有重新检索。`);
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

  async function copyMarkdown() {
    try {
      const result = await exportContent(id, "markdown");
      await navigator.clipboard.writeText(await result.blob.text());
      setNotice("Markdown 已复制。 ");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "复制失败");
    }
  }

  if (!task || !draft) {
    return <main className="loading">{error || "正在载入文化传播内容…"}</main>;
  }

  return (
    <main className="content-shell">
      <header className="content-header no-print">
        <div>
          <p className="eyebrow">
            文化传播编辑器 · v{task.current_content_version}
          </p>
          <h1>{draft.title}</h1>
          <p>事实层保持锁定；这里的操作只改变传播表达和内容版本。</p>
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
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </label>
          <label>
            输出形式
            <select
              value={outputType}
              onChange={(event) =>
                setOutputType(event.target.value as TaskSpec["output_type"])
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
              onChange={(event) => setMode(event.target.value as typeof mode)}
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
            🔒 复用已审校 EvolutionPackage，不调用检索与审校节点。
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
                  事实层 {version.evolution_hash.slice(0, 10)}…
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
              <button className="text-button" onClick={() => download("html")}>
                HTML
              </button>
              <button className="text-button" onClick={() => download("json")}>
                JSON
              </button>
              <button className="text-button" onClick={() => window.print()}>
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
                    className={passed ? "constraint-pass" : "constraint-fail"}
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
    </main>
  );
}

"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppNavigation } from "@/components/app-navigation";
import { confirmTask, getAsset, getTask } from "@/lib/api";
import type { Asset, Task, TaskSpec } from "@/lib/types";

export default function ConfirmTaskPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [task, setTask] = useState<Task | null>(null);
  const [spec, setSpec] = useState<TaskSpec | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentMessages, setAgentMessages] = useState<string[]>([]);

  useEffect(() => {
    getTask(id)
      .then(async (result) => {
        setTask(result);
        setSpec(result.spec);
        setAssets(await Promise.all(result.input_asset_ids.map(getAsset)));
      })
      .catch((reason: Error) => setError(reason.message));
  }, [id]);

  function update<K extends keyof TaskSpec>(key: K, value: TaskSpec[K]) {
    setSpec((current) => (current ? { ...current, [key]: value } : current));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!spec) return;
    setSaving(true);
    setError("");
    try {
      await confirmTask(id, spec);
      router.push(`/tasks/${id}/workspace`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败");
      setSaving(false);
    }
  }

  function addConstraint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const instruction = agentInstruction.trim();
    if (!instruction || !spec) return;
    update("constraints", [...spec.constraints, instruction]);
    setAgentMessages((current) => [...current, instruction]);
    setAgentInstruction("");
  }

  if (!task || !spec) {
    return <main className="loading">{error || "正在载入任务…"}</main>;
  }

  const needsTarget =
    spec.target_needs_confirmation || !spec.target_characters.length;

  return (
    <main className="agent-app-shell confirm-agent-shell">
      <AppNavigation
        active="workspace"
        character={spec.target_characters.join("")}
        status={task.status}
        taskId={id}
      />
      <section className="agent-canvas confirm-agent-canvas">
        <div className="page-shell page-shell--embedded">
          <header className="page-header confirm-canvas-header">
            <p className="eyebrow">任务确认</p>
            <h1>先确认字脉理解得是否准确</h1>
            <p>
              智能体已经把自然语言需求拆解为可执行参数。你可以直接在下面修正。
            </p>
          </header>
          {needsTarget && (
            <section className="confirmation-warning" role="alert">
              <strong>需要你确认目标汉字</strong>
              <p>
                上传材料没有以现代文字明确写出目标字。系统不会根据未知甲骨文、金文或篆文字形自行释读，请在下方填写一个现代汉字。
              </p>
            </section>
          )}
          {assets.length > 0 && (
            <section className="uploaded-context">
              <div>
                <p className="eyebrow">USER-PROVIDED CONTEXT</p>
                <h2>用户提供材料</h2>
                <p>
                  以下内容会作为当前任务的生成参考，并与网络检索内容一起提供给大模型。
                </p>
              </div>
              <div className="asset-list">
                {assets.map((asset) => (
                  <article className="asset-card" key={asset.id}>
                    <strong>{asset.filename}</strong>
                    <small>
                      {asset.kind === "image" ? "图片" : "文档"} ·{" "}
                      {asset.analysis.model}
                    </small>
                    {asset.extracted_text && (
                      <p>{asset.extracted_text.slice(0, 360)}</p>
                    )}
                    {asset.analysis.explicit_periods.length > 0 && (
                      <small>
                        明确年代：{asset.analysis.explicit_periods.join("、")}
                      </small>
                    )}
                    {asset.analysis.warnings.map((warning) => (
                      <p className="asset-warning" key={warning}>
                        {warning}
                      </p>
                    ))}
                  </article>
                ))}
              </div>
            </section>
          )}
          <form
            className="spec-grid confirm-spec-grid"
            id="task-confirm-form"
            onSubmit={submit}
          >
            <label>
              目标汉字
              <input
                aria-invalid={needsTarget}
                maxLength={1}
                placeholder="请输入一个现代汉字"
                value={spec.target_characters.join("")}
                onChange={(event) => {
                  const value = event.target.value.slice(0, 1);
                  update("target_characters", value ? [value] : []);
                  if (value) update("target_needs_confirmation", false);
                }}
              />
            </label>
            <label>
              文化主题
              <input
                value={spec.theme}
                onChange={(event) => update("theme", event.target.value)}
              />
            </label>
            <label>
              目标受众
              <input
                value={spec.audience}
                onChange={(event) => update("audience", event.target.value)}
              />
            </label>
            <label>
              预计时长（分钟）
              <input
                min={1}
                max={30}
                type="number"
                value={spec.duration_minutes}
                onChange={(event) =>
                  update("duration_minutes", Number(event.target.value))
                }
              />
            </label>
            <label>
              历史阶段数
              <input
                min={1}
                max={10}
                type="number"
                value={spec.required_stages}
                onChange={(event) =>
                  update("required_stages", Number(event.target.value))
                }
              />
            </label>
            <label>
              互动题数量
              <input
                min={0}
                max={10}
                type="number"
                value={spec.interaction_count}
                onChange={(event) =>
                  update("interaction_count", Number(event.target.value))
                }
              />
            </label>
            <label className="span-all">
              其他限制（每行一条）
              <textarea
                rows={3}
                value={spec.constraints.join("\n")}
                onChange={(event) =>
                  update(
                    "constraints",
                    event.target.value
                      .split("\n")
                      .filter((item) => item.trim()),
                  )
                }
              />
            </label>
            {error && <p className="span-all error">{error}</p>}
          </form>
        </div>
      </section>

      <aside
        className="agent-chat-panel confirm-agent-panel"
        aria-label="需求确认对话"
      >
        <header className="agent-chat-header">
          <div className="agent-avatar">脉</div>
          <div>
            <strong>需求理解助手</strong>
            <small>
              <span className="status-dot status-dot--online" /> 等待你确认
            </small>
          </div>
          <span className="agent-model-label">BRIEF AGENT</span>
        </header>
        <div className="agent-conversation">
          <article className="chat-message chat-message--user">
            <div>
              <p>{task.raw_input}</p>
            </div>
          </article>
          <article className="chat-message chat-message--assistant">
            <span className="chat-message-avatar">脉</span>
            <div>
              <strong>我这样理解你的需求</strong>
              <p>
                围绕“{spec.target_characters.join("") || "待确认"}”字，为
                {spec.audience}创作“{spec.theme}”主题内容，预计{" "}
                {spec.duration_minutes} 分钟，至少展示 {spec.required_stages}{" "}
                个历史阶段。
              </p>
            </div>
          </article>
          <article className="agent-process-card confirm-summary-card">
            <div>
              <span>传播目标</span>
              <strong>{task.communication_brief.communication_goal}</strong>
            </div>
            <div>
              <span>交付渠道</span>
              <strong>{task.communication_brief.channels.join(" · ")}</strong>
            </div>
            <div>
              <span>互动要求</span>
              <strong>{spec.interaction_count} 道互动题</strong>
            </div>
            <div>
              <span>参考方式</span>
              <strong>
                {spec.web_search_enabled
                  ? "网络搜索 + 已上传资料"
                  : "内置资料 + 已上传资料"}
              </strong>
            </div>
          </article>
          {needsTarget && (
            <article className="chat-confirmation-card">
              <span>需要补充</span>
              <strong>请在中间填写目标现代汉字</strong>
              <p>我不会根据未知古文字图片自行猜测目标字。</p>
            </article>
          )}
          {assets.length > 0 && (
            <article className="chat-message chat-message--tool">
              <span className="chat-message-avatar">✓</span>
              <div>
                <strong>已读取 {assets.length} 份上传资料</strong>
                <p>{assets.map((asset) => asset.filename).join("、")}</p>
              </div>
            </article>
          )}
          {agentMessages.map((message, index) => (
            <article
              className="chat-message chat-message--assistant"
              key={`${message}-${index}`}
            >
              <span className="chat-message-avatar">脉</span>
              <div>
                <strong>已加入补充要求</strong>
                <p>{message}</p>
              </div>
            </article>
          ))}
          {error && <p className="agent-chat-error">{error}</p>}
        </div>
        <button
          className="chat-primary-action agent-confirm-submit"
          disabled={saving || !spec.target_characters.length}
          form="task-confirm-form"
          type="submit"
        >
          <span>✓</span>
          <span>
            <strong>{saving ? "正在保存…" : "确认并进入工作台"}</strong>
            <small>下一步由智能体自主执行</small>
          </span>
        </button>
        <form
          className="agent-composer agent-composer--compact"
          onSubmit={addConstraint}
        >
          <label className="sr-only" htmlFor="confirm-agent-input">
            补充任务要求
          </label>
          <textarea
            id="confirm-agent-input"
            onChange={(event) => setAgentInstruction(event.target.value)}
            placeholder="还可以补充语气、渠道或限制…"
            rows={3}
            value={agentInstruction}
          />
          <div className="composer-toolbar">
            <span className="composer-hint">补充内容会加入任务约束</span>
            <button
              className="composer-send"
              disabled={agentInstruction.trim().length < 2}
              type="submit"
            >
              ↑<span className="sr-only">补充要求</span>
            </button>
          </div>
        </form>
      </aside>
    </main>
  );
}

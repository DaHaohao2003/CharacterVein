"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { getConversationMessages, sendConversationMessage } from "@/lib/api";
import { toPublicCopy, toPublicToolName } from "@/lib/public-copy";
import type {
  ConversationMessage,
  ConversationTurn,
  Task,
  WorkflowEvent,
} from "@/lib/types";

type WorkspaceAgentPanelProps = {
  activeArtifactId?: string;
  acknowledging: boolean;
  error: string;
  events: WorkflowEvent[];
  onAcknowledge: () => Promise<void>;
  onExecute: (resume: boolean) => Promise<void>;
  onConversationTurn: (turn: ConversationTurn) => Promise<void>;
  onSelectRoute: (routeId: string) => Promise<void>;
  onStartNewTask: (requirement: string) => Promise<void>;
  running: boolean;
  selectingRoute: string;
  task: Task;
  bootstrapConversation?: boolean;
};

const STATUS_COPY: Record<string, { title: string; body: string }> = {
  awaiting_confirmation: {
    title: "会话已经建立",
    body: "可以直接提问、研究字形，或告诉我想生成什么内容；输出形式不受固定模板限制。",
  },
  confirmed: {
    title: "任务已经准备好",
    body: "我将依次规划、检索、观察字形、提出文化叙事路线，并生成传播内容。",
  },
  running: {
    title: "我正在处理这项任务",
    body: "下面会实时展示当前计划、工具动作和执行结果摘要。",
  },
  awaiting_route_selection: {
    title: "需要你决定文化切口",
    body: "资料探索已经完成。我提出了几条叙事路线，选定后我会从检查点继续。",
  },
  completed: {
    title: "这轮深度任务已经完成",
    body: "可以继续追问、修改当前作品，或把它转换成另一种传播形式。",
  },
  failed: {
    title: "执行暂时中断",
    body: "失败信息已经保留。告诉我“继续执行”，我会从最近检查点恢复。",
  },
};

export function WorkspaceAgentPanel({
  activeArtifactId,
  acknowledging,
  error,
  events,
  onAcknowledge,
  onConversationTurn,
  onExecute,
  onSelectRoute,
  onStartNewTask,
  running,
  selectingRoute,
  task,
  bootstrapConversation = false,
}: WorkspaceAgentPanelProps) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [messagesLoaded, setMessagesLoaded] = useState(false);
  const [conversationError, setConversationError] = useState("");
  const conversationRef = useRef<HTMLDivElement>(null);
  const bootstrapStarted = useRef(false);
  const statusCopy = STATUS_COPY[task.status] ?? {
    title: "任务状态已更新",
    body: "你可以继续在这里向我下达指令。",
  };

  useEffect(() => {
    let active = true;
    getConversationMessages(task.id)
      .then((items) => {
        if (active) setMessages(items);
      })
      .catch((reason: Error) => {
        if (active) setConversationError(reason.message);
      })
      .finally(() => {
        if (active) setMessagesLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [task.id]);

  useEffect(() => {
    if (
      !bootstrapConversation ||
      !messagesLoaded ||
      bootstrapStarted.current ||
      messages.length > 0
    )
      return;
    bootstrapStarted.current = true;
    setSending(true);
    sendConversationMessage(task.id, task.raw_input)
      .then(async (turn) => {
        setMessages([turn.user_message, turn.assistant_message]);
        await onConversationTurn(turn);
      })
      .catch((reason: Error) => setConversationError(reason.message))
      .finally(() => setSending(false));
  }, [
    bootstrapConversation,
    messagesLoaded,
    messages.length,
    onConversationTurn,
    task.id,
    task.raw_input,
  ]);

  useEffect(() => {
    const node = conversationRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [events.length, messages, running, task.status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    setConversationError("");

    try {
      if (/新任务|重新创作|换一个字/.test(message)) {
        await onStartNewTask(
          message.replace(/^(创建|开始)?新任务[：:]?/, "").trim() || message,
        );
        return;
      }
      const turn = await sendConversationMessage(
        task.id,
        message,
        activeArtifactId,
      );
      setMessages((current) => [
        ...current,
        turn.user_message,
        turn.assistant_message,
      ]);
      await onConversationTurn(turn);
    } catch (reason) {
      setConversationError(
        reason instanceof Error ? reason.message : "执行这条指令时遇到了问题。",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <aside
      className="agent-chat-panel workspace-agent-panel"
      aria-label="智能体对话与执行过程"
    >
      <header className="agent-chat-header">
        <div className="agent-avatar">脉</div>
        <div>
          <strong>字脉智能体</strong>
          <small>
            <span
              className={
                running || sending
                  ? "status-pulse"
                  : "status-dot status-dot--online"
              }
            />
            {running || sending ? "正在处理这条消息" : "等待你的指令"}
          </small>
        </div>
        <span className="agent-model-label">AGENT</span>
      </header>

      <div className="agent-conversation" ref={conversationRef}>
        {messages.length === 0 && (
          <article className="chat-message chat-message--user">
            <div>
              <p>{task.raw_input}</p>
            </div>
          </article>
        )}

        <article
          className={
            running
              ? "chat-message chat-message--assistant is-working"
              : "chat-message chat-message--assistant"
          }
        >
          <span className="chat-message-avatar">脉</span>
          <div>
            <strong>{statusCopy.title}</strong>
            <p>{statusCopy.body}</p>
            {running && (
              <span className="thinking-dots">
                <i />
                <i />
                <i />
              </span>
            )}
          </div>
        </article>

        {task.agent_runtime.decision_summary && (
          <article className="agent-reasoning-card">
            <header>
              <span>当前判断</span>
              <small>{task.agent_runtime.current_phase}</small>
            </header>
            <strong>{task.agent_runtime.next_action}</strong>
            <p>{toPublicCopy(task.agent_runtime.decision_summary)}</p>
          </article>
        )}

        {task.plan && (
          <details className="agent-process-card" open={running}>
            <summary>
              <span>
                <strong>执行计划</strong>
                <small>
                  {
                    task.plan.filter((step) => step.status === "completed")
                      .length
                  }{" "}
                  / {task.plan.length} 已完成
                </small>
              </span>
              <span aria-hidden="true">⌄</span>
            </summary>
            <ol className="agent-plan-timeline">
              {task.plan.map((step) => (
                <li className={`is-${step.status}`} key={step.id}>
                  <span className="agent-plan-dot" />
                  <div>
                    <strong>{step.title}</strong>
                    <small>
                      {step.agent}
                      {step.tool_names?.length
                        ? ` · ${step.tool_names.map(toPublicToolName).join(" / ")}`
                        : ""}
                    </small>
                    {step.summary && <p>{toPublicCopy(step.summary)}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </details>
        )}

        {events.length > 0 && (
          <details className="agent-process-card" open={running}>
            <summary>
              <span>
                <strong>实时执行过程</strong>
                <small>{events.length} 条状态记录</small>
              </span>
              <span aria-hidden="true">⌄</span>
            </summary>
            <ol className="agent-event-stream">
              {events.slice(-14).map((event) => (
                <li key={event.id}>
                  <span
                    className={`event-status event-status--${event.status}`}
                  />
                  <div>
                    <strong>{event.step}</strong>
                    <p>{toPublicCopy(event.summary)}</p>
                    <small>
                      {new Date(event.created_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </small>
                  </div>
                </li>
              ))}
            </ol>
          </details>
        )}

        {(task.tool_calls?.length ?? 0) > 0 && (
          <details className="agent-process-card agent-tool-card">
            <summary>
              <span>
                <strong>工具动作</strong>
                <small>{task.tool_calls?.length ?? 0} 次调用</small>
              </span>
              <span aria-hidden="true">⌄</span>
            </summary>
            {(task.tool_calls ?? []).slice(-10).map((call) => (
              <article key={call.tool_call_id}>
                <header>
                  <code>{call.tool_name}</code>
                  <span>{call.status}</span>
                </header>
                <p>{toPublicCopy(call.input_summary)}</p>
                <small>
                  {toPublicCopy(call.result_summary)} ·{" "}
                  {call.duration_ms.toFixed(0)} ms
                </small>
              </article>
            ))}
          </details>
        )}

        {task.status === "awaiting_route_selection" &&
          (task.narrative_routes?.length ?? 0) > 0 && (
            <section
              className="chat-route-selection"
              aria-label="选择文化叙事路线"
            >
              <span>需要你的决定</span>
              <h3>选择一个文化叙事切口</h3>
              <p>这会成为后续对话与传播作品的共同主线。</p>
              {(task.narrative_routes ?? []).map((route, index) => (
                <button
                  disabled={Boolean(selectingRoute)}
                  key={route.route_id}
                  onClick={() => void onSelectRoute(route.route_id)}
                  type="button"
                >
                  <span>路线 {index + 1}</span>
                  <strong>{route.title}</strong>
                  <small>{toPublicCopy(route.core_message)}</small>
                  <em>
                    {selectingRoute === route.route_id ? "正在继续…" : "选择 →"}
                  </em>
                </button>
              ))}
            </section>
          )}

        {task.requires_user_confirmation && (
          <section className="chat-confirmation-card">
            <span>需要你的确认</span>
            <strong>当前参考资料比较有限</strong>
            <p>继续后，大模型会参考目前获得的内容生成，不执行逐句事实核验。</p>
            <button
              disabled={acknowledging}
              onClick={() => void onAcknowledge()}
              type="button"
            >
              {acknowledging ? "确认中…" : "接受并继续"}
            </button>
          </section>
        )}

        {task.status === "confirmed" && (
          <button
            className="chat-primary-action"
            disabled={running}
            onClick={() => void onExecute(false)}
            type="button"
          >
            <span>▶</span>
            <span>
              <strong>开始执行任务</strong>
              <small>智能体将自主完成资料探索与内容生成</small>
            </span>
          </button>
        )}

        {task.status === "failed" && (
          <button
            className="chat-primary-action"
            disabled={running}
            onClick={() => void onExecute(true)}
            type="button"
          >
            <span>↻</span>
            <span>
              <strong>从检查点恢复</strong>
              <small>保留已经完成的步骤</small>
            </span>
          </button>
        )}

        {messages.map((message) => (
          <article
            className={`chat-message chat-message--${message.role}`}
            key={message.id}
          >
            {message.role === "assistant" && (
              <span className="chat-message-avatar">脉</span>
            )}
            <div>
              <p>{message.content}</p>
              {message.role === "assistant" && message.state.action_summary && (
                <small className="chat-action-summary">
                  {message.state.action_summary}
                </small>
              )}
              {message.role === "assistant" &&
                (message.state.tools_used?.length ?? 0) > 0 && (
                  <span className="chat-tool-summary">
                    {message.state.tools_used?.map((tool) => (
                      <em key={tool}>{toPublicToolName(tool)}</em>
                    ))}
                  </span>
                )}
            </div>
          </article>
        ))}
        {sending && (
          <article className="chat-message chat-message--assistant is-working">
            <span className="chat-message-avatar">脉</span>
            <div>
              <p>正在理解这条消息，并决定是否需要字形、网络资料或当前作品……</p>
              <span className="thinking-dots">
                <i />
                <i />
                <i />
              </span>
            </div>
          </article>
        )}
        {(conversationError || error || task.error_message) && (
          <p className="agent-chat-error">
            {toPublicCopy(conversationError || error || task.error_message)}
          </p>
        )}
      </div>

      <form
        className="agent-composer agent-composer--compact"
        onSubmit={submit}
      >
        <label className="sr-only" htmlFor="workspace-agent-input">
          向字脉智能体下达指令
        </label>
        <textarea
          id="workspace-agent-input"
          onChange={(event) => setInput(event.target.value)}
          placeholder={"提问、研究字形、生成任意内容，或继续修改当前作品…"}
          rows={3}
          value={input}
        />
        <div className="composer-toolbar">
          <span className="composer-hint">
            Enter 发送 · 可连续追问、创作、修改或转换形式
          </span>
          <button
            className="composer-send"
            disabled={sending || input.trim().length < 1}
            type="submit"
          >
            {sending ? "…" : "↑"}
            <span className="sr-only">发送指令</span>
          </button>
        </div>
      </form>
    </aside>
  );
}

"use client";

import Link from "next/link";

export type PrimarySection = "home" | "research" | "communication";
export type WorkspaceView = "evolution" | "sources" | "output" | "task";

type AppNavigationProps = {
  active: PrimarySection;
  character?: string;
  onSectionChange?: (section: Exclude<PrimarySection, "home">) => void;
  status?: string;
  taskId?: string;
};

const STATUS_LABELS: Record<string, string> = {
  awaiting_confirmation: "对话进行中",
  confirmed: "准备执行",
  running: "智能体执行中",
  awaiting_route_selection: "等待选择路线",
  completed: "任务已完成",
  failed: "执行遇到问题",
};

const PRIMARY_ITEMS: Array<{
  id: PrimarySection;
  icon: string;
  label: string;
  description: string;
}> = [
  { id: "home", icon: "首", label: "首页", description: "开始与管理任务" },
  {
    id: "research",
    icon: "研",
    label: "汉字研究",
    description: "字形、资料与文化语境",
  },
  {
    id: "communication",
    icon: "传",
    label: "文化传播",
    description: "生成、修改与转换作品",
  },
];

function sectionHref(section: PrimarySection, taskId?: string): string {
  if (section === "home") return "/";
  if (!taskId) return section === "research" ? "/research" : "/communication";
  return section === "research"
    ? `/tasks/${taskId}/workspace?space=research&view=evolution`
    : `/tasks/${taskId}/workspace?space=communication&view=output`;
}

export function AppNavigation({
  active,
  character,
  onSectionChange,
  status,
  taskId,
}: AppNavigationProps) {
  return (
    <aside className="app-navigation" aria-label="字脉主导航">
      <div className="app-brand">
        <span className="app-brand-mark" aria-hidden="true">
          脉
        </span>
        <span>
          <strong>字脉</strong>
          <small>汉字文化传播智能体</small>
        </span>
      </div>

      <Link aria-label="开始新任务" className="app-new-task" href="/">
        <span aria-hidden="true">＋</span>
        <span>
          <strong>开始新任务</strong>
          <small>从一个问题或汉字开始</small>
        </span>
      </Link>

      <nav className="app-nav-primary" aria-label="主要功能">
        {PRIMARY_ITEMS.map((item) => {
          const content = (
            <>
              <span className="app-nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="app-nav-copy">
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </span>
            </>
          );
          const className = active === item.id ? "is-active" : "";
          const taskSection =
            item.id === "research" || item.id === "communication"
              ? item.id
              : null;
          if (taskSection && taskId && onSectionChange) {
            return (
              <button
                aria-label={item.label}
                className={className}
                key={item.id}
                onClick={() => onSectionChange(taskSection)}
                type="button"
              >
                {content}
              </button>
            );
          }
          return (
            <Link
              aria-label={item.label}
              className={className}
              href={sectionHref(item.id, taskId)}
              key={item.id}
            >
              {content}
            </Link>
          );
        })}
      </nav>

      {taskId && (
        <section className="app-current-task" aria-label="当前任务">
          <span>当前任务</span>
          <div>
            <strong>{character || "待确认"}</strong>
            <p>
              {character
                ? `正在围绕“${character}”持续研究与创作`
                : "等待确认研究汉字"}
            </p>
          </div>
        </section>
      )}

      <div className="app-nav-spacer" />
      {taskId && status && (
        <section className="agent-status-card">
          <span
            className={status === "running" ? "status-pulse" : "status-dot"}
          />
          <div>
            <strong>{STATUS_LABELS[status] ?? status}</strong>
            <small>研究与传播上下文已连接</small>
          </div>
        </section>
      )}
      <footer className="app-nav-footer">
        <span className="status-dot status-dot--online" />
        多模态模型 · 检索服务在线
      </footer>
    </aside>
  );
}

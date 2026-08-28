"use client";

import Link from "next/link";

export type WorkspaceView = "evolution" | "sources" | "output" | "task";

type AppNavigationProps = {
  active: "home" | "workspace" | "content";
  character?: string;
  currentView?: WorkspaceView;
  onViewChange?: (view: WorkspaceView) => void;
  status?: string;
  taskId?: string;
};

const STATUS_LABELS: Record<string, string> = {
  awaiting_confirmation: "对话创作中",
  confirmed: "准备执行",
  running: "智能体执行中",
  awaiting_route_selection: "等待选择路线",
  completed: "创作已完成",
  failed: "执行遇到问题",
};

const VIEW_ITEMS: Array<{
  id: WorkspaceView;
  icon: string;
  label: string;
}> = [
  { id: "evolution", icon: "字", label: "演化画布" },
  { id: "sources", icon: "源", label: "参考资料" },
  { id: "output", icon: "稿", label: "创作作品" },
  { id: "task", icon: "序", label: "任务概览" },
];

export function AppNavigation({
  active,
  character,
  currentView,
  onViewChange,
  status,
  taskId,
}: AppNavigationProps) {
  return (
    <aside className="app-navigation" aria-label="字脉导航">
      <div className="app-brand">
        <span className="app-brand-mark" aria-hidden="true">
          脉
        </span>
        <span>
          <strong>字脉</strong>
          <small>文化传播智能体</small>
        </span>
      </div>

      <nav className="app-nav-primary">
        <Link className={active === "home" ? "is-active" : ""} href="/">
          <span className="app-nav-icon">＋</span>
          新建创作
        </Link>
      </nav>

      {taskId && (
        <section className="app-nav-task">
          <div className="app-nav-section-title">
            <span>当前任务</span>
            {character && <strong>{character}</strong>}
          </div>
          <nav>
            {VIEW_ITEMS.map((item) =>
              onViewChange ? (
                <button
                  className={currentView === item.id ? "is-active" : ""}
                  key={item.id}
                  onClick={() => onViewChange(item.id)}
                  type="button"
                >
                  <span className="app-nav-icon">{item.icon}</span>
                  {item.label}
                </button>
              ) : (
                <Link
                  className={
                    active === "content" && item.id === "output"
                      ? "is-active"
                      : ""
                  }
                  href={
                    item.id === "output"
                      ? `/tasks/${taskId}/content`
                      : `/tasks/${taskId}/workspace?view=${item.id}`
                  }
                  key={item.id}
                >
                  <span className="app-nav-icon">{item.icon}</span>
                  {item.label}
                </Link>
              ),
            )}
          </nav>
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
            <small>任务 {taskId.slice(0, 8)}</small>
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

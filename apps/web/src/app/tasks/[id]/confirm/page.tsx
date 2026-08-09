"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

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

  if (!task || !spec) {
    return <main className="loading">{error || "正在载入任务…"}</main>;
  }

  const needsTarget =
    spec.target_needs_confirmation || !spec.target_characters.length;

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">任务确认</p>
        <h1>先确认字脉理解得是否准确</h1>
        <p>{task.raw_input}</p>
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
            <p>以下内容仅作为任务上下文，与系统检索并审校的证据分开保存。</p>
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
      <form className="spec-grid" onSubmit={submit}>
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
                event.target.value.split("\n").filter((item) => item.trim()),
              )
            }
          />
        </label>
        <div className="span-all actions">
          <button
            disabled={saving || !spec.target_characters.length}
            type="submit"
          >
            {saving ? "正在保存…" : "确认并进入工作台"}
          </button>
        </div>
        {error && <p className="span-all error">{error}</p>}
      </form>
    </main>
  );
}

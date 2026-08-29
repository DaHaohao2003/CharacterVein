import type {
  Asset,
  ContentVersion,
  CommunicationAsset,
  CommunicationAssetVersion,
  ConversationMessage,
  ConversationTurn,
  CreativeArtifact,
  GeneratedContent,
  GlyphImageSearchResult,
  Task,
  TaskSpec,
  WorkflowEvent,
} from "@/lib/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

export function createTask(
  rawInput: string,
  assetIds: string[] = [],
  webSearchEnabled = true,
): Promise<Task> {
  return request<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify({
      raw_input: rawInput,
      asset_ids: assetIds,
      web_search_enabled: webSearchEnabled,
    }),
  });
}

export async function uploadAsset(file: File): Promise<Asset> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/backend/api/v1/assets", {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `上传失败（${response.status}）`);
  }
  return (await response.json()) as Asset;
}

export function getAsset(assetId: string): Promise<Asset> {
  return request<Asset>(`/assets/${assetId}`);
}

export function getTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`);
}

export function confirmTask(taskId: string, spec: TaskSpec): Promise<Task> {
  return request<Task>(`/tasks/${taskId}/spec`, {
    method: "PUT",
    body: JSON.stringify({ spec }),
  });
}

export function runTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}/run`, { method: "POST" });
}

export function resumeTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}/resume`, { method: "POST" });
}

export function selectNarrativeRoute(
  taskId: string,
  routeId: string,
): Promise<Task> {
  return request<Task>(
    `/tasks/${taskId}/narrative-routes/${encodeURIComponent(routeId)}/select`,
    { method: "POST" },
  );
}

export function acknowledgeLimitations(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}/acknowledge-limitations`, {
    method: "POST",
  });
}

export function getEvents(taskId: string): Promise<WorkflowEvent[]> {
  return request<WorkflowEvent[]>(`/tasks/${taskId}/events`);
}

export function getConversationMessages(
  taskId: string,
): Promise<ConversationMessage[]> {
  return request<ConversationMessage[]>(
    `/tasks/${taskId}/conversation/messages`,
  );
}

export function sendConversationMessage(
  taskId: string,
  content: string,
  activeArtifactId?: string,
  activePageId?: string,
  activeBlockId?: string,
): Promise<ConversationTurn> {
  return request<ConversationTurn>(`/tasks/${taskId}/conversation/messages`, {
    method: "POST",
    body: JSON.stringify({
      content,
      active_artifact_id: activeArtifactId || null,
      active_page_id: activePageId || null,
      active_block_id: activeBlockId || null,
    }),
  });
}

export function getCreativeArtifacts(
  taskId: string,
): Promise<CreativeArtifact[]> {
  return request<CreativeArtifact[]>(`/tasks/${taskId}/creative-artifacts`);
}

export function creativeArtifactExportUrl(
  taskId: string,
  artifactId: string,
): string {
  return `/backend/api/v1/tasks/${taskId}/creative-artifacts/${artifactId}/export.md`;
}

export function richArtifactExportUrl(
  taskId: string,
  artifactId: string,
  format: "docx" | "html" | "txt" | "pdf" | "pptx",
): string {
  return `/backend/api/v1/tasks/${taskId}/creative-artifacts/${artifactId}/exports/${format}`;
}

export function searchGlyphImages(options: {
  character: string;
  scriptCode: string;
  scriptType: string;
  limit?: number;
}): Promise<GlyphImageSearchResult[]> {
  const params = new URLSearchParams({
    query: `${options.character} ${options.scriptType} 异体字形`,
    character: options.character,
    script_code: options.scriptCode,
    limit: String(options.limit ?? 200),
  });
  return request<GlyphImageSearchResult[]>(`/glyph-images/search?${params}`);
}

export function getContentVersions(taskId: string): Promise<ContentVersion[]> {
  return request<ContentVersion[]>(`/tasks/${taskId}/contents`);
}

export function regenerateCommunicationFragment(
  taskId: string,
  assetType: CommunicationAsset["asset_type"],
  targetIndex: number,
  instruction: string,
): Promise<CommunicationAssetVersion> {
  return request<CommunicationAssetVersion>(
    `/tasks/${taskId}/communication-assets/${assetType}/fragments/${targetIndex}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify({ instruction }),
    },
  );
}

export function regenerateContent(
  taskId: string,
  options: {
    audience: string;
    duration_minutes: number;
    output_type: TaskSpec["output_type"];
    interaction_count: number;
    mode: "full" | "body" | "interactions";
  },
): Promise<ContentVersion> {
  return request<ContentVersion>(`/tasks/${taskId}/regenerate`, {
    method: "POST",
    body: JSON.stringify(options),
  });
}

export function saveContent(
  taskId: string,
  version: number,
  content: GeneratedContent,
  changeSummary: string,
): Promise<ContentVersion> {
  return request<ContentVersion>(`/tasks/${taskId}/contents/${version}`, {
    method: "PUT",
    body: JSON.stringify({ content, change_summary: changeSummary }),
  });
}

export function activateContentVersion(
  taskId: string,
  version: number,
): Promise<ContentVersion> {
  return request<ContentVersion>(
    `/tasks/${taskId}/contents/${version}/activate`,
    { method: "POST" },
  );
}

export async function exportContent(
  taskId: string,
  format: "markdown" | "html" | "json",
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`/backend/api/v1/tasks/${taskId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `导出失败（${response.status}）`);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename =
    disposition.match(/filename="([^"]+)"/)?.[1] ?? `export.${format}`;
  return { blob: await response.blob(), filename };
}

export async function exportCommunicationPackage(
  taskId: string,
  format: "markdown" | "html" | "json",
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `/backend/api/v1/tasks/${taskId}/communication-package/exports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `传播包导出失败（${response.status}）`);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename =
    disposition.match(/filename="([^"]+)"/)?.[1] ??
    `communication-package.${format}`;
  return { blob: await response.blob(), filename };
}

export function exportUrl(taskId: string): string {
  return `/backend/api/v1/tasks/${taskId}/export.md`;
}

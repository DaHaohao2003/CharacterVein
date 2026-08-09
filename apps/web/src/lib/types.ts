export type TaskSpec = {
  target_characters: string[];
  theme: string;
  audience: string;
  duration_minutes: number;
  output_type: "interactive_lesson" | "culture_card" | "article_outline";
  required_stages: number;
  interaction_count: number;
  language: string;
  constraints: string[];
  source_contexts: string[];
  target_needs_confirmation: boolean;
};

export type AssetAnalysis = {
  target_characters: string[];
  extracted_text: string;
  artifact_names: string[];
  explicit_periods: string[];
  themes: string[];
  user_sources: string[];
  warnings: string[];
  uncertain_glyphs: boolean;
  requires_target_confirmation: boolean;
  model: string;
  fallback_used: boolean;
};

export type Asset = {
  id: string;
  task_id: string | null;
  origin: "user_upload";
  kind: "image" | "document";
  status: string;
  mime_type: string;
  filename: string;
  size_bytes: number;
  extracted_text: string;
  analysis: AssetAnalysis;
  error_message: string | null;
  created_at: string;
};

export type GlyphStage = {
  stage_id: string;
  character: string;
  script_type: string;
  script_code?: string;
  period: string;
  approximate_date: string;
  historical_period?: string;
  lineage_role: "mainline" | "branch" | "transition";
  region_or_system?: string;
  sample_date?: string;
  image_url?: string;
  image_id?: string;
  source_id: string;
  source_label: string;
  source_path?: string;
  image_attribution?: string;
  availability: "available" | "dataset_gap";
  structure_description: string;
  change_from_previous?: string;
  variant_type: string;
};

export type GlyphImageSearchResult = {
  id: string;
  character: string;
  codepoint: string;
  script_type: string;
  script_code: string;
  historical_period: string;
  lineage_role: "mainline" | "branch" | "transition";
  region_or_system?: string;
  source_path: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  metadata: {
    is_representative?: boolean;
    variant_index?: number;
    [key: string]: unknown;
  };
  score: number;
  content_url: string;
};

export type Source = {
  source_id: string;
  source_type: string;
  title: string;
  author_or_org: string;
  publication_date?: string;
  locator: string;
  url?: string;
  authority_level: string;
  license: string;
};

export type Evidence = {
  evidence_id: string;
  source_id: string;
  source_type: string;
  title: string;
  author_or_org: string;
  publication_date?: string;
  quote_or_summary: string;
  locator: string;
  url?: string;
  authority_level: string;
  license: string;
};

export type Claim = {
  claim_id: string;
  content: string;
  claim_type: string;
  evidence_ids: string[];
  evidence_grade: string;
  audit_status: string;
};

export type EvolutionPackage = {
  character: string;
  sources: Source[];
  glyph_stages: GlyphStage[];
  shape_changes: string[];
  meaning_changes: string[];
  cultural_contexts: string[];
  claims: Claim[];
  evidence: Evidence[];
  controversies: string[];
};

export type AuditReport = {
  status: "approved" | "needs_retry" | "partial";
  model: string;
  prompt_version: string;
  attempt: number;
  fallback_used: boolean;
  summary: string;
  issues: Array<{
    issue_code: string;
    claim_id?: string;
    message: string;
    severity: string;
    action: string;
    retryable: boolean;
  }>;
};

export type RetrievalSummary = {
  query_id: string;
  query: string;
  purpose: string;
  candidate_count: number;
  selected_count: number;
  structured_matches: number;
  exact_matches: number;
  keyword_matches: number;
  semantic_matches: number;
  channel_candidate_counts: Record<string, number>;
  attempt: number;
};

export type EvidenceSearchQuery = {
  query_id: string;
  query: string;
  purpose: string;
  character: string;
  script_type?: string;
  historical_period?: string;
  topic?: string;
};

export type ToolCall = {
  tool_call_id: string;
  tool_name: string;
  status: "running" | "completed" | "failed";
  input_summary: string;
  result_summary: string;
  result_count: number;
  duration_ms: number;
  attempt: number;
  error?: string;
};

export type GeneratedContent = {
  title: string;
  audience: string;
  duration_minutes: number;
  outline: string[];
  body_markdown: string;
  interaction_questions: string[];
  source_ids: string[];
  estimated_characters: number;
};

export type ConstraintResult = {
  passed: boolean;
  checks: Record<string, boolean>;
  messages: string[];
};

export type Task = {
  id: string;
  status: string;
  raw_input: string;
  spec: TaskSpec;
  plan: Array<{
    id: string;
    title: string;
    agent: string;
    status: string;
    summary: string;
    tool_names: string[];
    depends_on: string[];
    completion_criteria: string;
    failure_action: string;
  }> | null;
  search_queries: EvidenceSearchQuery[];
  tool_calls: ToolCall[];
  requires_user_confirmation: boolean;
  evolution_package: EvolutionPackage | null;
  generated_content: GeneratedContent | null;
  constraint_result: ConstraintResult | null;
  retrieval_summary: RetrievalSummary[] | null;
  audit_report: AuditReport | null;
  input_asset_ids: string[];
  current_content_version: number;
  error_message: string | null;
};

export type ContentVersion = {
  task_id: string;
  version: number;
  content: GeneratedContent;
  spec: TaskSpec;
  constraints: ConstraintResult;
  origin: "generated" | "regenerated" | "edited" | "restored";
  parent_version: number | null;
  evolution_hash: string;
  change_summary: string;
  created_at: string;
};

export type WorkflowEvent = {
  id: number;
  step: string;
  status: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

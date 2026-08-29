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
  web_search_enabled: boolean;
  communication_brief?: CommunicationBrief | null;
};

export type CommunicationBrief = {
  target_characters: string[];
  communication_goal: string;
  theme: string;
  audience: string;
  channels: Array<"interactive_page" | "social_cards" | "short_video_60s">;
  tone: string[];
  duration_seconds: number;
  deliverables: Array<"interactive_story" | "five_cards" | "video_script">;
  required_stages: number;
  interaction_count: number;
  success_criteria: string[];
  language: string;
  constraints: string[];
  source_contexts: string[];
  target_needs_confirmation: boolean;
  web_search_enabled: boolean;
};

export type NarrativeRoute = {
  route_id: string;
  title: string;
  core_message: string;
  opening_hook: string;
  visual_hooks: Array<{
    image_id: string;
    script_type: string;
    role: "opening" | "comparison" | "transition" | "interaction";
    prompt: string;
  }>;
  story_beats: string[];
  contemporary_connection: string;
  recommended_channels: CommunicationBrief["channels"];
  reference_ids: string[];
};

export type CulturalMotif = {
  source_route_id: string;
  title: string;
  core_message: string;
  opening_hook: string;
  visual_sequence: NarrativeRoute["visual_hooks"];
  story_beats: string[];
  contemporary_connection: string;
  audience_promise: string;
  tone: string[];
  reference_ids: string[];
};

export type InteractiveStoryContent = {
  title: string;
  lede: string;
  sections: Array<{
    section_id: string;
    title: string;
    narrative: string;
    visual_hook_id: string | null;
    interaction_prompt: string | null;
  }>;
  closing: string;
  interaction_questions: string[];
};

export type SocialCardsContent = {
  title: string;
  cards: Array<{
    index: number;
    headline: string;
    body: string;
    visual_hook_id: string | null;
    visual_direction: string;
  }>;
  posting_caption: string;
};

export type ShortVideoScriptContent = {
  title: string;
  duration_seconds: 60;
  opening_hook: string;
  scenes: Array<{
    start_second: number;
    end_second: number;
    visual: string;
    narration: string;
    subtitle: string;
    visual_hook_id: string | null;
  }>;
  closing_cta: string;
  full_narration: string;
};

export type CommunicationAsset =
  | {
      asset_type: "interactive_story";
      version: number;
      content: InteractiveStoryContent;
      reference_ids: string[];
      visual_hook_ids: string[];
      status: "generated" | "needs_revision" | "approved";
    }
  | {
      asset_type: "social_cards";
      version: number;
      content: SocialCardsContent;
      reference_ids: string[];
      visual_hook_ids: string[];
      status: "generated" | "needs_revision" | "approved";
    }
  | {
      asset_type: "short_video_script";
      version: number;
      content: ShortVideoScriptContent;
      reference_ids: string[];
      visual_hook_ids: string[];
      status: "generated" | "needs_revision" | "approved";
    };

export type CommunicationAssetVersion = {
  id: string;
  task_id: string;
  asset_type: CommunicationAsset["asset_type"];
  version: number;
  content: CommunicationAsset["content"];
  reference_ids: string[];
  visual_hook_ids: string[];
  parent_id: string | null;
  context_hash: string;
  status: CommunicationAsset["status"];
  evaluation: ArtifactEvaluation | null;
  created_at: string;
};

export type ArtifactEvaluation = {
  passed: boolean;
  checks: Record<string, boolean>;
  messages: string[];
  next_action:
    | "SEARCH_MORE"
    | "REWRITE_QUERY"
    | "RESELECT_GLYPH"
    | "BUILD_NARRATIVES"
    | "REWRITE_ASSET"
    | "ASK_USER"
    | "FINISH";
  retry_targets: string[];
};

export type ArtifactEvaluationPackage = {
  passed: boolean;
  assets: Partial<
    Record<
      "interactive_story" | "social_cards" | "short_video_script",
      ArtifactEvaluation
    >
  >;
  retry_targets: string[];
  messages: string[];
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
  source_url?: string;
  source_license?: string;
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
  origin: "web" | "user_upload" | "fixture";
  task_id?: string;
  asset_id?: string;
  retrieved_at?: string;
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
  origin: "web" | "user_upload" | "fixture";
  task_id?: string;
  asset_id?: string;
  metadata?: Record<string, unknown>;
  usability: "usable" | "partial" | "metadata_only" | "unusable";
  retrieved_at?: string;
};

export type Claim = {
  claim_id: string;
  content: string;
  claim_type: string;
  evidence_ids: string[];
  evidence_grade: string;
  audit_status: string;
  claim_origin: "evidence_derived" | "hypothesis" | "system_synthesis";
  evidence_relations: Array<{
    evidence_id: string;
    support_type:
      "supports" | "partially_supports" | "contradicts" | "context_only";
  }>;
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
  visual_analysis?: {
    character: string;
    stage_observations: Array<{
      image_id: string;
      script_type: string;
      visible_features: string[];
      composition: string;
      stroke_form: string;
    }>;
    comparisons: Array<{
      from_image_id: string;
      to_image_id: string;
      visible_changes: string[];
      summary: string;
    }>;
    overall_summary: string;
    warnings: string[];
    model: string;
    fallback_used: boolean;
  } | null;
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
  provider: string;
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

export type ConversationIntent =
  "answer" | "explore" | "create" | "revise" | "transform" | "clarify";

export type ConversationMessage = {
  id: string;
  task_id: string;
  role: "user" | "assistant";
  content: string;
  intent: ConversationIntent | null;
  state: {
    action_summary?: string;
    workspace_view?: "conversation" | "evolution" | "sources" | "artifact";
    tools_used?: string[];
    artifact_id?: string | null;
    web_sources?: Array<{ title: string; url: string; site_name?: string }>;
    [key: string]: unknown;
  };
  created_at: string;
};

export type CreativeArtifact = {
  id: string;
  task_id: string;
  lineage_id: string;
  parent_id: string | null;
  artifact_type: string;
  format_label: string;
  title: string;
  summary: string;
  content_markdown: string;
  rich_document: RichArtifactDocument;
  version: number;
  reference_ids: string[];
  visual_hook_ids: string[];
  status: string;
  created_at: string;
};

export type RichBlockKind =
  "heading" | "paragraph" | "list" | "quote" | "image" | "caption";

export type RichContentBlock = {
  block_id: string;
  kind: RichBlockKind;
  text: string;
  level: number | null;
  image_id: string | null;
  image_url: string | null;
  alt_text: string;
  caption: string;
  source_kind: "glyph" | "generated" | "upload" | null;
  locked: boolean;
};

export type RichContentPage = {
  page_id: string;
  title: string;
  layout: "cover" | "feature" | "split" | "text" | "gallery";
  blocks: RichContentBlock[];
};

export type RichArtifactDocument = {
  schema_version: "1.0";
  title: string;
  theme: "character-vein" | "museum" | "ink" | "classroom" | "minimal";
  pages: RichContentPage[];
  supported_formats: Array<"docx" | "html" | "txt" | "pdf" | "pptx">;
};

export type ConversationTurn = {
  intent: ConversationIntent;
  action_summary: string;
  workspace_view: "conversation" | "evolution" | "sources" | "artifact";
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
  artifact: CreativeArtifact | null;
  tools_used: string[];
};

export type Task = {
  id: string;
  status: string;
  raw_input: string;
  spec: TaskSpec;
  communication_brief: CommunicationBrief;
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
  agent_runtime: {
    current_phase?: string;
    next_action?: string;
    decision_summary?: string;
    allowed_actions?: string[];
    budgets?: Record<string, number>;
    exploration_history?: Array<Record<string, unknown>>;
  };
  narrative_routes: NarrativeRoute[];
  selected_route_id: string | null;
  cultural_motif: CulturalMotif | null;
  communication_assets: Partial<
    Record<
      "interactive_story" | "social_cards" | "short_video_script",
      CommunicationAsset
    >
  >;
  artifact_evaluation: ArtifactEvaluationPackage | null;
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

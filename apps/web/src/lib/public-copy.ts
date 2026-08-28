const GLYPH_IDENTIFIER =
  /(?:U\+[0-9A-F]{4,6}(?:\/[JBGSLKC])?(?:\/[\w.-]+)?|\b[JBGSLKC]\d{3,}\b)/gi;
const SCRIPT_BY_CODE: Record<string, string> = {
  J: "甲骨文",
  B: "金文",
  G: "战国文字",
  S: "篆书",
  L: "隶书",
  K: "楷书",
  C: "草书",
};

const PUBLIC_TOOL_NAMES: Record<string, string> = {
  search_evidence: "查找参考资料",
  search_glyphs: "读取历代字形",
  analyze_glyphs: "观察字形图片",
  create_artifact: "生成或更新作品",
  build_narratives: "整理传播切口",
  build_cultural_motif: "整理文化主题",
  generate_communication_asset: "生成传播内容",
  evaluate_communication_asset: "检查内容要求",
  generate_content: "生成内容",
  check_constraints: "检查任务要求",
};

export function toPublicToolName(value: string): string {
  return PUBLIC_TOOL_NAMES[value] ?? "处理当前任务";
}

/** Keep storage and retrieval metadata internal when rendering agent-facing copy. */
export function toPublicCopy(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/JieZi(?:-Dataset)?/gi, "字形资料库")
    .replace(/image[_ ]?id\s*[=:：]\s*[^；，。\s]+/gi, "字形样本")
    .replace(/(?:图片|图像)(?:编号|ID)\s*[=:：]?\s*[^；，。\s]+/gi, "字形样本")
    .replace(/(?:图片|图像)\s*ID/gi, "字形样本")
    .replace(/原始路径\s*[：:]\s*[^；，。\n]+/g, "")
    .replace(/书体代码\s*=\s*([JBGSLKC])/g, (_, code: string) => {
      return `书体=${SCRIPT_BY_CODE[code] ?? "指定书体"}`;
    })
    .replace(GLYPH_IDENTIFIER, "字形样本")
    .replace(/元数据/g, "资料记录")
    .replace(/\s{2,}/g, " ")
    .trim();
}

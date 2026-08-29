export type CommunicationFormat = {
  id: string;
  icon: string;
  title: string;
  category: string;
  description: string;
  deliverable: string;
  prompt: string;
};

export const COMMUNICATION_FORMATS: readonly CommunicationFormat[] = [
  {
    id: "culture-article",
    icon: "文",
    title: "文化文章",
    category: "图文内容",
    description: "把字形观察与文化背景组织成适合特定读者的完整文章。",
    deliverable: "标题、导语、正文结构与结尾",
    prompt: "围绕一个汉字写一篇面向中学生的文化文章",
  },
  {
    id: "audio-script",
    icon: "声",
    title: "讲解与播客稿",
    category: "声音脚本",
    description: "将研究内容转化为适合口述、导览或音频节目的叙事。",
    deliverable: "开场、完整口播、节奏提示与收束",
    prompt: "根据汉字研究内容生成一份三分钟播客稿",
  },
  {
    id: "visual-cards",
    icon: "图",
    title: "图文卡片方案",
    category: "视觉策划",
    description: "规划多张文化卡片的文案、字形使用位置与画面方向。",
    deliverable: "逐卡文案、真实字形位置与配图建议",
    prompt: "把一个汉字的研究内容设计成五张文化图文卡片",
  },
  {
    id: "learning-content",
    icon: "课",
    title: "教育内容",
    category: "学习活动",
    description: "根据年龄、场景和时长生成课堂活动或公共教育讲解。",
    deliverable: "学习目标、讲解流程、互动问题与总结",
    prompt: "设计一项面向初中生的汉字文化课堂活动",
  },
  {
    id: "video-script",
    icon: "影",
    title: "视频脚本",
    category: "脚本作品",
    description: "把文化主题组织为可继续制作的分镜、旁白、字幕与画面方案。",
    deliverable: "开场钩子、分镜、旁白、字幕与素材建议",
    prompt: "制作一份六十秒汉字文化视频脚本，包含分镜、旁白和字幕",
  },
] as const;

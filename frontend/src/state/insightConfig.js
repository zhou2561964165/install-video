// v3 目标语言配置：加语言只改这里，不改组件结构或请求逻辑。
export const SUMMARY_SUPPORT_NOTICE = '支持有长度上限的长文总结；处理可能需要较长时间，请对照原字幕核对结果。';
export const INSIGHT_TABS = [
  { key: 'summary', label: '总结摘要', action: '生成总结', empty: '生成总结后，这里会显示内容概览和关键要点。' },
  { key: 'subtitle', label: '字幕文本', action: '查看字幕', empty: '读取字幕后，这里会显示来源提供的完整文本。' },
  { key: 'translation', label: '字幕翻译', action: '翻译字幕', empty: '选择输出语言并翻译后，这里会显示字幕译文。' },
  { key: 'transcription', label: '音频转写', action: '转写音频', empty: '从视频音频识别原文；本地转写可能需要较长时间。结果独立保留，不会替代平台字幕。' },
  { key: 'mindmap', label: '思维导图', action: '生成导图', empty: '基于平台字幕生成可折叠的主题结构，便于梳理内容。请对照字幕核对结果。' },
];

export const TARGET_LANGUAGES = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
];

// ASR identifies the spoken language; writing variants belong to translation.
export const TRANSCRIPTION_LANGUAGES = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
];
export const TIMELINE_PAGE_SIZE = 100;

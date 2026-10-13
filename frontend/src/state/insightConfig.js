// v3 目标语言配置：加语言只改这里，不改组件结构或请求逻辑。
export const SUMMARY_SUPPORT_NOTICE = '当前支持短篇和中篇总结，长文总结暂不支持。';
export const INSIGHT_TABS = [
  { key: 'summary', label: '总结摘要', action: '生成总结', empty: '生成总结后，这里会显示内容概览和关键要点。' },
  { key: 'subtitle', label: '字幕文本', action: '查看字幕', empty: '读取字幕后，这里会显示来源提供的完整文本。' },
  { key: 'translation', label: '字幕翻译', action: '翻译字幕', empty: '选择输出语言并翻译后，这里会显示字幕译文。' },
];

export const TARGET_LANGUAGES = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
];

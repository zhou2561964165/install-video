import type { ThemeConfig } from 'antd';

// Approved project palette: primitive → semantic → Ant component tokens.
export const primitive = {
  blue600: '#345ed5', blue700: '#294bb2', gray100: '#f1f4fa', gray900: '#202536',
  fontBody: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
} as const;
export const semantic = {
  primary: primitive.blue600, primaryHover: primitive.blue700,
  background: primitive.gray100, text: primitive.gray900, font: primitive.fontBody,
} as const;
export const adminTheme: ThemeConfig = {
  token: {
    colorPrimary: semantic.primary, colorPrimaryHover: semantic.primaryHover,
    colorBgLayout: semantic.background, colorText: semantic.text, fontFamily: semantic.font,
  },
  cssVar: { key: 'install-video-admin' },
};

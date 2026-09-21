import { SCENE } from '../state/sceneMachine.js';

// 模型实际拥有的 expression（P-4：无「哭哭」，改用现有文件）
export const EXPRESSION_NAMES = ['圈圈', '脸红', '葱', '唱歌', '比心', '前倾', 'QQ人'];

export const SCENE_MASCOT = {
  [SCENE.ENTRY]:       { expression: null,  motion: 'idle', sway: false, run: false },
  [SCENE.PARSING]:     { expression: '圈圈', motion: 'idle', sway: true,  run: false },
  [SCENE.SELECTING]:   { expression: '脸红', motion: 'idle', sway: false, run: false },
  [SCENE.DOWNLOADING]: { expression: null,  motion: 'idle', sway: false, run: true  },
  [SCENE.DONE]:        { expression: '比心', motion: null,  sway: false, run: false },
  [SCENE.ERROR]:       { expression: '圈圈', motion: null,  sway: false, run: false },
};

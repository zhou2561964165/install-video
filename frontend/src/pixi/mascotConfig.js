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

// 模型注册表：新增模型 = 放一个模型文件夹到 public/live2d/<id>/ 并在这里加一条，
// 切换 UI 与渲染层都会自动感知，无需改渲染代码。
//   id    —— 唯一标识，也是 public/live2d/<id>/ 的目录名
//   name  —— 切换 UI 里显示的名称
//   url   —— 模型入口（.model3.json）
//   scale —— 模型缩放
//   x/y   —— 相对屏幕宽高的占比（0~1），决定角色摆放位置
//   scene —— 可选：当该模型的 expression/motion 名与共享默认 SCENE_MASCOT 不同时，
//            在这里按场景覆盖（键为 SCENE.*，值为 { expression, motion, sway, run }）
export const MODELS = [
  {
    id: 'miku',
    name: '初音未来',
    url: '/live2d/miku/miku.model3.json',
    scale: 0.28,
    x: 0.82,
    y: 0.62,
  },
];

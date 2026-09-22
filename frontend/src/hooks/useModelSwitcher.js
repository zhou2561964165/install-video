import { useCallback, useRef, useState } from 'react';
import { MODELS, DEFAULT_MODEL_ID } from '../pixi/mascotConfig.js';
import { playSfx } from '../audio/audioManager.js';

const TOAST_MS = 2600;

// 模型切换的状态管理（React 侧）。点击切换发生在 PIXI 画布（Live2D 模型）上，
// pixi 层完成切换动画后通过 onModelChange 回调同步回来；这里负责：
//   - 持有当前模型 id（初始 DEFAULT_MODEL_ID）
//   - 切换成功时更新 id + 弹提示 + 播放 select SFX
// 返回 { modelId, toast, onModelChange }。
export function useModelSwitcher() {
  const [modelId, setModelId] = useState(DEFAULT_MODEL_ID);
  const [toast, setToast] = useState(null);
  const timerRef = useRef(null);

  const onModelChange = useCallback((nextId) => {
    const next = MODELS.find((m) => m.id === nextId) || MODELS[0];
    setModelId(next.id);
    setToast(`已切换为「${next.name}」`);
    playSfx('select');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  return { modelId, toast, onModelChange };
}

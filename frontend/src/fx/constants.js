// 动效 / 交互共享常量：时长、缓动、粒子参数。
// 所有动画参数集中在此，组件 / pixi 层不得写死数字（Task 2 要求）。
// 缓动：t ∈ [0,1] → 归一化进度
export const EASE = {
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inCubic: (t) => t * t * t,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
};

// Live2D 模型切换动画参数
export const MODEL_SWITCH_FX = {
  fadeOut: 160,     // 旧模型淡出时长（ms）
  fadeIn: 240,      // 新模型淡入时长（ms）
  burstCount: 22,   // 切换爆散粒子数
  burstSpeed: 5,    // 爆散粒子初速（px/帧）
  burstDecay: 0.92, // 爆散粒子每帧速度衰减
  burstLife: 36,    // 爆散粒子存活帧数
  ringRadius: 170,  // 光环最大扩散半径（px）
};

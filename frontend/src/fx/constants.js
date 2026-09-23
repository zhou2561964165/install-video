// 动效 / 交互共享常量：时长、缓动、粒子参数。
// 所有动画参数集中在此，组件 / pixi 层不得写死数字（Task 2 要求）。
// 缓动：t ∈ [0,1] → 归一化进度
export const EASE = {
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inCubic: (t) => t * t * t,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
};

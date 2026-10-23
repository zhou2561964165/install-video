import { appPath } from '../lib/appBase.js';

// 模型注册表：新增模型 = 将模型文件放到 public/<assetPath>/ 并在这里加一条，
// 切换 UI 与渲染层都会自动感知，无需改渲染代码。
//   id          —— 稳定唯一标识，升级资源目录时保持不变
//   assetPath   —— 带版本的资源目录；入口与其相对资源一起换址，避免旧错误响应缓存
//   name        —— 切换 UI 里显示的名称
//   url         —— 相对 assetPath 的模型入口（.model3.json），导出时统一加应用前缀
//   heightRatio —— free模式中的视口高度比例；显式embedded兼容使用区域contain。
//                 0.49 ≈ 白自然高 1680 × 0.28（470px）÷ 27 寸（2560×1440 @150%）全屏高 960px。
//   x/y         —— 相对屏幕宽高的占比（0~1），决定角色摆放位置（渲染与兜底图共用，勿写死）
//   fallback    —— Live2D 加载失败时的静态兜底图 { url }（与主模型一致，按 heightRatio 等比缩放）
//   hit         —— 点击热区兜底盒（模型局部坐标，锚点居中）；getLocalBounds 退化时使用
export const MODELS = [
  {
    id: 'bai',
    name: '白',
    assetPath: 'live2d/bai-v1',
    url: '白.model3.json',
    textureSize: 16384,
    heightRatio: 0.49,
    x: 0.82,
    y: 0.62,
    // 窄屏采用更小的视口高度比例，避免遮挡主要操作。
    mobile: { maxWidth: 720, heightRatio: 0.2, x: 0.5, y: 0.5 },
    fallback: { url: '白.16384/texture_00.png' },
    hit: { width: 1400, height: 2000 },
  },
].map((model) => ({
  ...model,
  url: appPath(`${model.assetPath}/${model.url}`),
  ...(model.fallback && { fallback: { ...model.fallback, url: appPath(`${model.assetPath}/${model.fallback.url}`) } }),
}));

// 默认模型 id：切换状态、兜底、初始加载统一从这里取，避免在组件内写死 'bai'
export const DEFAULT_MODEL_ID = MODELS[0].id;

// 模型布局选择保持配置驱动：渲染与静态兜底共用同一入口，新增断点不改摆放算法。
export function getModelLayout(model, viewportWidth) {
  return model.mobile && viewportWidth <= model.mobile.maxWidth ? model.mobile : model;
}

// 默认独立于文档的视口活动；embedded仅供显式旧调用兼容。
export const PLACEMENT = { mode: 'free', x: 0.5, y: 0.5, paddingRatio: 0.04, dragThreshold: 3, touchAction: 'pan-y pinch-zoom', modelTouchAction: 'pinch-zoom', autoPreventDefault: false };
// 渲染层必须传入当前完整bounds推导的placement，约束全部可见范围。
export function getDraggedModelPosition(position, viewport, placement) {
  if (placement) return {
    x: Math.min(placement.maxX, Math.max(placement.minX, position.x)),
    y: Math.min(placement.maxY, Math.max(placement.minY, position.y)),
  };
  const pad = Math.min(viewport.width, viewport.height) * PLACEMENT.paddingRatio;
  return {
    x: Math.min(viewport.width - pad, Math.max(pad, position.x)),
    y: Math.min(viewport.height - pad, Math.max(pad, position.y)),
  };
}

export function getModelPlacement(model, viewport, bounds, scaleFactor, region, { mode = PLACEMENT.mode, pivot = { x: 0, y: 0 } } = {}) {
  if (mode === 'embedded') {
    const valid = region && ['left', 'top', 'width', 'height'].every((key) => Number.isFinite(region[key])) && region.width > 0 && region.height > 0 && bounds.width > 0 && bounds.height > 0;
    if (!valid) return { scale: 0, x: 0, y: 0, minX: 0, maxX: 0, minY: 0, maxY: 0, visible: false };
    const pad = Math.min(region.width, region.height) * PLACEMENT.paddingRatio;
    const fraction = Math.min(1, Math.max(SCALE.min / SCALE.max, scaleFactor / SCALE.max));
    const scale = Math.min((region.width - pad * 2) / bounds.width, (region.height - pad * 2) / bounds.height) * fraction;
    const left = ((bounds.x ?? -bounds.width / 2) - pivot.x) * scale;
    const top = ((bounds.y ?? -bounds.height / 2) - pivot.y) * scale;
    const right = left + bounds.width * scale, bottom = top + bounds.height * scale;
    const minX = region.left + pad - left, maxX = region.left + region.width - pad - right;
    const minY = region.top + pad - top, maxY = region.top + region.height - pad - bottom;
    const x = region.left + region.width * PLACEMENT.x - (left + right) / 2;
    const y = region.top + region.height * PLACEMENT.y - (top + bottom) / 2;
    return { scale, x: Math.min(maxX, Math.max(minX, x)), y: Math.min(maxY, Math.max(minY, y)), minX, maxX, minY, maxY,
      visible: region.left < viewport.width && region.left + region.width > 0 && region.top < viewport.height && region.top + region.height > 0 };
  }
  const layout = getModelLayout(model, viewport.width);
  const area = { left: 0, top: 0, width: viewport.width, height: viewport.height };
  const pad = Math.min(area.width, area.height) * PLACEMENT.paddingRatio;
  const desiredHeight = viewport.height * layout.heightRatio * scaleFactor;
  const scale = Math.min(desiredHeight / bounds.height, (area.width - pad * 2) / bounds.width, (area.height - pad * 2) / bounds.height);
  const left = ((bounds.x ?? -bounds.width / 2) - pivot.x) * scale;
  const top = ((bounds.y ?? -bounds.height / 2) - pivot.y) * scale;
  const right = left + bounds.width * scale, bottom = top + bounds.height * scale;
  const minX = pad - left, maxX = viewport.width - pad - right;
  const minY = pad - top, maxY = viewport.height - pad - bottom;
  const x = viewport.width * layout.x - (left + right) / 2;
  const y = viewport.height * layout.y - (top + bottom) / 2;
  return { scale, x: Math.min(maxX, Math.max(minX, x)), y: Math.min(maxY, Math.max(minY, y)),
    minX, maxX, minY, maxY,
    visible: bounds.width > 0 && bounds.height > 0 && viewport.width > 0 && viewport.height > 0 };
}

export function supportsModelTexture(model, maxTextureSize) {
  return !model.textureSize || maxTextureSize >= model.textureSize;
}

// 程序化待机动画配置：「白」的 model3.json 的 Motions 只挂了 edle 装饰特效（单个星光特效，
// 无呼吸/待机动作），且无 Breath 字段，角色本身不会自动呼吸/摆动，故用正弦逐帧
// 驱动 coreModel 参数补上「呼吸 + 头部轻微摆动」。参数名/振幅/频率/相位全部在此，渲染层不写死。
//   params   —— 待驱动的 Live2D 参数列表：id 为参数名（运行时按模型真实参数过滤，缺失自动跳过）；
//               base 为中性值，amplitude 为摆动幅度，frequency 为每秒周期数，phase 为相位
//               （错开各参数，避免同步抖动）。
//   注意：只驱动「物理输入」参数（ParamAngleX/Y/Z、ParamBreath 在 physics3.json 里是 Input），
//   头摆会经物理级联出身体/头发摆动；ParamBodyAngleX 是物理 Output（每帧被物理覆写），不可驱动。
//   fallback —— 仅free无匹配参数时退化为scale呼吸；embedded静止，保持稳定热区。
export const IDLE = {
  params: [
    { id: 'ParamAngleX', base: 0, amplitude: 5, frequency: 0.35, phase: 0 },
    { id: 'ParamAngleY', base: 0, amplitude: 3, frequency: 0.22, phase: 1.2 },
    { id: 'ParamAngleZ', base: 0, amplitude: 2, frequency: 0.18, phase: 2.4 },
    { id: 'ParamBreath', base: 0.5, amplitude: 0.5, frequency: 0.25, phase: 0 },
  ],
  fallback: { scale: 0.015, frequency: 0.3 },
};

// 模型等比缩放配置：菜单「变大/变小」按 step 倍率累积，clamp 到 [min,max]；
// initial 为初始倍率；embedded最大值对应区域contain容量，free相对视口默认高度。
// 改这里调步长/边界/初始值，不改渲染逻辑。
export const SCALE = { step: 1.2, min: 0.5, max: 2.0, initial: 1.0 };

// 表情/道具配置：「白」完整版带 46 个 .exp3.json，每个 = 单参数 Value=1（Add 混合）。
// 标准 expression manager 是单选（一次一个 currentExpression），无法「换发型+换衣服+戴耳机」并存，
// 因此这里走「直接写参数」：paramId 置 1 开 / 0 关，可任意多选并存。参数名全部在此，渲染层不写死。
//   stage   —— 下载阶段 → 情绪眼（单选，入口无映射则不显示）
//   random  —— 随机道具：每 interval 毫秒从 pool 随机取一个展示 duration 毫秒后收回
//   menu    —— 点击角色弹出的功能菜单分组
//              mode: single = 组内互斥；toggle = 开关；multi = 独立复选
//   46 个表情已全部暴露：睫毛/眼镜/头发/头部装饰/身体装饰颜色 →「颜色」组（multi）；
//   创可贴×4 →「配饰」组；黑脸/血迹/哭/脸红 →「情绪」组（multi）。往 menu / random.pool 加一行即可继续扩展。
export const EXPRESSIONS = {
  stage: {
    parsing: { paramId: 'Param40', name: '圈圈眼' },
    selecting: { paramId: 'Param38', name: '煎蛋眼' },
    downloading: { paramId: 'Param40', name: '圈圈眼' },
    done: { paramId: 'Param41', name: '星星眼' },
    error: { paramId: 'Param43', name: '生气' },
  },
  random: {
    pool: [
      { paramId: 'Param35', name: '拿手柄' },
      { paramId: 'Param32', name: '拿话筒' },
      { paramId: 'Param31', name: '戳脸' },
    ],
    interval: 20000, // 每 ~20s 随机展示一次
    duration: 4000,  // 展示 ~4s 后收回
  },
  effect: {
    // 装饰特效（edle.motion3.json，Loop=true）：单个「星光闪烁」循环特效——
    // 白.model3.json 的 Motions 仅挂这一个文件、且该文件无 Motions 数组，并非多特效。
    // 命中 stages 的场景循环播放，其余场景 stopAllMotions。数据驱动，改 stages 即调整触发时机。
    motion: { group: 'edle', index: 0 },
    stages: ['done', 'error'],
  },
  menu: [
    {
      key: 'hair',
      label: '发型',
      mode: 'single',
      options: [
        { name: '短发', paramId: 'Param49' },
        { name: '披发', paramId: 'Param69' },
        { name: '刘海切换', paramId: 'Param66' },
        { name: '左鬓发', paramId: 'Param67' },
        { name: '右鬓发', paramId: 'Param68' },
        { name: '左马尾', paramId: 'Param62' },
        { name: '右马尾', paramId: 'Param63' },
        { name: '左啾啾', paramId: 'Param64' },
        { name: '右啾啾', paramId: 'Param65' },
      ],
    },
    {
      key: 'clothes',
      label: '衣服',
      mode: 'single',
      options: [
        { name: '衣服颜色1', paramId: 'Param72' },
        { name: '衣服颜色2', paramId: 'Param73' },
        { name: '围裙', paramId: 'Param48' },
        { name: '绷带', paramId: 'Param93' },
      ],
    },
    {
      key: 'size',
      label: '大小变',
      mode: 'toggle',
      options: [{ name: '大小变', paramId: 'Param108' }],
    },
    {
      key: 'accessory',
      label: '配饰',
      mode: 'multi',
      options: [
        { name: '耳机', paramId: 'Param54' },
        { name: '猫', paramId: 'Param60' },
        { name: '天使环', paramId: 'Param106' },
        { name: '眼镜（方）', paramId: 'Param33' },
        { name: '眼镜（圆）', paramId: 'Param36' },
        { name: '爱心发饰', paramId: 'Param56' },
        { name: '发卡', paramId: 'Param57' },
        { name: '翅膀（装饰）', paramId: 'Param61' },
        { name: '翅膀（背后）', paramId: 'Param37' },
        { name: '牌子', paramId: 'Param45' },
        { name: '左袖子爱心', paramId: 'Param55' },
        { name: '袖带', paramId: 'Param46' },
        { name: '创可贴（额）', paramId: 'Param34' },
        { name: '创可贴（嘴）', paramId: 'Param92' },
        { name: '创可贴（右腿）', paramId: 'Param58' },
        { name: '创可贴（左腿）', paramId: 'Param59' },
      ],
    },
    {
      key: 'color',
      label: '颜色',
      mode: 'multi',
      options: [
        { name: '睫毛颜色', paramId: 'Param76' },
        { name: '眼镜颜色', paramId: 'Param70' },
        { name: '头发颜色', paramId: 'Param71' },
        { name: '头部装饰颜色', paramId: 'Param74' },
        { name: '身体装饰颜色', paramId: 'Param75' },
      ],
    },
    {
      key: 'mood',
      label: '情绪',
      mode: 'multi',
      options: [
        { name: '脸红', paramId: 'Param52' },
        { name: '哭', paramId: 'Param42' },
        { name: '黑脸', paramId: 'Param51' },
        { name: '血迹', paramId: 'Param53' },
      ],
    },
  ],
};

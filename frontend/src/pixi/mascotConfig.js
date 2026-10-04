// 模型注册表：新增模型 = 放一个模型文件夹到 public/live2d/<id>/ 并在这里加一条，
// 切换 UI 与渲染层都会自动感知，无需改渲染代码。
//   id          —— 唯一标识，也是 public/live2d/<id>/ 的目录名
//   name        —— 切换 UI 里显示的名称
//   url         —— 模型入口（.model3.json）
//   heightRatio —— 模型占屏幕高度的比例（0~1）；渲染时按屏幕高等比缩放，任意尺寸屏幕都看到等比例模型。
//                 0.49 ≈ 白自然高 1680 × 0.28（470px）÷ 27 寸（2560×1440 @150%）全屏高 960px。
//   x/y         —— 相对屏幕宽高的占比（0~1），决定角色摆放位置（渲染与兜底图共用，勿写死）
//   fallback    —— Live2D 加载失败时的静态兜底图 { url }（与主模型一致，按 heightRatio 等比缩放）
//   hit         —— 点击热区兜底盒（模型局部坐标，锚点居中）；getLocalBounds 退化时使用
export const MODELS = [
  {
    id: 'bai',
    name: '白',
    url: '/live2d/bai/白.model3.json',
    textureSize: 16384,
    heightRatio: 0.49,
    x: 0.82,
    y: 0.62,
    // 窄屏相对文档流预留区居中，高度上限同时服从区域和视口比例。
    // maxWidth 与 CSS 移动断点一致；位置不是固定视口坐标。
    mobile: { maxWidth: 720, heightRatio: 0.2, x: 0.5, y: 0.5 },
    fallback: { url: '/live2d/bai/白.16384/texture_00.png' },
    hit: { width: 1400, height: 2000 },
  },
];

// 默认模型 id：切换状态、兜底、初始加载统一从这里取，避免在组件内写死 'bai'
export const DEFAULT_MODEL_ID = MODELS[0].id;

// 模型布局选择保持配置驱动：渲染与静态兜底共用同一入口，新增断点不改摆放算法。
export function getModelLayout(model, viewportWidth) {
  return model.mobile && viewportWidth <= model.mobile.maxWidth ? model.mobile : model;
}

// 手机由文档流预留区承载；桌面保持原比例并限制在视口内。
// paddingRatio 给轻微呼吸留边，所有渲染/拖动共用同一几何边界。
export const PLACEMENT = { paddingRatio: 0.04, desktopFooterRatio: 0.1, dragThreshold: 3, touchAction: 'pan-y pinch-zoom', autoPreventDefault: false };
export function getModelPlacement(model, viewport, bounds, scaleFactor, region) {
  const layout = getModelLayout(model, viewport.width);
  const compact = layout !== model;
  const area = compact && region ? region : { left: 0, top: 0, width: viewport.width, height: viewport.height * (1 - PLACEMENT.desktopFooterRatio) };
  const pad = Math.min(area.width, area.height) * PLACEMENT.paddingRatio;
  const desiredHeight = compact ? Math.min(area.height * (scaleFactor / SCALE.max), viewport.height * layout.heightRatio * scaleFactor) : viewport.height * layout.heightRatio * scaleFactor;
  const scale = Math.min(desiredHeight / bounds.height, (area.width - pad * 2) / bounds.width, (area.height - pad * 2) / bounds.height);
  const halfWidth = bounds.width * scale / 2;
  const halfHeight = bounds.height * scale / 2;
  const minX = area.left + pad + halfWidth, maxX = area.left + area.width - pad - halfWidth;
  const minY = area.top + pad + halfHeight, maxY = area.top + area.height - pad - halfHeight;
  const x = compact ? area.left + area.width * layout.x : viewport.width * layout.x;
  const y = compact ? area.top + area.height * layout.y : viewport.height * layout.y;
  return { scale, x: Math.min(maxX, Math.max(minX, x)), y: Math.min(maxY, Math.max(minY, y)),
    minX, maxX, minY, maxY,
    visible: !compact || Boolean(region && region.top < viewport.height && region.top + region.height > 0) };
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
//   fallback —— 模型没有任何匹配参数时，退化为容器级 scale 呼吸（幅度/频率）。
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
// initial 为初始/默认倍率（相对默认高度的倍率，初始即按最大值展示，可用「变小」缩回）。
// 改这里调步长/边界/初始值，不改渲染逻辑。
export const SCALE = { step: 1.2, min: 0.5, max: 2.0, initial: 2.0 };

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

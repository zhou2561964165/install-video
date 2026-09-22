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
//   credit      —— 署名（作者/建模），About 页脚从这里读
export const MODELS = [
  {
    id: 'bai',
    name: '白',
    url: '/live2d/bai/白-免费版.model3.json',
    heightRatio: 0.49,
    x: 0.82,
    y: 0.62,
    fallback: { url: '/live2d/bai/白-免费版.16384/texture_00.png' },
    hit: { width: 1400, height: 2000 },
    credit: { artist: '煎果饼子txy', modeler: '逐尾鲨' },
  },
];

// 默认模型 id：切换状态、兜底、初始加载统一从这里取，避免在组件内写死 'bai'
export const DEFAULT_MODEL_ID = MODELS[0].id;

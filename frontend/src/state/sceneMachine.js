export const SCENE = {
  ENTRY: 'entry',
  PARSING: 'parsing',
  SELECTING: 'selecting',
  DOWNLOADING: 'downloading',
  DONE: 'done',
  ERROR: 'error',
};

export const initialState = () => ({
  scene: SCENE.ENTRY,
  url: '',
  parseResult: null,     // ParseResponse | null
  selectedFormat: null,  // FormatOption | null
  forceServer: false,
  download: null,        // DownloadResponse | null
  job: null,             // JobResponse | null
  error: null,           // { error_type, error } | null
});

export function reduce(state, action) {
  switch (action.type) {
    case 'SUBMIT_URL':
      return {
        ...initialState(),
        scene: SCENE.PARSING,
        url: action.url,
      };
    case 'PARSE_SUCCESS':
      return { ...state, scene: SCENE.SELECTING, parseResult: action.payload };
    case 'PARSE_FAIL':
      return { ...state, scene: SCENE.ERROR, error: action.error };
    case 'SELECT_FORMAT':
      return {
        ...state,
        selectedFormat: action.format,
        forceServer: action.forceServer ?? state.forceServer,
      };
    case 'START_DOWNLOAD':
      return { ...state, scene: SCENE.DOWNLOADING, download: action.download };
    case 'DOWNLOAD_PROGRESS': {
      const job = action.job;
      if (job.status === 'done') return { ...state, job, scene: SCENE.DONE };
      if (job.status === 'error') {
        return {
          ...state,
          job,
          scene: SCENE.ERROR,
          error: { error_type: job.error_type || 'network', error: job.error || '下载失败' },
        };
      }
      return { ...state, job };
    }
    case 'DOWNLOAD_FAIL':
      return { ...state, scene: SCENE.ERROR, error: action.error };
    case 'RESET':
      return initialState();
    default:
      return state;
  }
}

// 9 种 error_type → 二次元错误场景文案（spec §4 / design §8）
export const ERROR_SCENES = {
  invalid_url:      { emoji: '💫', title: '链接好像不对',   hint: '再检查一下链接吧' },
  unsupported_site: { emoji: '🌐', title: '这个网站还不支持', hint: '换一个网站试试' },
  age_restricted:   { emoji: '🔞', title: '年龄限制内容',     hint: '需要登录或验证年龄' },
  geo_blocked:      { emoji: '🗺️', title: '地区限制',         hint: '该视频在您所在地区不可用' },
  drm:              { emoji: '🔒', title: '受保护内容',       hint: '版权保护，无法下载' },
  login_required:   { emoji: '🔑', title: '需要登录',         hint: '该视频需登录后才能下载' },
  ffmpeg_missing:   { emoji: '🎬', title: '服务器缺少组件',   hint: '请稍后再试，或联系站长' },
  network:          { emoji: '📡', title: '网络出错了',       hint: '检查网络后重试' },
  quota:            { emoji: '⏳', title: '请求太频繁啦',     hint: '休息一下再试' },
};

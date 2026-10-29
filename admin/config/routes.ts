// Official Umi route registry, guarded by permission strings from auth/me.
export default [
  { path: '/login', layout: false, component: './user/login' },
  { path: '/overview', name:'概览',icon:'dashboard',component:'./Overview',access:'canReadOverview' },
  { path: '/users',name:'用户与权益',icon:'team',component:'./Users',access:'canReadUsers' },
  { path: '/users/:user_id',component:'./Users/Detail',access:'canReadUsers',hideInMenu:true },
  { path: '/memberships',name:'会员列表',icon:'idcard',component:'./Memberships',access:'canReadMemberships' },
  { path: '/jobs',name:'下载任务',icon:'CloudDownloadOutlined',component:'./Jobs',access:'canReadJobs' },
  { path: '/jobs/:job_id',component:'./Jobs/Detail',access:'canReadJobs',hideInMenu:true },
  { path: '/billing',name:'支付记录',icon:'AccountBookOutlined',component:'./Billing',access:'canReadBilling' },
  { path: '/support',name:'客服工单',icon:'CustomerServiceOutlined',component:'./Support',access:'canReadSupport' },
  { path: '/support/:ticket_id',component:'./Support/Detail',access:'canReadSupport',hideInMenu:true },
  { path: '/audit',name:'操作审计',icon:'audit',component:'./Audit',access:'canReadAudit' },
  { path: '/system',name:'系统状态',icon:'safety',component:'./System',access:'canReadSystem' },
  { path: '/', redirect: '/overview' },
  { path: '/*', layout: false, component: './exception/404' },
];

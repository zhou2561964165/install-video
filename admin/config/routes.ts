// Official Umi route registry, guarded by permission strings from auth/me.
export default [
  { path: '/login', layout: false, component: './user/login' },
  { path: '/overview', name:'概览',icon:'dashboard',component:'./Overview',access:'canReadOverview' },
  { path: '/users',name:'用户管理',icon:'team',component:'./Users',access:'canReadUsers' },
  { path: '/users/:user_id',component:'./Users/Detail',access:'canReadUsers',hideInMenu:true },
  { path: '/memberships',component:'./Memberships',access:'canReadMemberships',hideInMenu:true },
  { path: '/billing',name:'支付订单',icon:'AccountBookOutlined',component:'./Billing',access:'canReadBilling' },
  { path: '/support',name:'客服工单',icon:'CustomerServiceOutlined',component:'./Support',access:'canReadSupport' },
  { path: '/jobs',name:'下载记录',icon:'CloudDownloadOutlined',component:'./Jobs',access:'canReadJobs' },
  { path: '/jobs/:job_id',component:'./Jobs/Detail',access:'canReadJobs',hideInMenu:true },
  { path: '/support/:ticket_id',component:'./Support/Detail',access:'canReadSupport',hideInMenu:true },
  { name:'高级管理',icon:'setting',access:'canReadAdvanced',routes:[
    { path: '/audit',name:'操作记录',icon:'audit',component:'./Audit',access:'canReadAudit' },
    { path: '/system',name:'系统诊断',icon:'safety',component:'./System',access:'canReadSystem' },
  ] },
  { path: '/', redirect: '/overview' },
  { path: '/*', layout: false, component: './exception/404' },
];

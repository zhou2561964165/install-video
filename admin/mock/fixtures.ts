/** Fully synthetic development fixtures. Never imported by application pages. */
import type { Schemas } from '../src/services/admin/types';
import { resourceConfig } from '../src/config/resourceConfig';
export const stamp='2026-10-26T00:00:00Z';
export const capabilities: Schemas['Capabilities']={membership_control_write:{ready:false,reason:'模拟环境不执行会员设置'},account_access_write:{ready:false,reason:'M1 演示不开放写入'},billing_amounts:{ready:false,reason:'金额权威来源尚未就绪'},support_reissue:{ready:false,reason:'stripe_read_key_missing'}};
export function mockMeta(asOf:string):Schemas['AdminMeta'] {return {
 api_version:'v1',contract_version:'1.0.0-proposal.20261029.1',as_of:asOf,features:capabilities,
 pagination:{default_page:1,default_page_size:10,max_page_size:50},display_timezone:'Asia/Singapore',quota_day_timezone:'UTC',quota_day_semantics:'accepted_at_utc_date',
 limits:{session_ttl_seconds:900,reason_min_length:10,reason_max_length:500,idempotency_replay_retention_seconds:2592000,refresh_interval_seconds:0},
 queries:Object.entries(resourceConfig).map(([resource,spec])=>({resource,sort_values:[...spec.sortValues],filters:spec.filters.map(f=>({name:f.name,kind:f.kind,...(f.kind==='enum'?{allowed_values:f.schema.enum!.map(String)}:{})}))})),state_dictionaries:[],
};}
export const users: Schemas['UserDetail'][]=Array.from({length:27},(_,i)=>{
 const id=`usr_demo_${String(i+1).padStart(2,'0')}`,active=i%3===0;
 return {id,email:`person${String(i+1).padStart(2,'0')}@example.invalid`,created_at:new Date(Date.UTC(2026,9,i+1)).toISOString(),access:{enabled:i%5!==0,revision:i===0?'9007199254740993':String(i),protected_account:i===0},
 membership:{control_mode:'auto',control_revision:'0',control_expires_at:null,effective_reason:active?'payment_active':i%3===1?'payment_expired':'payment_inactive',effective_expires_at:active?'2099-01-01T00:00:00Z':null,effective_permanent:false,user_id:id,status:active?'active':i%3===1?'expired':'free',effective:active,expires_at:active?'2099-01-01T00:00:00Z':null,revision:active?'9007199254740993':null,entitlement_source:active?'synthetic_demo':null,cancel_at_period_end:false},
 quota:{quota_day:'2026-10-26',used:i+3,limit:active?null:5,remaining:active?null:2-i,unlimited:active},as_of:stamp};
});
export const memberships: Schemas['Membership'][]=users.filter((_,i)=>i%3!==2).map(u=>u.membership);
const publicStates=['queued','downloading','merging','done','error','future_state'];
const internalStates=['queued','running','retry_wait','succeeded','failed',null];
export const jobs:Schemas['JobDetail'][]=Array.from({length:23},(_,i)=>({
 id:`job_demo_${i+1}`,user_id:i===22?null:users[i%users.length].id,title:i===22?null:`合成演示视频 ${i+1}`,source_host:i===22?null:'video.example.invalid',execution_version:i%6===5?1:2,
 public_status:publicStates[i%6],internal_state:internalStates[i%6],progress:i%6===3?100:25,attempts_used:1,attempts_limit:3,created_at:users[i].created_at,updated_at:stamp,
 expires_at:null,run_deadline_at:null,next_run_at:null,error_type:i%6===4?'source_unavailable':null,error_message:i%6===4?'来源暂不可用。':null,
 artifact:{media_state:i%6===3?'available':null,byte_size:i%6===3?'9007199254740993':null,media_format:i%6===3?'mp4':null,media_check:i%6===3?'verified':null,completed_at:i%6===3?stamp:null},
 attempts:i%6===5?[]:[{id:`attempt_demo_${i+1}`,attempt_index:1,state:i%6===3?'succeeded':'running',started_at:stamp,ended_at:i%6===3?stamp:null,error_code:null}],as_of:stamp,
}));
const fact:Schemas['BillingFactSnapshot']={id:'fact_demo_01',provider_account_scope:'synthetic_test_scope',livemode:false,reconciliation:'verified',provider_status:'paid',money:{amount_minor:'9007199254740993',currency:'cny',currency_exponent:null},amount_refunded_minor:null,observed_at:stamp};
export const checkouts:Schemas['CheckoutDetail'][]=users.slice(0,15).map((u,i)=>({id:`checkout_demo_${i+1}`,user_id:u.id,state:['pending','open','paid','expired','failed','future_state'][i%6],reconciliation:i%3===0?'verified':null,fulfilled:i%6===2,provider_account_scope:i%3===0?'synthetic_test_scope':null,livemode:i%3===0?false:null,created_at:u.created_at,expires_at:null,revision:'9007199254740993',price_id:'price_synthetic_only',mode:'payment',duration_days:30,reconcile_attempts:0,verified_facts:i===2?[fact]:[],facts_state:i===2?'available':'none',as_of:stamp}));
export const payments:Schemas['PaymentDetail'][]=users.slice(0,13).map((u,i)=>({id:`pi_demo_${i+1}`,user_id:i===12?null:u.id,source_id:i===12?null:`checkout_demo_${i+1}`,revoked:i%3===0,money:null,amount_state:'unknown',amount_source:null,verified_facts:i===1?[fact]:[],facts_state:i===1?'available':i===2?'ambiguous':'none',facts_reason:i===2?'scope_or_user_binding_ambiguous':null,as_of:stamp}));
export const audit:Schemas['AuditEntry'][]=users.slice(0,12).map((u,i)=>({id:`audit_demo_${i+1}`,actor_user_id:i%3===0?null:'usr_demo_01',target_user_id:u.id,action:i%2===0?'auth.login_succeeded':'users.access.denied',outcome:i%2===0?'succeeded':'denied',reason:i%2===0?null:'合成演示记录，不执行实际操作',request_id:`mock_request_${i+1}`,recorded_at:u.created_at,change:null,operation:i%2===0?null:'users.access'}));
const categories=[['membership_not_credited','会员付款后未到账'],['download_failing','下载一直失败'],['login_problem','账号无法登录'],['other','其他问题']] as const;
export const supportTickets:Schemas['SupportTicketDetail'][]=users.slice(0,9).map((u,i)=>{
 const [category,label]=categories[i%4],open=i<6,membershipTicket=category==='membership_not_credited';
 return {id:`ticket_demo_${i+1}`,user_id:u.id,user_email:u.email,category,category_label:label,priority:membershipTicket||u.membership.effective?'priority':'normal',
  state:open?'open':i%2?'resolved':'rejected',resolution:open?null:i%2?'replied':'rejected',checkout_id:membershipTicket?checkouts[i].id:null,created_at:u.created_at,resolved_at:open?null:stamp,
  user_note:i===1?'<b>合成说明</b>，按纯文本显示':null,reply_template:open?null:'generic',reply_text:open?null:'已收到您的反馈，我们会尽快处理',reply_note:null,resolved_by:open?null:'usr_demo_01',
  checkout:membershipTicket?checkouts[i]:null,membership:u.membership,latest_check:null,
  actions:{verify:{allowed:false,reason:open&&membershipTicket?'stripe_read_key_missing':open?'not_reissuable_category':'ticket_closed'},reissue:{allowed:false,reason:open&&membershipTicket?'stripe_read_key_missing':open?'not_reissuable_category':'ticket_closed'},reply:{allowed:open,reason:open?null:'ticket_closed'},reject:{allowed:open,reason:open?null:'ticket_closed'}},as_of:stamp};
});
export function mockOverview(asOf:string):Schemas['Overview'] {
 const groups=(key:'public_status'|'internal_state')=>Object.entries(jobs.reduce<Record<string,number>>((out,j)=>{const s=j[key]??'legacy_unset';out[s]=(out[s]??0)+1;return out;},{})).map(([state,count])=>({state,count}));
 return {as_of:asOf,users_total:users.length,effective_vip_total:users.filter(u=>u.membership.effective).length,retained_server_jobs_total:jobs.length,jobs_by_public_status:groups('public_status'),jobs_by_internal_state:groups('internal_state'),scope:{users:'全部合成用户',effective_vip:'同一 as_of 的合成有效会员',jobs:'仅合成的当前保留 server Job'}};
}
export function mockSystem(asOf:string):Schemas['SystemStatus'] {return {as_of:asOf,components:[{component:'database',status:'ok',reason_code:null,checked_at:asOf},...(['download_worker','billing_worker','artifact_store'] as const).map(component=>({component,status:'unknown' as const,reason_code:'no_reliable_sample',checked_at:null}))],capabilities,download_submission_ready:{ready:false,reason:'PG 下载公开入口尚未接通；此处仅演示'}};}

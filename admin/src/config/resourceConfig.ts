import { contractOperations } from '../services/admin/contract';
import type { AdminQuery, ListOperation } from '../services/admin/api';
import type { Schemas } from '../services/admin/types';
import { isUtcTime } from '../utils/adminTime';
export const safetyDefaults = {pagination:{default_page:1,default_page_size:20,max_page_size:100},displayTimezone:'UTC',refreshInterval:0} as const;
export function paginationPolicy(meta?: Schemas['AdminMeta']) {
  const p = meta?.pagination;
  if (!p || !Number.isInteger(p.max_page_size) || p.max_page_size<1 || p.max_page_size>1000 || !Number.isInteger(p.default_page_size) || p.default_page_size<1 || p.default_page_size>p.max_page_size) return {...safetyDefaults.pagination};
  return {default_page:1,default_page_size:p.default_page_size,max_page_size:p.max_page_size};
}
export function refreshInterval(meta?: Schemas['AdminMeta']) { const seconds = meta?.limits?.refresh_interval_seconds; return typeof seconds==='number' && Number.isInteger(seconds) && seconds>=15 && seconds<=300 ? seconds : 0; }
export function canUseFeature(permissions: readonly string[], meta: Schemas['AdminMeta']|undefined, permission: string, feature: keyof Schemas['Capabilities']) {
  if(feature!=='account_access_write'&&feature!=='billing_amounts'&&feature!=='support_reissue')return false;
  return permissions.includes(permission) && meta?.features?.[feature]?.ready === true;
}
type QuerySchema = {type:string;enum?:readonly (string|number)[];format?:string;pattern?:string;maxLength?:number;minimum?:number;maximum?:number};
type FilterConfig = {name:string;kind:'enum'|'text'|'id'|'datetime'|'boolean';label:string;schema:QuerySchema};
const labels: Record<string,string> = {email:'邮箱',enabled:'账号可用',effective_vip:'有效会员',user_id:'用户 ID',public_status:'公开状态',internal_state:'内部状态',execution_version:'执行版本',effective:'当前生效',status:'原始状态',state:'状态',reconciliation:'核查状态',provider_account_scope:'供应商范围',livemode:'生产模式',revoked:'已撤销',actor_user_id:'操作者 ID',target_user_id:'目标用户 ID',action:'操作',outcome:'结果',recorded_from:'开始时间',recorded_before:'结束时间（不含）',category:'问题类型',priority:'优先级'};
const resourceLabels: Record<ListOperation,string> = {adminListUsers:'用户与权益',adminListJobs:'下载任务',adminListMemberships:'会员列表',adminListCheckouts:'Checkout',adminListPayments:'Payment',adminListAuditLogs:'操作审计',adminListSupportTickets:'客服工单'};
const listOperations = Object.keys(resourceLabels) as ListOperation[];
export const resourceConfig = Object.fromEntries(listOperations.map(key=>{
  const spec = contractOperations[key];
  const filters = Object.entries(spec.query).filter(([name])=>!['page','page_size','sort'].includes(name)).map(([name,raw])=>{
    const schema = raw as QuerySchema;
    return {name,label:labels[name]??name,schema,kind:schema.enum?'enum':schema.type==='boolean'?'boolean':schema.format==='date-time'?'datetime':schema.pattern==='^[A-Za-z0-9_.:-]+$'?'id':'text'} as FilterConfig;
  });
  return [key,{label:resourceLabels[key],permission:spec.permission,sortValues:spec.query.sort.enum as readonly string[],filters}];
})) as Record<ListOperation,{label:string;permission:string;sortValues:readonly string[];filters:FilterConfig[]}>;
export function validateQueryValue(schema: QuerySchema, value: unknown): boolean {
  if (schema.type==='boolean') return typeof value==='boolean';
  if (schema.type==='integer') return typeof value==='number' && Number.isSafeInteger(value) && (schema.minimum===undefined||value>=schema.minimum) && (schema.maximum===undefined||value<=schema.maximum) && (!schema.enum||schema.enum.includes(value));
  if (typeof value!=='string'||!value.length||Array.from(value).length>(schema.maxLength??1000)) return false;
  return (!schema.enum||schema.enum.includes(value)) && (!schema.pattern||new RegExp(schema.pattern).test(value)) && (schema.format!=='date-time'||isUtcTime(value));
}
export function toAdminQuery<K extends ListOperation>(operation: K, params: Record<string,unknown>={}, sort: Record<string,unknown>={}, filters: Record<string,unknown>={}, meta?: Schemas['AdminMeta']): AdminQuery<K> {
  const policy=paginationPolicy(meta), resource=resourceConfig[operation], server=meta?.queries?.find(q=>q.resource===operation);
  const integer = (v: unknown,fallback:number) => typeof v==='number'&&Number.isSafeInteger(v)&&v>=1?v:fallback;
  const output: Record<string,unknown> = {page:integer(params.current??params.page,policy.default_page),page_size:Math.min(integer(params.pageSize??params.page_size,policy.default_page_size),policy.max_page_size)};
  const requestedSort = Object.entries(sort).find(([,direction])=>direction==='ascend'||direction==='descend');
  const sorting = requestedSort ? `${requestedSort[0]}:${requestedSort[1]==='ascend'?'asc':'desc'}` : params.sort;
  if (typeof sorting==='string' && resource.sortValues.includes(sorting) && server?.sort_values.includes(sorting)) output.sort=sorting;
  for (const f of resource.filters) {
    const descriptor=server?.filters.find(d=>d.name===f.name && d.kind===f.kind);
    if (!descriptor) continue;
    let value=params[f.name]??filters[f.name];
    if (Array.isArray(value)) value=value.length===1?value[0]:undefined;
    if (!validateQueryValue(f.schema,value)) continue;
    if (f.kind==='enum'&&!descriptor.allowed_values?.includes(String(value))) continue;
    output[f.name]=value;
  }
  return output as AdminQuery<K>;
}

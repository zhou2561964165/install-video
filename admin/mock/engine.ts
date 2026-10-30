/** Independent in-process development backend. No real account, DB or upstream access. */
import { randomUUID } from 'node:crypto';
import { contractOperations } from '../src/services/admin/contract';
import { resourceConfig, validateQueryValue } from '../src/config/resourceConfig';
import { audit, capabilities, checkouts, jobs, memberships, mockMeta, mockOverview, mockSystem, payments, supportTickets, users } from './fixtures';
export type MockRequest={method:string;path:string;headers?:Record<string,string|undefined>;query?:Record<string,unknown>;body?:unknown};
export type MockResponse={status:number;headers?:Record<string,string>;body?:unknown};
type Scenario='normal'|'empty'|'forbidden'|'unavailable'|'rate-limited'|'meta-unavailable'|'expired';
const scenarios:Scenario[]=['normal','empty','forbidden','unavailable','rate-limited','meta-unavailable','expired'];
const permissions=['overview:read','users:read','memberships:read','jobs:read','billing:read','audit:read','system:read','support:read'];
// These explicit demonstration accounts exist only in this dev mock source.
const accounts=[{email:'operator@example.invalid',password:'LocalDemoOnly!26',permissions:[...permissions,'users:access:write','memberships:write','support:write'],role:'demo-operator'},
 {email:'viewer@example.invalid',password:'LocalDemoOnly!26',permissions,role:'demo-viewer'},
 {email:'limited@example.invalid',password:'LocalDemoOnly!26',permissions:['overview:read','users:read'],role:'demo-limited'}];
type MockSession={account:typeof accounts[number];expires:number;csrf:string;scenario:Scenario};
const bodyRecord=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'?value as Record<string,unknown>:{};
export function createMockBackend(now:()=>number=Date.now) {
 const sessions=new Map<string,MockSession>();
 const error=(status:number,type:string):MockResponse=>{const id=`mock-${randomUUID()}`;return {status,headers:{'X-Request-ID':id,...(status===429?{'Retry-After':'15'}:{})},body:{detail:{error_type:type,error:'Synthetic development error',request_id:id}}};};
 return (request:MockRequest):MockResponse=>{
  const method=request.method.toUpperCase(),headers=request.headers??{},cookie=headers.cookie??'',key=/(?:^|;\s*)admin_demo_session=([^;]+)/.exec(cookie)?.[1],session=key?sessions.get(key):undefined;
  const valid=session&&session.expires>now();
  if(request.path==='/__admin_mock/help'&&method==='GET')return {status:200,body:{warning:'DEVELOPMENT MOCK ONLY — no real credentials or data',accounts,scenarios,scenario_endpoint:'POST /__admin_mock/scenario {scenario: name} with the mock cookie; expired revokes the session. Restore other scenarios with normal.'}};
  if(request.path==='/__admin_mock/scenario'&&method==='POST'){
   if(!valid)return error(401,'session_expired');
   const scenario=bodyRecord(request.body).scenario;
   if(!scenarios.includes(scenario as Scenario))return error(422,'invalid_scenario');
   if(scenario==='expired')sessions.delete(key!);else session.scenario=scenario as Scenario;
   return {status:200,body:{scenario}};
  }
  const match=Object.entries(contractOperations).find(([,operation])=>operation.method===method&&new RegExp(`^${operation.path.replace(/\{[^}]+\}/g,'[A-Za-z0-9_.:%-]+')}$`).test(request.path));
  if(!match)return error(404,'not_found');
  const [operation,spec]=match;
  if(operation==='adminLogin'){
   const body=bodyRecord(request.body),account=accounts.find(a=>a.email===body.email&&a.password===body.password);
   if(!account)return error(401,'invalid_credentials');
   if(key)sessions.delete(key);
   const id=randomUUID(),expires=now()+900000;sessions.set(id,{account,expires,csrf:randomUUID()+randomUUID(),scenario:'normal'});
   return {status:200,headers:{'Set-Cookie':`admin_demo_session=${id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=900`},body:{session_expires_at:new Date(expires).toISOString()}};
  }
  if(!valid){if(key)sessions.delete(key);const response=error(401,'session_expired');if(operation==='adminLogout')response.headers={...response.headers,'Set-Cookie':'admin_demo_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'};return response;}
  if(spec.permission&&!session.account.permissions.includes(spec.permission))return error(403,'permission_denied');
  if(method!=='GET'&&headers['x-csrf-token']!==session.csrf)return error(403,'csrf_rejected');
  if(operation==='adminLogout'){sessions.delete(key!);return {status:204,headers:{'Set-Cookie':'admin_demo_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'}};}
  const asOf=new Date(now()).toISOString();
  if(operation==='adminMe')return {status:200,body:{user_id:'usr_demo_01',email:session.account.email,role:session.account.role,permissions:session.account.permissions,session_expires_at:new Date(session.expires).toISOString(),csrf_token:session.csrf,capabilities}};
  if(operation==='adminMeta')return session.scenario==='meta-unavailable'?error(503,'admin_unavailable'):{status:200,body:mockMeta(asOf)};
  if(session.scenario==='forbidden')return error(403,'permission_denied');
  if(session.scenario==='unavailable')return error(503,'admin_unavailable');
  if(session.scenario==='rate-limited')return error(429,'rate_limited');
  if(operation==='adminSetUserMembership')return error(503,'mock_write_disabled');
  if(operation==='adminSetUserAccess')return error(503,'account_access_not_ready');
  // Support writes are never simulated: a mock success could be mistaken for a real reply or re-issue.
  if(['adminReplySupportTicket','adminRejectSupportTicket','adminVerifySupportPayment','adminReissueMembership'].includes(operation))return error(503,'mock_write_disabled');
  if(operation==='adminOverview')return {status:200,body:mockOverview(asOf)};
  if(operation==='adminSystemStatus')return {status:200,body:mockSystem(asOf)};
  const data:Record<string,Record<string,unknown>[]>={adminListUsers:users,adminListJobs:jobs,adminListMemberships:memberships,adminListCheckouts:checkouts,adminListPayments:payments,adminListAuditLogs:audit,adminListSupportTickets:supportTickets.map(({user_note:_n,reply_template:_t,reply_text:_r,reply_note:_o,resolved_by:_b,checkout:_c,membership:_m,latest_check:_l,actions:_a,as_of:_s,...row})=>row)};
  const details:Record<string,Record<string,unknown>[]>={adminGetUser:users,adminGetJob:jobs,adminGetCheckout:checkouts,adminGetPayment:payments,adminGetSupportTicket:supportTickets};
  if(details[operation]){const id=decodeURIComponent(request.path.split('/').at(-1)!);const item=details[operation].find(row=>row.id===id);return item?{status:200,body:{...item,as_of:asOf}}:error(404,'not_found');}
  if(!data[operation])return error(404,'not_found');
  const query=request.query??{},schema=spec.query as Record<string,{type:string;enum?:readonly(string|number)[];format?:string;pattern?:string;maxLength?:number;minimum?:number;maximum?:number;default?:unknown}>,normalized:Record<string,unknown>={};
  for(const [name,raw]of Object.entries(query)){
   const field=schema[name];if(!field||Array.isArray(raw))return error(422,'invalid_query');
   const value=field.type==='integer'&&typeof raw==='string'&&/^\d+$/.test(raw)?Number(raw):field.type==='boolean'&&raw==='true'?true:field.type==='boolean'&&raw==='false'?false:raw;
   if(!validateQueryValue(field,value))return error(422,'invalid_query');normalized[name]=value;
  }
  const page=Number(normalized.page??1),pageSize=Number(normalized.page_size??10);if(pageSize>50)return error(422,'page_size_exceeded');
  let rows=session.scenario==='empty'?[]:[...data[operation]];
  const read=(row:Record<string,unknown>,name:string):unknown=>name==='enabled'?bodyRecord(row.access).enabled:name==='effective_vip'?bodyRecord(row.membership).effective:name==='payment_id'?row.id:name==='internal_state'&&row.internal_state===null?'legacy_unset':row[name];
  for(const [name,value]of Object.entries(normalized)){
   if(['page','page_size','sort'].includes(name))continue;
   rows=rows.filter(row=>name==='recorded_from'?Date.parse(String(row.recorded_at))>=Date.parse(String(value)):name==='recorded_before'?Date.parse(String(row.recorded_at))<Date.parse(String(value)):name==='email'?String(row.email).toLowerCase().includes(String(value).toLowerCase()):read(row,name)===value);
  }
  const resource=resourceConfig[operation as keyof typeof resourceConfig],sorting=String(normalized.sort??schema.sort.default??resource.sortValues[0]),[field,direction]=sorting.split(':');
  rows.sort((a,b)=>{
   const left=read(a,field),right=read(b,field);
   if(left==null&&right!=null)return 1;if(right==null&&left!=null)return -1;
   const compare=(x:unknown,y:unknown)=>String(x)<String(y)?-1:String(x)>String(y)?1:0;
   const primary=typeof left==='number'&&typeof right==='number'?left-right:left==null&&right==null?0:field.endsWith('_at')?Date.parse(String(left))-Date.parse(String(right)):compare(left,right);
   return primary?primary*(direction==='desc'?-1:1):compare(a.id??a.user_id,b.id??b.user_id);
  });
  return {status:200,body:{items:rows.slice((page-1)*pageSize,page*pageSize),total:rows.length,page,page_size:pageSize,as_of:asOf}};
 };
}

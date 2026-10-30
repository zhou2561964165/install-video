import type { Schemas } from '../services/admin/types';
import { safetyDefaults } from '../config/resourceConfig';
import { isUtcTime } from './adminTime';
export function formatTime(value: string|null|undefined, timezone = safetyDefaults.displayTimezone as string): string {
  if (!isUtcTime(value)) return '—';
  try { return `${new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value))} (${timezone})`; }
  catch { return `${new Date(value).toISOString()} (UTC)`; }
}
export function formatBytes(value: string|null|undefined): string {
  if (!value||!/^(0|[1-9][0-9]*)$/.test(value)) return '—';
  const bytes=BigInt(value),units=['B','KiB','MiB','GiB','TiB','PiB','EiB']; let i=0,divisor=1n;
  while(bytes>=divisor*1024n&&i<units.length-1){divisor*=1024n;i++;}
  if (!i) return `${bytes} B`;
  const scaled=(bytes*100n+divisor/2n)/divisor;
  return `${scaled/100n}.${String(scaled%100n).padStart(2,'0')} ${units[i]}`;
}
export function formatMoney(money: Schemas['Money']|null|undefined): string {
  if (!money || money.amount_minor===null || !/^(0|[1-9][0-9]*)$/.test(money.amount_minor) || money.currency===null || !/^[a-z]{3}$/.test(money.currency) || money.currency_exponent===null || !Number.isInteger(money.currency_exponent) || money.currency_exponent<0 || money.currency_exponent>9) return '金额未知';
  const n=money.amount_minor.padStart(money.currency_exponent+1,'0'), e=money.currency_exponent;
  return `${money.currency.toUpperCase()} ${e?`${n.slice(0,-e)}.${n.slice(-e)}`:n}`;
}
export function formatQuota(quota: Schemas['Quota']|null|undefined): string {
  if (!quota) return '—';
  const remaining=quota.remaining===null?'剩余未知':quota.remaining<0?`超出额度 ${-quota.remaining}`:`剩余 ${quota.remaining}`;
  return `已用 ${quota.used} · ${quota.unlimited?'不限次数':`上限 ${quota.limit??'未知'} · ${remaining}`} · ${quota.quota_day} (UTC)`;
}
const known: Record<string,Record<string,[string,Schemas['StateDisplay']['tone']]>>={
 'job.public_status':{queued:['排队中','neutral'],downloading:['下载中','info'],merging:['合并中','info'],done:['已完成','success'],error:['失败','error']},
 'job.internal_state':{queued:['排队中','neutral'],running:['执行中','info'],retry_wait:['等待重试','warning'],succeeded:['成功','success'],failed:['失败','error'],needs_review:['待复核','warning'],legacy_hold:['历史保留','neutral'],legacy_unset:['历史未设置','neutral']},
 'membership.status':{free:['暂无付款会员','neutral'],active:['原会员记录已启用','info'],expired:['原会员记录已到期','neutral']},
 'checkout.state':{pending:['待创建','neutral'],open:['待完成付款','info'],paid:['订单标记已付款','info'],expired:['已过期','neutral'],failed:['失败','error']},
 'system.status':{ok:['正常','success'],degraded:['降级','warning'],unavailable:['不可用','error'],unknown:['未知 / 无可靠采样','neutral']},
 'reconciliation':{not_started:['未开始','neutral'],unknown:['未知','neutral'],verified:['已核查','success'],needs_review:['待复核','warning'],closed:['已关闭','neutral']},
 'job.attempt':{running:['执行中','info'],lost:['租约丢失','warning'],failed:['失败','error'],succeeded:['成功','success']},
 'audit.outcome':{succeeded:['成功','success'],denied:['拒绝','warning'],failed:['失败','error']},
};
export function stateDisplay(domain:string,value:string|null|undefined,meta?:Schemas['AdminMeta']):{label:string;tone:Schemas['StateDisplay']['tone']} {
  if (value===null||value===undefined) return {label:'未设置',tone:'neutral'};
  const fallback=known[domain]?.[value];
  // Server dictionaries label only contract-known states. A future state remains neutral.
  if (!fallback) return {label:`未知状态（${value}）`,tone:'neutral'};
  const item=meta?.state_dictionaries?.find(d=>d.domain===domain)?.values.find(s=>s.value===value);
  return {label:item?.label??fallback[0],tone:item&&['neutral','info','success','warning','error'].includes(item.tone)?item.tone:fallback[1]};
}
export const stateLabel=stateDisplay;

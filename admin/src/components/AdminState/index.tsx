import { Button, Result, Tag, Tooltip } from 'antd';
import { normalizeAdminError } from '../../services/admin/errors';
import type { Schemas } from '../../services/admin/types';
import { formatTime, stateDisplay } from '../../utils/adminFormat';
export function AdminError({error,onRetry}:{error:unknown;onRetry?:()=>void}) {
  const normalized=normalizeAdminError(error);
  const status=normalized.status===403?'403':normalized.status===404?'404':'error';
  return <Result status={status} title={normalized.message} subTitle={<>
    {normalized.requestId&&<div>请求编号：{normalized.requestId}</div>}
    {normalized.retryAfter&&<div>建议等待 {normalized.retryAfter} 秒后手动重试。</div>}
    {normalized.outcomeUnknown&&<div>写入结果未知；请先刷新核对，保留原请求编号和幂等键。</div>}
  </>} extra={onRetry&&<Button onClick={onRetry}>重新加载</Button>}/>;
}
export function AdminStateTag({domain,value,meta}:{domain:string;value:string|null|undefined;meta?:Schemas['AdminMeta']}) {
  const state=stateDisplay(domain,value,meta), colors={neutral:'default',info:'processing',success:'success',warning:'warning',error:'error'};
  return <Tag color={colors[state.tone]}>{state.label}</Tag>;
}
export function AdminTimestamp({value,timezone}:{value:string|null|undefined;timezone?:string}) {
  return <Tooltip title={value?formatTime(value,'UTC'):undefined}><span className="admin-numeric">{formatTime(value,timezone)}</span></Tooltip>;
}

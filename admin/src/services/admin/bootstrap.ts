import type { ProSettings } from '@ant-design/pro-components';
import { adminApi } from './api';
import { clearSession, setSession, sessionEpoch } from './session';
import { paginationPolicy } from '../../config/resourceConfig';
import { normalizeAdminError, AdminApiError } from './errors';
import type { Schemas } from './types';
import { isUtcTime } from '../../utils/adminTime';
export type AdminInitialState = {settings:Partial<ProSettings>;me?:Schemas['AdminMe'];meta?:Schemas['AdminMeta'];permissions:string[];bootstrapError?:AdminApiError};
export async function bootstrapSession(settings: Partial<ProSettings>): Promise<AdminInitialState> {
  const epoch=sessionEpoch();
  try {
    const me=await adminApi.adminMe();
    if (!Array.isArray(me.permissions)||me.permissions.some(p=>typeof p!=='string')||typeof me.csrf_token!=='string'||!me.csrf_token||!isUtcTime(me.session_expires_at)||Date.parse(me.session_expires_at)<=Date.now()) throw new AdminApiError(502,'invalid_session_projection');
    const meta=await adminApi.adminMeta();
    if (meta.api_version!=='v1'||!meta.features||meta.contract_version!=='1.0.0-proposal.20261029.1'||typeof meta.features.membership_control_write?.ready!=='boolean'||typeof meta.features.account_access_write?.ready!=='boolean'||typeof meta.features.billing_amounts?.ready!=='boolean'||!meta.pagination||!Array.isArray(meta.queries)||meta.queries.some(q=>typeof q.resource!=='string'||!Array.isArray(q.filters)||!Array.isArray(q.sort_values))||!Array.isArray(meta.state_dictionaries)||!isUtcTime(meta.as_of)||meta.quota_day_timezone!=='UTC'||meta.quota_day_semantics!=='accepted_at_utc_date') throw new AdminApiError(502,'invalid_metadata_projection');
    const policy=paginationPolicy(meta);
    if(meta.pagination.default_page!==1||policy.max_page_size!==meta.pagination.max_page_size||policy.default_page_size!==meta.pagination.default_page_size) throw new AdminApiError(502,'invalid_pagination_policy');
    const limits=meta.limits,range=(v:unknown,min:number,max=Number.MAX_SAFE_INTEGER)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min&&v<=max;
    if(!limits||!range(limits.session_ttl_seconds,300,3600)||!range(limits.reason_min_length,10,2000)||!range(limits.reason_max_length,limits.reason_min_length,2000)||!range(limits.idempotency_replay_retention_seconds,604800)||!(limits.refresh_interval_seconds===0||range(limits.refresh_interval_seconds,15,300)))throw new AdminApiError(502,'invalid_policy_limits');
    if(epoch!==sessionEpoch()) throw new AdminApiError(409,'session_changed');
    setSession(me,meta);
    return {settings,me,meta,permissions:me.permissions};
  } catch (value) {
    if(normalizeAdminError(value).errorType==='session_changed') throw value;
    if(epoch===sessionEpoch()) clearSession('bootstrap');
    return {settings,permissions:[],bootstrapError:normalizeAdminError(value)};
  }
}

import { request } from '@umijs/max';
import type { operations, Schemas } from './types';
import { contractOperations } from './contract';
import { AdminApiError, normalizeAdminError } from './errors';
import { clearSession, getSession, sessionEpoch } from './session';
export type ListOperation = 'adminListUsers'|'adminListJobs'|'adminListMemberships'|'adminListCheckouts'|'adminListPayments'|'adminListAuditLogs'|'adminListSupportTickets';
export type AdminQuery<K extends ListOperation> = NonNullable<operations[K]['parameters']['query']>;
async function call<T>(operation: keyof typeof contractOperations, values: {id?: string; params?: object; data?: object; key?: string} = {}): Promise<T> {
  const spec = contractOperations[operation], write = spec.method !== 'GET';
  const epoch=sessionEpoch();
  let path: string = spec.path;
  if (values.id !== undefined) {
    if (!/^[A-Za-z0-9_.:-]{1,256}$/.test(values.id)) throw new AdminApiError(422, 'invalid_id');
    path = path.replace(/\{[^}]+\}/, encodeURIComponent(values.id));
  }
  const headers: Record<string,string> = {};
  if (write && operation !== 'adminLogin') {
    const csrf = getSession().me?.csrf_token;
    if (!csrf) {clearSession('unauthorized'); throw new AdminApiError(401, 'csrf_unavailable');}
    headers['X-CSRF-Token'] = csrf;
  }
  if (values.key !== undefined) {
    if (!/^[A-Za-z0-9._:-]{16,128}$/.test(values.key)) throw new AdminApiError(422,'invalid_idempotency_key');
    headers['Idempotency-Key'] = values.key;
  }
  try {
    // No retry middleware, Bearer, localStorage, request recorder or automatic mock fallback.
    const result=await request<T>(`${ADMIN_API_BASE}${path}`, {method: spec.method, baseURL: '', withCredentials: true,
      headers, params: values.params, data: values.data, timeout: 20000, skipErrorHandler: true});
    if (epoch!==sessionEpoch()) throw new AdminApiError(409,'session_changed',undefined,undefined,[],write);
    return result;
  } catch (value) {
    const error = normalizeAdminError(value, write);
    if(epoch!==sessionEpoch()) throw new AdminApiError(409,'session_changed',undefined,undefined,[],write);
    if (error.status === 401 && epoch===sessionEpoch()) clearSession('unauthorized');
    throw error;
  }
}
export const adminApi = {
  adminLogin: (body: Schemas['LoginRequest']) => {clearSession('login'); return call<Schemas['SessionCreated']>('adminLogin',{data:body});},
  adminMe: () => call<Schemas['AdminMe']>('adminMe'),
  adminLogout: async () => { const epoch=sessionEpoch(); try { await call<void>('adminLogout'); } finally { if(epoch===sessionEpoch()) clearSession('logout'); } },
  adminMeta: () => call<Schemas['AdminMeta']>('adminMeta'),
  adminOverview: () => call<Schemas['Overview']>('adminOverview'),
  adminListUsers: (query?: AdminQuery<'adminListUsers'>) => call<Schemas['UserPage']>('adminListUsers',{params:query}),
  adminGetUser: (id: string) => call<Schemas['UserDetail']>('adminGetUser',{id}),
  adminSetUserAccess: (id: string, body: Schemas['AccessPatch'], key: string) => call<Schemas['AccessResult']>('adminSetUserAccess',{id,data:body,key}),
  adminSetUserMembership: (id: string, body: Schemas['MembershipPatch'], key: string) => call<Schemas['MembershipResult']>('adminSetUserMembership',{id,data:body,key}),
  adminListJobs: (query?: AdminQuery<'adminListJobs'>) => call<Schemas['JobPage']>('adminListJobs',{params:query}),
  adminGetJob: (id: string) => call<Schemas['JobDetail']>('adminGetJob',{id}),
  adminListMemberships: (query?: AdminQuery<'adminListMemberships'>) => call<Schemas['MembershipPage']>('adminListMemberships',{params:query}),
  adminListCheckouts: (query?: AdminQuery<'adminListCheckouts'>) => call<Schemas['CheckoutPage']>('adminListCheckouts',{params:query}),
  adminGetCheckout: (id: string) => call<Schemas['CheckoutDetail']>('adminGetCheckout',{id}),
  adminListPayments: (query?: AdminQuery<'adminListPayments'>) => call<Schemas['PaymentPage']>('adminListPayments',{params:query}),
  adminGetPayment: (id: string) => call<Schemas['PaymentDetail']>('adminGetPayment',{id}),
  adminListAuditLogs: (query?: AdminQuery<'adminListAuditLogs'>) => call<Schemas['AuditPage']>('adminListAuditLogs',{params:query}),
  adminSystemStatus: () => call<Schemas['SystemStatus']>('adminSystemStatus'),
  adminListSupportTickets: (query?: AdminQuery<'adminListSupportTickets'>) => call<Schemas['SupportTicketPage']>('adminListSupportTickets',{params:query}),
  adminGetSupportTicket: (id: string) => call<Schemas['SupportTicketDetail']>('adminGetSupportTicket',{id}),
  adminReplySupportTicket: (id: string, body: Schemas['SupportReply']) => call<Schemas['SupportTicketState']>('adminReplySupportTicket',{id,data:body}),
  adminRejectSupportTicket: (id: string, body: Schemas['SupportReply']) => call<Schemas['SupportTicketState']>('adminRejectSupportTicket',{id,data:body}),
  adminVerifySupportPayment: (id: string) => call<Schemas['PaymentCheck']>('adminVerifySupportPayment',{id}),
  adminReissueMembership: (id: string, key: string) => call<Schemas['ReissueResult']>('adminReissueMembership',{id,key}),
};
export function toProTableResult<T>(page: {items:T[];total:number}) { return {data:page.items,total:page.total,success:true as const}; }

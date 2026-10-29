import type { Schemas } from './types';
export type ClearReason = 'unauthorized'|'expired'|'logout'|'bootstrap'|'login';
type Session = {me?: Schemas['AdminMe']; meta?: Schemas['AdminMeta']; clearReason?:ClearReason};
let session: Session = {};
let epoch=0;
const listeners = new Set<() => void>();
export const getSession = () => session;
export const sessionEpoch = () => epoch;
export function setSession(me: Schemas['AdminMe'], meta?: Schemas['AdminMeta']) { epoch++; session = {me, meta}; listeners.forEach(fn=>fn()); }
export function clearSession(reason:ClearReason='logout') { epoch++; session = {clearReason:reason}; listeners.forEach(fn=>fn()); }
export function subscribeSession(fn: () => void) { listeners.add(fn); return () => {listeners.delete(fn);}; }
export function safeReturnPath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || /[\\\r\n]/.test(value)) return '/overview';
  let decoded: string;
  try { decoded = decodeURIComponent(value); } catch { return '/overview'; }
  if (decoded.startsWith('//') || /[\\\r\n]/.test(decoded) || /^\/login(?:[/?#]|$)/.test(decoded)) return '/overview';
  return /^\/(overview|users|jobs|memberships|billing|audit|system|support)(?:[/?#]|$)/.test(decoded) ? value : '/overview';
}

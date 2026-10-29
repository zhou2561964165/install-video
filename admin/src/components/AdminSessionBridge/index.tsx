import { history, useModel } from '@umijs/max';
import { useEffect } from 'react';
import { clearSession, getSession, safeReturnPath, subscribeSession } from '../../services/admin/session';
/** Synchronize in-memory state into the official initialState model, including late 401s. */
export function AdminSessionBridge() {
  const {initialState,setInitialState}=useModel('@@initialState');
  useEffect(()=>subscribeSession(()=>{
    const session=getSession();
    if(session.clearReason==='bootstrap') return;
    void setInitialState(previous=>({...previous,settings:previous?.settings??{},me:session.me,meta:session.meta,permissions:session.me?.permissions??[],bootstrapError:undefined}));
    if (!session.me && ['unauthorized','expired'].includes(session.clearReason??'') && history.location.pathname!=='/login') history.replace(`/login?expired=1&returnPath=${encodeURIComponent(safeReturnPath(history.location.pathname+history.location.search))}`);
  }),[setInitialState]);
  useEffect(()=>{
    if (!initialState?.me) return undefined;
    const remaining=Date.parse(initialState.me.session_expires_at)-Date.now();
    if (!Number.isFinite(remaining)||remaining<=0) {clearSession('expired');return undefined;}
    const timer=window.setTimeout(()=>clearSession('expired'),Math.min(remaining,2147483647));
    return ()=>window.clearTimeout(timer);
  },[initialState?.me?.session_expires_at]);
  return null;
}

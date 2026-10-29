// Derived from the official Ant Design Pro runtime hooks, not a custom layout.
import type { RequestConfig, RunTimeLayoutConfig } from '@umijs/max';
import { history, Link } from '@umijs/max';
import type { ReactNode } from 'react';
import defaultSettings from '../config/defaultSettings';
import { adminTheme } from './config/theme';
import { errorConfig } from './requestErrorConfig';
import { bootstrapSession } from './services/admin/bootstrap';
import { getSession, safeReturnPath } from './services/admin/session';
import { AdminError } from './components/AdminState';
import { AdminSessionBridge } from './components/AdminSessionBridge';
import AdminHeader from './components/AdminHeader';
import { AdminMockBanner } from './components/AdminMockBanner';

export async function getInitialState() {
  return bootstrapSession(defaultSettings);
}
export function rootContainer(container:ReactNode) {return <>
  {ADMIN_MOCK_ENABLED&&<AdminMockBanner/>}
  {container}
</>;}
export const layout: RunTimeLayoutConfig = ({ initialState }) => ({
  ...initialState?.settings,
  actionsRender: () => [<AdminHeader key="admin-session"/>],
  footerRender: false,
  menuItemRender: (item, dom) => item.path ? <Link to={item.path}>{dom}</Link> : dom,
  // Official layout checks route access before childrenRender; bootstrap errors
  // therefore need its documented inaccessible slot as well as the content slot.
  unAccessible:initialState?.bootstrapError&&initialState.bootstrapError.status!==401?<AdminError error={initialState.bootstrapError} onRetry={()=>window.location.reload()}/>:undefined,
  onPageChange:()=>{
    if (!getSession().me && (!initialState?.bootstrapError || initialState.bootstrapError.status===401) && history.location.pathname!=='/login')
      history.replace(`/login?returnPath=${encodeURIComponent(safeReturnPath(history.location.pathname+history.location.search))}`);
  },
  childrenRender: (children) => <>
    <AdminSessionBridge/>
    {initialState?.bootstrapError&&initialState.bootstrapError.status!==401?<AdminError error={initialState.bootstrapError} onRetry={()=>window.location.reload()}/>:children}
  </>,
});
export const antd = () => ({ theme: adminTheme });

// Retain the official Umi request/axios integration; the narrow adapter owns CSRF.
export const request: RequestConfig = {
  baseURL: '',
  withCredentials: true,
  ...errorConfig,
};

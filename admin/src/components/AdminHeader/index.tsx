import { history } from '@umijs/max';
import { UserOutlined } from '@ant-design/icons';
import { Button, Dropdown, Grid, Space, Typography } from 'antd';
import { useState } from 'react';
import { useAdminSession } from '../../hooks/useAdminSession';
import { adminApi } from '../../services/admin/api';
import { formatTime } from '../../utils/adminFormat';
import { normalizeAdminError } from '../../services/admin/errors';
export default function AdminHeader() {
  const {me,meta}=useAdminSession(),[busy,setBusy]=useState(false);
  const screens=Grid.useBreakpoint();
  if (!me) return null;
  const logout=async()=>{if(busy)return;setBusy(true);let confirmed=false,replaced=false;try{await adminApi.adminLogout();confirmed=true;}catch(error){replaced=normalizeAdminError(error).errorType==='session_changed';}finally{if(!replaced)history.replace(confirmed?'/login':'/login?logout=unconfirmed');setBusy(false);}};
  if(!screens.sm)return <Dropdown trigger={['click']} placement="bottomRight" menu={{
    style:{maxWidth:'var(--header-menu-width)'},
    items:[
      {key:'account',disabled:true,label:<span className="admin-header-session-detail">{me.email} · {me.role}</span>},
      {key:'expires',disabled:true,label:<span className="admin-header-session-detail">到期 {formatTime(me.session_expires_at,meta?.display_timezone)}</span>},
      {type:'divider'},
      {key:'logout',label:busy?'正在退出…':'退出登录',disabled:busy,onClick:()=>{void logout();}},
    ],
  }}><Button icon={<UserOutlined/>} aria-label="管理员会话" loading={busy}>账号</Button></Dropdown>;
  return <Space wrap className="admin-header">
    <Typography.Text>{me.email} · {me.role}</Typography.Text>
    <Typography.Text type="secondary">到期 {formatTime(me.session_expires_at,meta?.display_timezone)}</Typography.Text>
    <Button loading={busy} onClick={logout}>退出登录</Button>
  </Space>;
}

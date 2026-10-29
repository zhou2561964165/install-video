// Official LoginForm composition, trimmed from upstream src/pages/user/login/index.tsx.
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { LoginForm, ProFormText } from '@ant-design/pro-components';
import { history, useModel } from '@umijs/max';
import { Alert, Button } from 'antd';
import { useState } from 'react';
import { flushSync } from 'react-dom';
import { adminApi } from '../../../services/admin/api';
import { bootstrapSession } from '../../../services/admin/bootstrap';
import { safeReturnPath } from '../../../services/admin/session';
import { normalizeAdminError } from '../../../services/admin/errors';
import { AdminError } from '../../../components/AdminState';

export default function Login() {
  const {initialState,setInitialState}=useModel('@@initialState');
  const [error,setError]=useState<unknown>();
  const [busy,setBusy]=useState(false);
  const target=()=>safeReturnPath(new URLSearchParams(history.location.search).get('returnPath'));
  return <main className="admin-login">
    {new URLSearchParams(history.location.search).has('expired')&&<Alert type="warning" title="会话已过期或撤销，请重新登录。"/>}
    {new URLSearchParams(history.location.search).get('logout')==='unconfirmed'&&<Alert type="warning" title="本地会话已清除，服务端退出结果未确认。请重新核对会话，勿假定已撤销。"/>}
    {ADMIN_MOCK_ENABLED&&<Alert type="info" title={<>仅供本地演示：<a href="/__admin_mock/help" target="_blank" rel="noreferrer">查看合成账号与测试场景</a></>}/>}
    {initialState?.me?<Alert type="success" title="管理员会话有效" action={<Button onClick={()=>history.replace(target())}>进入管理端</Button>}/>:null}
    <LoginForm<{email:string;password:string}> title="视频工具管理端" subTitle="独立管理员会话 · 以服务端到期时间为准"
      submitter={{searchConfig:{submitText:'登录'},submitButtonProps:{loading:busy}}}
      onFinish={async(values)=>{setBusy(true);setError(undefined);try{
        await adminApi.adminLogin({email:values.email.trim(),password:values.password});
        const state=await bootstrapSession(initialState?.settings??{});
        // Umi's async setter schedules React state but does not await its commit.
        // Commit permissions/access before navigating to a protected return path.
        flushSync(()=>{void setInitialState(state);});
        if (state.bootstrapError) throw state.bootstrapError;
        history.replace(target());return true;
      }catch(value){setError(normalizeAdminError(value));return false;}finally{setBusy(false);}}}>
      {(error||initialState?.bootstrapError&&initialState.bootstrapError.status!==401)&&<AdminError error={error??initialState?.bootstrapError}/>}
      <ProFormText name="email" label="邮箱"
        rules={[{required:true,message:'请输入邮箱'},{type:'email',message:'邮箱格式不正确'},{max:254,message:'邮箱过长'}]}
        fieldProps={{ prefix: <UserOutlined />, autoComplete: 'username',type:'email' }} />
      <ProFormText.Password name="password" label="密码"
        rules={[{required:true,message:'请输入密码'},{max:1024,message:'密码过长'}]}
        fieldProps={{ prefix: <LockOutlined />, autoComplete: 'current-password' }} />
    </LoginForm>
  </main>;
}

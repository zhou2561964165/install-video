import { beforeEach, describe, expect, it, vi } from 'vitest';
import { request } from '@umijs/max';
import { adminApi } from '../src/services/admin/api';
import { bootstrapSession } from '../src/services/admin/bootstrap';
import { clearSession, getSession, setSession, subscribeSession } from '../src/services/admin/session';
import { mockMeta } from '../mock/fixtures';
import type { Schemas } from '../src/services/admin/types';
import { errorConfig } from '../src/requestErrorConfig';
const me:Schemas['AdminMe']={user_id:'test_operator',email:'synthetic@example.invalid',role:'new_role',permissions:['users:read'],session_expires_at:'2099-01-01T00:00:00Z',csrf_token:'synthetic-memory-token',capabilities:{membership_control_write:{ready:false,reason:null},account_access_write:{ready:false,reason:null},billing_amounts:{ready:false,reason:null},support_reissue:{ready:false,reason:null}}};
const deferred=<T,>()=>{let resolve!:(value:T)=>void,reject!:(value:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {resolve,reject,promise};};
beforeEach(()=>{clearSession();vi.mocked(request).mockReset();});
describe('atomic bootstrap and request ordering',()=>{
 it('publishes me and real meta together once, never an interim csrf-only state',async()=>{
  const metadata=deferred<Schemas['AdminMeta']>(),snapshots:unknown[]=[];const stop=subscribeSession(()=>snapshots.push(getSession()));
  vi.mocked(request).mockResolvedValueOnce(me).mockReturnValueOnce(metadata.promise as never);
  const loading=bootstrapSession({});await Promise.resolve();await Promise.resolve();
  expect(getSession().me).toBeUndefined();expect(snapshots).toHaveLength(0);
  metadata.resolve(mockMeta('2026-10-26T00:00:00Z'));const state=await loading;stop();
  expect(state.me).toEqual(me);expect(state.meta?.pagination.max_page_size).toBe(50);expect(snapshots).toHaveLength(1);
 });
 it('keeps meta 503 as an unavailable bootstrap error and clears all authority',async()=>{
  setSession(me);vi.mocked(request).mockResolvedValueOnce(me).mockRejectedValueOnce({response:{status:503}});
  const state=await bootstrapSession({});expect(state).toMatchObject({permissions:[],bootstrapError:{status:503}});expect(state.me).toBeUndefined();expect(state.meta).toBeUndefined();expect(getSession()).toEqual({clearReason:'bootstrap'});
 });
 it('does not fabricate metadata after malformed success or invalid pagination',async()=>{
  for(const meta of [{}, {...mockMeta('2026-10-26T00:00:00Z'),pagination:{default_page:1,default_page_size:90,max_page_size:50}}]){
   vi.mocked(request).mockResolvedValueOnce(me).mockResolvedValueOnce(meta);const state=await bootstrapSession({});expect(state.bootstrapError).toBeDefined();expect(state.meta).toBeUndefined();expect(state.permissions).toEqual([]);
  }
 });
 it('late 401 cannot clear a replacement session',async()=>{
  setSession(me);const old=deferred<unknown>();vi.mocked(request).mockReturnValueOnce(old.promise as never);const pending=adminApi.adminListUsers();setSession({...me,email:'new@example.invalid'});old.reject({response:{status:401}});
  await expect(pending).rejects.toMatchObject({status:409,errorType:'session_changed'});expect(getSession().me?.email).toBe('new@example.invalid');
 });
 it('late successful read is rejected after 401 clears the session',async()=>{
  setSession(me);const old=deferred<unknown>();vi.mocked(request).mockReturnValueOnce(old.promise as never).mockRejectedValueOnce({response:{status:401}});const pending=adminApi.adminListUsers();
  await expect(adminApi.adminOverview()).rejects.toMatchObject({status:401});old.resolve({items:[{id:'old-private-data'}]});await expect(pending).rejects.toMatchObject({errorType:'session_changed'});expect(getSession().me).toBeUndefined();
 });
 it('late bootstrap never publishes into a replacement session',async()=>{
  const old=deferred<Schemas['AdminMeta']>();vi.mocked(request).mockResolvedValueOnce(me).mockReturnValueOnce(old.promise as never);const pending=bootstrapSession({});await Promise.resolve();await Promise.resolve();
  setSession({...me,email:'replacement@example.invalid'});old.resolve(mockMeta('2026-10-26T00:00:00Z'));await expect(pending).rejects.toMatchObject({errorType:'session_changed'});expect(getSession().me?.email).toBe('replacement@example.invalid');
 });
 it('adminMe alone never changes the authority store',async()=>{vi.mocked(request).mockResolvedValueOnce(me);await adminApi.adminMe();expect(getSession().me).toBeUndefined();});
 it('rejects expired session projection before metadata request',async()=>{vi.mocked(request).mockResolvedValueOnce({...me,session_expires_at:'2000-01-01T00:00:00Z'});const state=await bootstrapSession({});expect(state.permissions).toEqual([]);expect(request).toHaveBeenCalledTimes(1);});
 it('preserves login 401 when installed Umi still invokes the global error handler',async()=>{
  const raw={response:{status:401}};
  vi.mocked(request).mockImplementationOnce(async(...args:unknown[])=>{
   errorConfig.errorConfig!.errorHandler!(raw as unknown as Error,args[1] as Parameters<NonNullable<NonNullable<typeof errorConfig.errorConfig>['errorHandler']>>[1]);throw raw;
  });
  await expect(adminApi.adminLogin({email:'synthetic@example.invalid',password:'wrong'})).rejects.toMatchObject({status:401,outcomeUnknown:false});expect(getSession().me).toBeUndefined();
 });
 it('global skipped handler does not clear a newer session before the old adapter can reject it',()=>{
  setSession({...me,email:'new@example.invalid'});const raw={response:{status:401}};
  expect(()=>errorConfig.errorConfig!.errorHandler!(raw as unknown as Error,{skipErrorHandler:true})).toThrow();expect(getSession().me?.email).toBe('new@example.invalid');
 });
 it('preserves raw 503 for write outcome decoding instead of normalizing it too early',async()=>{
  setSession(me);const raw={response:{status:503}};
  vi.mocked(request).mockImplementationOnce(async(...args:unknown[])=>{
   errorConfig.errorConfig!.errorHandler!(raw as unknown as Error,args[1] as Parameters<NonNullable<NonNullable<typeof errorConfig.errorConfig>['errorHandler']>>[1]);throw raw;
  });
  await expect(adminApi.adminSetUserAccess('synthetic',{enabled:false,reason:'a valid synthetic reason',expected_revision:'0'},'a-stable-test-key-1')).rejects.toMatchObject({status:503,outcomeUnknown:true});
 });
});

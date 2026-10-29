import { describe,expect,it } from 'vitest';
import { isDevelopmentMock, resolveDeployment } from '../config/deployment';
import { canUseFeature, toAdminQuery, validateQueryValue } from '../src/config/resourceConfig';
import { formatTime } from '../src/utils/adminFormat';
import { mockMeta } from '../mock/fixtures';
describe('production isolation and deployment prefix',()=>{
 it('only enables mock for an explicit development true flag',()=>{for(const env of [{},{NODE_ENV:'production',ADMIN_MOCK:'true'},{NODE_ENV:'development'},{NODE_ENV:'development',ADMIN_MOCK:'1'},{NODE_ENV:'test',ADMIN_MOCK:'true'}])expect(isDevelopmentMock(env)).toBe(false);expect(isDevelopmentMock({NODE_ENV:'development',ADMIN_MOCK:'true'})).toBe(true);});
 it('keeps API, static assets and hash route base independent',()=>{expect(resolveDeployment({}).deployment).toEqual({routeBase:'/',publicPath:'/admin/',apiBase:'/api/admin/v1'});expect(resolveDeployment({ADMIN_PUBLIC_PATH:'/demo/admin/',ADMIN_API_BASE:'/demo/api/admin/v1'})).toMatchObject({deployment:{routeBase:'/',publicPath:'/demo/admin/',apiBase:'/demo/api/admin/v1'},developmentProxy:undefined});});
 it('requires explicit development proxy and never applies it to production',()=>{expect(resolveDeployment({NODE_ENV:'development'}).developmentProxy).toBeUndefined();expect(resolveDeployment({NODE_ENV:'development',ADMIN_DEV_PROXY_TARGET:'http://127.0.0.1:49174'}).developmentProxy).toBeDefined();expect(resolveDeployment({NODE_ENV:'production',ADMIN_DEV_PROXY_TARGET:'http://127.0.0.1:49174'}).developmentProxy).toBeUndefined();});
 it.each(['https://external.invalid/api','//external.invalid/api','/api?secret=1','/api/../other','/api%2fother','/api\\other','/api\nother'])('rejects unsafe same-origin prefix %s',path=>{expect(()=>resolveDeployment({ADMIN_API_BASE:path})).toThrow();});
});
describe('strict metadata and wire-value boundaries',()=>{
 it('does not authorize an unknown future capability even if ready',()=>{const meta=mockMeta('2026-10-26T00:00:00Z');meta.features.future_write={ready:true};expect(canUseFeature(['future:write'],meta,'future:write','future_write')).toBe(false);});
 it('rejects local, impossible and normalized timestamps',()=>{for(const time of ['2026-02-30T00:00:00Z','2026-10-26 00:00:00','2026-10-26T00:00:00+08:00','2026-10-26T24:00:00Z']){expect(formatTime(time)).toBe('—');expect(validateQueryValue({type:'string',format:'date-time'},time)).toBe(false);}expect(formatTime('2026-10-26T00:00:00.123456Z')).toContain('UTC');});
 it('never forwards unsupported metadata filters or enum values',()=>{const meta=mockMeta('2026-10-26T00:00:00Z');meta.queries.find(q=>q.resource==='adminListJobs')!.filters.find(f=>f.name==='public_status')!.allowed_values=['future_state','done'];expect(toAdminQuery('adminListJobs',{pageSize:500,public_status:'error',internal_state:'legacy_unset'},{created_at:'descend'},{},meta)).toEqual({page:1,page_size:50,sort:'created_at:desc',internal_state:'legacy_unset'});});
 it('rejects unsafe integer values and preserves actual booleans',()=>{expect(validateQueryValue({type:'integer'},Number.MAX_SAFE_INTEGER+1)).toBe(false);expect(validateQueryValue({type:'boolean'},'false')).toBe(false);expect(validateQueryValue({type:'boolean'},false)).toBe(true);});
});

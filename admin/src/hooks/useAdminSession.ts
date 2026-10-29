import { useModel } from '@umijs/max';
import { bootstrapSession } from '../services/admin/bootstrap';
import { clearSession } from '../services/admin/session';
import { canUseFeature } from '../config/resourceConfig';
import type { Schemas } from '../services/admin/types';
export function useAdminSession() {
  const {initialState,setInitialState}=useModel('@@initialState');
  const permissions=initialState?.permissions??[];
  return {me:initialState?.me,meta:initialState?.meta,permissions,
    can:(permission:string)=>permissions.includes(permission),
    canFeature:(permission:string,feature:keyof Schemas['Capabilities'])=>canUseFeature(permissions,initialState?.meta,permission,feature),
    reload:async()=>{const state=await bootstrapSession(initialState?.settings??{});await setInitialState(state);return state;},
    clear:()=>{clearSession();void setInitialState(previous=>({...previous,settings:previous?.settings??{},permissions:[],me:undefined,meta:undefined}));},
  };
}

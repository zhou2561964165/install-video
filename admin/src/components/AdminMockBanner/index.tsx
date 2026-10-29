import { Alert } from 'antd';
import { useLayoutEffect, useRef } from 'react';
/** Reserve the actual development warning height for fixed portal drawers. */
export function AdminMockBanner() {
 const ref=useRef<HTMLDivElement>(null);
 useLayoutEffect(()=>{
  const update=()=>document.documentElement.style.setProperty('--admin-mock-banner-height',`${ref.current?.getBoundingClientRect().height??0}px`);
  update();const observer=new ResizeObserver(update);if(ref.current)observer.observe(ref.current);
  return ()=>{observer.disconnect();document.documentElement.style.removeProperty('--admin-mock-banner-height');};
 },[]);
 return <div ref={ref} className="admin-mock-banner"><Alert role="status" type="warning" title="模拟数据 · 仅开发环境 · 所有账号与记录均为合成" banner/></div>;
}

import {createContext,useContext,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {useLocation,useNavigate,useNavigationType} from 'react-router-dom';
import {Button} from './primitives';
import './PageBack.css';

type Entry={key:string;url:string};
export type BackHistory={scope:string;entries:Entry[];index:number};
export const emptyBackHistory:BackHistory={scope:'',entries:[],index:-1};
export function backArea(path:string):string {
 if(path==='/app'||path.startsWith('/app/'))return 'work';
 if((path==='/superadmin'||path.startsWith('/superadmin/'))&&!/^\/superadmin\/login(?:\/|$)/.test(path))return 'management';
 return '';
}
export function backFallback(path:string):string {
 const clean=path.replace(/\/+$/,'');
 const device=clean.match(/^\/app\/maintenance\/devices\/([^/]+)\/(profile|report|timeline)$/);
 if(device)return device[2]==='profile'?'/app/maintenance/equipment':`/app/maintenance/devices/${device[1]}/profile`;
 if(/^\/app\/maintenance\/dashboard\/[^/]+$/.test(clean))return '/app/maintenance/dashboard';
 if(clean.startsWith('/app/administration/')&&clean!=='/app/administration/users')return '/app/administration/users';
 if(backArea(clean)==='management')return '/superadmin';
 return '/app/dashboard';
}
// Only navigation observed during this authenticated lifetime is trusted. Never consult
// history.length, referrer, localStorage, or a caller-supplied return URL.
export function advanceBackHistory(previous:BackHistory,entry:Entry,action:string,scope:string):BackHistory {
 if(!scope)return emptyBackHistory;
 if(previous.scope!==scope||!previous.entries.length)return {scope,entries:[entry],index:0};
 if(previous.entries[previous.index]?.key===entry.key&&previous.entries[previous.index]?.url===entry.url)return previous;
 if(action==='POP'){
  const index=previous.entries.findIndex(e=>e.key===entry.key);
  return index<0?{scope,entries:[entry],index:0}:{...previous,index};
 }
 if(action==='REPLACE'){
  const entries=previous.entries.slice();entries[previous.index]=entry;return {...previous,entries};
 }
 const entries=[...previous.entries.slice(0,previous.index+1),entry].slice(-100);
 return {scope,entries,index:entries.length-1};
}
const BackContext=createContext({canBack:false,homeRoute:"/app/dashboard",unknownHome:"/app/dashboard"});
export function PageBackProvider({identityKey,homeRoute="/app/dashboard",administrative=false,children}:{identityKey:string;homeRoute?:string;administrative?:boolean;children:ReactNode}){
 const location=useLocation();const action=useNavigationType();
 const [history,setHistory]=useState<BackHistory>(emptyBackHistory);
 const area=backArea(location.pathname);const scope=identityKey&&area?identityKey+'|'+area:'';
 const url=location.pathname+location.search+location.hash;
 useLayoutEffect(()=>{setHistory(old=>advanceBackHistory(old,{key:location.key,url},action,scope));},[location.key,url,action,scope]);
 const canBack=!!scope&&history.scope===scope&&history.index>0&&history.entries[history.index]?.key===location.key;
 const safeHome=homeRoute.startsWith("/app/")&&!/[\\\r\n]/.test(homeRoute)?homeRoute:"/app/dashboard";
 return <BackContext.Provider value={{canBack,homeRoute:safeHome,unknownHome:administrative?"/superadmin":safeHome}}>{children}</BackContext.Provider>;
}
export function usePageBack(){
 const {canBack,homeRoute,unknownHome}=useContext(BackContext);const navigate=useNavigate();const location=useLocation();
 // Native history.go is asynchronous. Ignore repeated activations for the same
 // location until the router observes its completion, so a double click cannot
 // consume an untrusted entry beyond the one allowed previous page.
 const pendingKey=useRef<string|null>(null);
 useLayoutEffect(()=>{pendingKey.current=null;},[location.key,location.pathname,location.search,location.hash]);
 const parent=backFallback(location.pathname);const fallback=!backArea(location.pathname)?unknownHome:parent==="/app/dashboard"?homeRoute:parent;
 const homeDestination=backArea(location.pathname)==="management"||(!backArea(location.pathname)&&unknownHome==="/superadmin")?"/superadmin":homeRoute;
 return {canBack,homeRoute,homeDestination,goBack:()=>{if(pendingKey.current===location.key)return;pendingKey.current=location.key;if(canBack)void navigate(-1);else void navigate(fallback,{replace:true});}};
}
export function PageBack({standalone=false}:{standalone?:boolean}){
 const location=useLocation();const {canBack,homeRoute,goBack}=usePageBack();const path=location.pathname.replace(/\/+$/,'');
 if(/^\/(?:login(?:\/|$)|superadmin\/login(?:\/|$))/.test(path))return null;
 if(!standalone&&(backArea(path)!=='work'||path==='/app'||path==='/app/dashboard'||(!canBack&&path===homeRoute.replace(/\/+$/,''))))return null;
 return <div className="page-back-bar" dir="rtl"><Button type="button" variant="ghost" icon="arrowRight" aria-label="بازگشت به صفحهٔ قبلی" title={canBack?'بازگشت به صفحهٔ قبلی':'بازگشت به صفحهٔ بالادستی'} onClick={goBack}>بازگشت</Button></div>;
}

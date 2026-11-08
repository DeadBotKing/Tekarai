import { previewWorkspaceCatalog } from './workspacePreviewCatalog';
import type { NavigationItem } from '../../app/configuration/navigation';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useApiClient } from '../api/apiContext';
import { useAuth } from '../auth/authContext';
export interface WorkspaceModule {code:string;label:string;route:string;actionPrefixes:string[];apiPrefixes?:string[];permissions:string[];requires:string[]}
export interface OrganizationWorkspace {permissions?:string[];tenantId:string;tenantCode:string;title:string;introduction:string;homeMode:'legacy'|'cards'|'list';homeModule?:string;enabledModules:string[];menuOrder:string[];revision:number;catalog:WorkspaceModule[]}
export function routeModule(path:string):string|null {
 const p=path.split('?')[0];
 if(p.startsWith('/app/extensions/'))return p.split('/')[3]||'__unknown';
 for(const [prefix,key] of [['/app/documents','documents'],['/app/projects','projects'],['/app/tasks','tasks'],['/app/chat','communication'],['/app/intelligence','intelligence'],['/app/maintenance/procurement','procurement'],['/app/maintenance/permits','safety'],['/app/maintenance','maintenance']]) {
  if(p===prefix||p.startsWith(prefix+'/'))return key;
 }
 return null;
}
export function workspaceAllows(workspace:OrganizationWorkspace|null,path:string):boolean {const key=routeModule(path);return !key||!!workspace?.enabledModules.includes(key);}
export function workspaceActionAllows(workspace:OrganizationWorkspace|null,action:string):boolean {
 const matches=workspace?.catalog.flatMap(m=>m.actionPrefixes.filter(p=>action.startsWith(p)).map(p=>({length:p.length,code:m.code}))).sort((a,b)=>b.length-a.length)||[];
 if(matches.length)return !!workspace?.enabledModules.includes(matches[0].code);
 // Core stays available; business actions fail closed before the workspace is loaded.
 return !/^(maintenance|analytics|asset|project|task|document|procurement|safety|communication|projectIntelligence|ai|learning|extension)\./.test(action);
}
type State={workspace:OrganizationWorkspace|null;loading:boolean;error:string;reload:()=>void};
const Context=createContext<State>({workspace:null,loading:false,error:'',reload:()=>{}});
export function OrganizationWorkspaceProvider({children}:{children:ReactNode}):JSX.Element {
 const api=useApiClient();const {session,offlinePreview}=useAuth();const [tick,setTick]=useState(0);
 const key=session ? session.user.id+':'+session.accessToken : '';
 const [state,setState]=useState<{key:string;workspace:OrganizationWorkspace|null;loading:boolean;error:string}>({key:'',workspace:null,loading:false,error:''});
 useEffect(()=>{let active=true;if(!key){setState({key,workspace:null,loading:false,error:''});return;}
 if(offlinePreview){setState({key,workspace:{tenantId:'preview',tenantCode:'platform',title:'محیط نمایشی',introduction:'',homeMode:'legacy',enabledModules:previewWorkspaceCatalog.map(m=>m.code),menuOrder:[],revision:0,catalog:previewWorkspaceCatalog},loading:false,error:''});return;}
 setState({key,workspace:null,loading:true,error:''});
 api.get<OrganizationWorkspace>('organization-workspace/current',{retry:0}).then(workspace=>{
  if(!workspace?.tenantId||!Array.isArray(workspace.enabledModules)||!Array.isArray(workspace.catalog))throw new Error('تنظیمات محیط سازمان دریافت نشد.');
  if(active)setState({key,workspace,loading:false,error:''});
 }).catch(e=>{if(active)setState({key,workspace:null,loading:false,error:e instanceof Error?e.message:'دریافت محیط سازمان ناموفق بود.'});});
 return()=>{active=false;};},[api,key,tick,offlinePreview]);
 useEffect(()=>{const reload=()=>setTick(t=>t+1);window.addEventListener('tekarai:workspace-updated',reload);return()=>window.removeEventListener('tekarai:workspace-updated',reload);},[]);
 const matched=state.key===key;
 return <Context.Provider value={{workspace:matched?state.workspace:null,loading:!!key&&(!matched||state.loading),error:matched?state.error:'',reload:()=>setTick(t=>t+1)}}>{children}</Context.Provider>;
}
export const useOrganizationWorkspace=()=>useContext(Context);

export function composeWorkspaceNavigation(items:NavigationItem[],workspace:OrganizationWorkspace|null):NavigationItem[] {
 const extra:NavigationItem[]=(workspace?.catalog.filter(m=>m.route.startsWith('/app/extensions/')&&workspace.enabledModules.includes(m.code))||[]).map(m=>({id:'extension-'+m.code,label:'nav.workspace',displayLabel:m.label,icon:'layers',children:[{id:m.code,label:'nav.workspace',displayLabel:m.label,icon:'layers',route:m.route,anyPermission:m.permissions}]}));
 const rank=(item:NavigationItem)=>{if(item.id==='workspace')return -2;if(item.id==='administration')return -1;const code=routeModule(item.route||item.children?.[0]?.route||'');const index=workspace?.menuOrder.indexOf(code||'')??-1;return index<0?999:index;};
 const compose=(nodes:NavigationItem[]):NavigationItem[]=>nodes.filter(n=>!n.route||workspaceAllows(workspace,n.route)).map(n=>({...n,children:n.children?compose(n.children):undefined})).filter(n=>!n.children||n.children.length>0).sort((a,b)=>workspace?.menuOrder.length?rank(a)-rank(b):0);
 return compose([...items,...extra]);
}

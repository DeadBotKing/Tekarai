import { Link, useParams, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
const DashboardPage=lazy(()=>import('./DashboardPage').then(m=>({default:m.DashboardPage}))); 
import { useOrganizationWorkspace } from '../core/tenant/organizationWorkspace';
import { usePermissions } from '../core/permissions/permissionContext';
import { workspaceExtensions } from '../core/tenant/workspaceExtensions';
export function OrganizationHomePage():JSX.Element {
 const {workspace}=useOrganizationWorkspace();const {hasAny}=usePermissions();
 if(!workspace)return <p role="alert">محیط سازمان آماده نیست.</p>;
 const start=workspace.catalog.find(m=>m.code===workspace.homeModule&&workspace.enabledModules.includes(m.code));
 if(start&&hasAny(start.permissions))return <Navigate to={start.route} replace/>;
 if(workspace.homeMode==='legacy')return <Suspense fallback={<p>در حال بارگذاری…</p>}><DashboardPage/></Suspense>;
 const enabled=workspace.catalog.filter(m=>workspace.enabledModules.includes(m.code)&&hasAny(m.permissions)).sort((a,b)=>{
  const index=(code:string)=>{const i=workspace.menuOrder.indexOf(code);return i<0?999:i;};return index(a.code)-index(b.code);
 });
 return <section dir="rtl" style={{padding:24}}><h1>{workspace.title}</h1><p style={{whiteSpace:'pre-wrap'}}>{workspace.introduction||'به محیط اختصاصی سازمان خود خوش آمدید.'}</p>
 {enabled.length?<nav aria-label="امکانات سازمان" style={{display:'grid',gridTemplateColumns:workspace.homeMode==='cards'?'repeat(auto-fit,minmax(210px,1fr))':'1fr',gap:16}}>{enabled.map(m=><Link key={m.code} to={m.route} style={{padding:24,border:'1px solid #e2ded3',borderRadius:12,background:'#fffdf7',color:'#214d3d'}}>{m.label}</Link>)}</nav>:<p>هنوز امکانی برای شما فعال نشده است. مدیر سازمان دسترسی‌ها و مدیر کل امکانات سازمان را تعیین می‌کنند.</p>}</section>;
}
export function OrganizationExtensionPage():JSX.Element {
 const {extensionCode=''}=useParams();const {workspace}=useOrganizationWorkspace();const {hasAny}=usePermissions();
 const metadata=workspace?.catalog.find(m=>m.code===extensionCode);const Component=workspaceExtensions[extensionCode];
 if(!metadata||!workspace?.enabledModules.includes(extensionCode)||!hasAny(metadata.permissions))return <p role="alert">این قابلیت در دسترس شما نیست.</p>;
 return Component?<Component/>:<p role="alert">رابط این قابلیت در نسخه نصب‌شده موجود نیست؛ با مدیر کل تماس بگیرید.</p>;
}

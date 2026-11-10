import {useLayoutEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {useApiClient} from '../core/api/apiContext';
import {useAuth} from '../core/auth/authContext';
import {useOrganizationWorkspace} from '../core/tenant/organizationWorkspace';
import {Button,Card,SectionHeader} from '../shared/components/primitives';
import './AssistantPage.css';

type Scope='all'|'maintenance'|'documents'|'projects';
type Choice={id:string;label:string};
type Catalog={ready:boolean;state:string;model:string;scopes:Scope[];devices:Choice[];projects:Choice[];documents:Choice[]};
type Source={id:string;title:string;href:string;version:string;page:number|null;excerpt:string};
type Answer={answer:string;sources:Source[];warnings:string[];asOf:string;readOnly:boolean;localOnly:boolean};
const labels:Record<Scope,string>={all:'دستیار مشترک',maintenance:'تجهیزات و تعمیرات',documents:'پرسش از مستندات',projects:'پروژه‌ها و کارها'};
const states:Record<string,string>={ready:'مدل محلی در دسترس است؛ کیفیت پاسخ نیاز به بررسی شما دارد.',offline:'سرویس مدل محلی در دسترس نیست؛ راه‌اندازی Ollama روی سرور را بررسی کنید.',model_missing:'مدل انتخاب‌شده یا نسخهٔ تأییدشدهٔ آن روی سرور آماده نیست.',disabled:'دستیار در تنظیمات سرور غیرفعال است.',memory_low:'حافظهٔ آزاد سرور برای پاسخ جدید کافی نیست؛ برای حفظ عملکرد سایت منتظر بمانید.'};
export function safeAssistantLink(href:string):boolean{return /^\/app\/(?:documents|projects|tasks|maintenance\/devices\/[a-f0-9-]{36}\/profile|maintenance\/work-orders(?:\?search=[a-f0-9-]{36})?)$/i.test(href);}
export function AssistantPage():JSX.Element{
 const api=useApiClient();const {session}=useAuth();const {workspace}=useOrganizationWorkspace();
 const identity=[session?.user.id,workspace?.tenantId,session?.user.role,(workspace?.permissions||session?.user.permissions||[]).join('|')].join(':');
 const [catalog,setCatalog]=useState<Catalog|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [scope,setScope]=useState<Scope>('all');
 const [question,setQuestion]=useState('');const [device,setDevice]=useState('');const [project,setProject]=useState('');const [documents,setDocuments]=useState<string[]>([]);
 const [answers,setAnswers]=useState<{question:string;result:Answer}[]>([]);const [busy,setBusy]=useState(false);const [tick,setTick]=useState(0);
 const sequence=useRef(0);const active=useRef<AbortController|null>(null);const output=useRef<HTMLDivElement|null>(null);
 useLayoutEffect(()=>{
  const version=++sequence.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  setCatalog(null);setLoading(true);setBusy(false);setError('');setAnswers([]);setQuestion('');setScope('all');setDevice('');setProject('');setDocuments([]);
  api.get<Catalog>('assistant/status',{signal:controller.signal,retry:0,timeoutMs:15000}).then(value=>{
   if(sequence.current!==version)return;
   if(!value||typeof value.ready!=='boolean'||!Array.isArray(value.scopes)||![value.devices,value.projects,value.documents].every(list=>Array.isArray(list)&&list.every(c=>c&&typeof c.id==='string'&&typeof c.label==='string')))throw new Error('پاسخ وضعیت دستیار معتبر نیست.');
   setCatalog(value);
  }).catch(()=>{if(!controller.signal.aborted&&sequence.current===version)setError('وضعیت دستیار دریافت نشد. فعال بودن «دستیار هوشمند» در امکانات سازمان و مجوز خواندن منابع را بررسی کنید.');}).finally(()=>{if(sequence.current===version)setLoading(false);});
  return()=>{sequence.current++;controller.abort();active.current?.abort();};
 },[api,identity,tick]);
 function changeScope(value:Scope){setScope(value);setDevice('');setProject('');setDocuments([]);setAnswers([]);setError('');}
 async function ask(){
  if(busy||!catalog?.ready||question.trim().length<3)return;
  const q=question.trim(),version=sequence.current;const controller=new AbortController();active.current=controller;setBusy(true);setError('');
  try{
   const response=await api.post<Answer>('assistant/ask',{question:q,scope,...(device?{deviceId:device}:{}),...(project?{projectId:project}:{}),documentIds:documents},{signal:controller.signal,retry:0,timeoutMs:150000});
   if(sequence.current!==version)return;
   if(!response||typeof response.answer!=='string'||!Array.isArray(response.sources)||!Array.isArray(response.warnings)||response.readOnly!==true||response.localOnly!==true)throw new Error('پاسخ دستیار معتبر نیست.');
   setAnswers(previous=>[...previous.slice(-3),{question:q,result:response}]);setQuestion('');requestAnimationFrame(()=>output.current?.focus());
  }catch(e){if(!controller.signal.aborted&&sequence.current===version)setError(e instanceof Error?e.message:'پاسخ دریافت نشد؛ دوباره تلاش کنید.');}
  finally{if(sequence.current===version)setBusy(false);}
 }
 const allowed=(s:Scope)=>s==='all'||!!catalog?.scopes.includes(s);
 return <section className="page assistant-page" dir="rtl">
  <SectionHeader eyebrow="هوش مصنوعی محلی" title="دستیار هوشمند سازمان" subtitle="پاسخ از منابع مجاز شما؛ بدون ارسال به سرویس ابری و بدون تغییر خودکار اطلاعات."/>
  <Card padding="md"><div className="assistant-status"><div role="status">{loading?'در حال بررسی دسترسی و مدل…':catalog?(states[catalog.state]||'وضعیت مدل نامشخص است.'):''}</div><Button type="button" variant="ghost" icon="refresh" disabled={busy||loading} onClick={()=>setTick(t=>t+1)}>بررسی دوباره</Button></div>
   <p className="assistant-note">این دستیار جایگزین تصمیم فنی، دستورالعمل مصوب یا تأیید مسئول نیست. هر پرسش مستقل بررسی می‌شود. گفتگو فقط در حافظهٔ همین صفحه نگه داشته می‌شود و با خروج پاک می‌شود.</p>
   <div className="assistant-scopes" role="group" aria-label="بخش پرسش">{(Object.keys(labels) as Scope[]).filter(allowed).map(s=><Button key={s} type="button" variant={scope===s?'primary':'secondary'} aria-pressed={scope===s} disabled={busy||loading||!catalog} onClick={()=>changeScope(s)}>{labels[s]}</Button>)}</div>
   {catalog&&<form onSubmit={event=>{event.preventDefault();void ask();}}>
    <fieldset disabled={busy} className="assistant-filters"><legend>محدود کردن منابع — اختیاری</legend>
     {(scope==='all'||scope==='maintenance'||scope==='documents')&&catalog.devices.length>0&&<label>دستگاه<select aria-label="دستگاه" value={device} onChange={e=>setDevice(e.target.value)}><option value="">نمونهٔ دستگاه‌های مجاز</option>{catalog.devices.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
     {(scope==='all'||scope==='projects')&&catalog.projects.length>0&&<label>پروژه<select aria-label="پروژه" value={project} onChange={e=>setProject(e.target.value)}><option value="">نمونهٔ پروژه‌ها و کارهای مجاز</option>{catalog.projects.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
     {(scope==='all'||scope==='documents')&&catalog.documents.length>0&&<label>سند — حداکثر دو مورد<select aria-label="اسناد" multiple value={documents} onChange={e=>setDocuments(Array.from(e.target.selectedOptions).map(o=>o.value).slice(0,2))}>{catalog.documents.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select><small>بدون انتخاب: جست‌وجوی محدود بین اسناد اخیرِ مجاز</small></label>}
    </fieldset>
    <label className="assistant-question">پرسش شما<textarea aria-label="پرسش شما" autoComplete="off" maxLength={400} rows={4} disabled={busy} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="نام دستگاه، مشکل یا موضوع سند را مشخص کنید…"/></label>
    <div className="assistant-actions"><Button type="submit" variant="primary" icon="sparkles" disabled={busy||!catalog.ready||question.trim().length<3}>{busy?'در حال بررسی منابع و تولید پاسخ…':'پرسیدن از دستیار'}</Button><Button type="button" variant="ghost" disabled={busy||(!answers.length&&!question)} onClick={()=>{setAnswers([]);setQuestion('');setError('');}}>پاک کردن گفتگو</Button></div>
   </form>}
   {error&&<p role="alert" className="assistant-error">{error}</p>}
  </Card>
  <div ref={output} tabIndex={-1} aria-label="پاسخ‌های دستیار" className="assistant-answers">{answers.map((item,index)=><Card key={index} padding="md"><h2>{item.question}</h2><p className="assistant-answer">{item.result.answer}</p><p className="assistant-note">خروجی مدل تأیید انسانی نشده است. زمان آغاز بررسی منابع: {item.result.asOf}</p>
   {item.result.sources.length>0&&<div className="assistant-sources"><h3>منابع مورد استناد</h3>{item.result.sources.map((s,i)=><details key={s.id+':'+i}><summary>{s.id} — {s.title}{s.page?` · صفحهٔ ${s.page}`:''}</summary><p className="assistant-excerpt">{s.excerpt}</p><small>اثر انگشت نسخه: {s.version}</small>{safeAssistantLink(s.href)&&<Link to={s.href}>رفتن به بخش منبع</Link>}</details>)}</div>}
   <ul className="assistant-note">{item.result.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul>
  </Card>)}</div>
 </section>;
}

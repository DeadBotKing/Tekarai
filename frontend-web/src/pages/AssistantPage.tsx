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
type PdfTable={headers:string[];rows:string[][];direction:'rtl'|'ltr'};
type Source={id:string;title:string;href:string;version:string;page:number|null;excerpt:string;documentFormat?:string;tables?:PdfTable[];citedByModel?:boolean};
type Coverage={scope:Scope;selectionMode:'documents'|'filtered'|'sample';selectedDocumentCount:number;excerptOnly:true;reviewedSources:{id:string;title:string;page:number|null;documentFormat:string;citedByModel:boolean}[]};
type Answer={coverage?:Coverage;answer:string;sources:Source[];warnings:string[];asOf:string;readOnly:boolean;localOnly:boolean};
const labels:Record<Scope,string>={all:'دستیار مشترک',maintenance:'تجهیزات و تعمیرات',documents:'پرسش از مستندات',projects:'پروژه‌ها و کارها'};
const states:Record<string,string>={ready:'مدل محلی در دسترس است؛ کیفیت پاسخ نیاز به بررسی شما دارد.',offline:'سرویس مدل محلی در دسترس نیست؛ راه‌اندازی Ollama روی سرور را بررسی کنید.',model_missing:'مدل انتخاب‌شده یا نسخهٔ تأییدشدهٔ آن روی سرور آماده نیست.',disabled:'دستیار در تنظیمات سرور غیرفعال است.',memory_low:'حافظهٔ آزاد سرور برای پاسخ جدید کافی نیست؛ برای حفظ عملکرد سایت منتظر بمانید.'};
export function safeAssistantLink(href:string):boolean{return /^\/app\/(?:documents|projects|tasks|maintenance\/devices\/[a-f0-9-]{36}\/profile|maintenance\/work-orders(?:\?search=[a-f0-9-]{36})?)$/i.test(href);}
export function safePdfTables(value:unknown):PdfTable[]{
 if(!Array.isArray(value)||value.length>2)return [];
 let total=0;
 for(const t of value){if(!t||!['rtl','ltr'].includes(t.direction)||!Array.isArray(t.headers)||t.headers.length<2||t.headers.length>12||!Array.isArray(t.rows)||t.rows.length<1||t.rows.length>12||t.headers.length*t.rows.length>120)return [];
  if(t.rows.some((row:unknown)=>!Array.isArray(row)||row.length!==t.headers.length)||[t.headers,...t.rows].some((row:unknown[])=>row.some(c=>typeof c!=='string'||c.length>160)))return [];
  total+=JSON.stringify(t).length;if(total>6000)return [];
 }
 return value as PdfTable[];
}
export function safeCoverage(value:unknown):Coverage|null{
 if(!value||typeof value!=='object')return null;
 const c=value as Coverage;
 if(!Object.keys(labels).includes(c.scope)||!['documents','filtered','sample'].includes(c.selectionMode)||c.excerptOnly!==true||!Number.isInteger(c.selectedDocumentCount)||c.selectedDocumentCount<0||c.selectedDocumentCount>2||!Array.isArray(c.reviewedSources)||c.reviewedSources.length>3)return null;
 if(c.reviewedSources.some(r=>!r||typeof r.id!=='string'||!/^S[1-3]$/.test(r.id)||typeof r.title!=='string'||r.title.length>500||!(r.page===null||(Number.isInteger(r.page)&&r.page>0&&r.page<=15))||typeof r.documentFormat!=='string'||typeof r.citedByModel!=='boolean')||new Set(c.reviewedSources.map(r=>r.id)).size!==c.reviewedSources.length)return null;
 return c;
}
const suggestions:Record<Scope,string[]>={
 all:['از منابع انتخاب‌شده چه اطلاعاتی دربارهٔ این موضوع موجود است؟','چه اطلاعاتی برای پاسخ دقیق‌تر در منابع بررسی‌شده موجود نیست؟'],
 documents:['این سند دربارهٔ چیست و چه اطلاعاتی در آن ثبت می‌شود؟','موارد ثبت‌شده و اطلاعات نامشخص این سند را جداگانه توضیح بده.'],
 maintenance:['وضعیت و سوابق ثبت‌شدهٔ دستگاه انتخاب‌شده را خلاصه کن.','در سوابق بررسی‌شده چه مشکلاتی ثبت شده و چه اطلاعاتی برای بررسی فنی کم است؟'],
 projects:['وضعیت ثبت‌شدهٔ پروژه و کارهای آن را خلاصه کن.','کدام کارها طبق تاریخ‌های ثبت‌شده عقب افتاده‌اند؟ اگر تاریخ کافی نیست، مشخص کن.']
};
export function AssistantPage():JSX.Element{
 const api=useApiClient();const {session}=useAuth();const {workspace}=useOrganizationWorkspace();
 const identity=[session?.user.id,workspace?.tenantId,session?.user.role,(workspace?.permissions||session?.user.permissions||[]).join('|')].join(':');
 const [catalog,setCatalog]=useState<Catalog|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [scope,setScope]=useState<Scope>('all');
 const [question,setQuestion]=useState('');const [device,setDevice]=useState('');const [project,setProject]=useState('');const [documents,setDocuments]=useState<string[]>([]);const [documentSearch,setDocumentSearch]=useState('');
 const [answers,setAnswers]=useState<{question:string;result:Answer;context:string}[]>([]);const [busy,setBusy]=useState(false);const [tick,setTick]=useState(0);
 const sequence=useRef(0);const active=useRef<AbortController|null>(null);const output=useRef<HTMLDivElement|null>(null);
 useLayoutEffect(()=>{
  const version=++sequence.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  setCatalog(null);setLoading(true);setBusy(false);setError('');setAnswers([]);setQuestion('');setScope('all');setDevice('');setProject('');setDocuments([]);setDocumentSearch('');
  api.get<Catalog>('assistant/status',{signal:controller.signal,retry:0,timeoutMs:15000}).then(value=>{
   if(sequence.current!==version)return;
   if(!value||typeof value.ready!=='boolean'||!Array.isArray(value.scopes)||![value.devices,value.projects,value.documents].every(list=>Array.isArray(list)&&list.every(c=>c&&typeof c.id==='string'&&typeof c.label==='string')))throw new Error('پاسخ وضعیت دستیار معتبر نیست.');
   setCatalog(value);
  }).catch(()=>{if(!controller.signal.aborted&&sequence.current===version)setError('وضعیت دستیار دریافت نشد. فعال بودن «دستیار هوشمند» در امکانات سازمان و مجوز خواندن منابع را بررسی کنید.');}).finally(()=>{if(sequence.current===version)setLoading(false);});
  return()=>{sequence.current++;controller.abort();active.current?.abort();};
 },[api,identity,tick]);
 function changeScope(value:Scope){setScope(value);setDevice('');setProject('');setDocuments([]);setDocumentSearch('');setAnswers([]);setError('');}
 function chooseDocuments(next:string[]){if(next.length>2)return;setDocuments(next);setAnswers([]);setError('');if(next.length){setDevice('');setProject('');}}
 const searchKey=(text:string)=>text.toLocaleLowerCase().replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/\u200c/g,' ').trim();
 const visibleDocuments=(catalog?.documents||[]).filter(item=>searchKey(item.label).includes(searchKey(documentSearch)));
 async function ask(){
  if(busy||!catalog?.ready||question.trim().length<3)return;
  const q=question.trim(),version=sequence.current;const controller=new AbortController();active.current=controller;setBusy(true);setError('');
  try{
   const response=await api.post<Answer>('assistant/ask',{question:q,scope,...(device?{deviceId:device}:{}),...(project?{projectId:project}:{}),documentIds:documents},{signal:controller.signal,retry:0,timeoutMs:150000});
   if(sequence.current!==version)return;
   if(!response||typeof response.answer!=='string'||!Array.isArray(response.sources)||!Array.isArray(response.warnings)||response.readOnly!==true||response.localOnly!==true)throw new Error('پاسخ دستیار معتبر نیست.');
   setAnswers(previous=>[...previous.slice(-3),{question:q,result:response,context:documents.length?documents.map(id=>catalog.documents.find(c=>c.id===id)?.label||'سند انتخاب‌شده').join('، '):[labels[scope],catalog.devices.find(c=>c.id===device)?.label,catalog.projects.find(c=>c.id===project)?.label].filter(Boolean).join(' — ')}]);setQuestion('');requestAnimationFrame(()=>output.current?.focus());
  }catch(e){if(!controller.signal.aborted&&sequence.current===version)setError(e instanceof Error?e.message:'پاسخ دریافت نشد؛ دوباره تلاش کنید.');}
  finally{if(sequence.current===version)setBusy(false);}
 }
 const suggestedScope=documents.length?'documents':scope;
 const allowed=(s:Scope)=>s==='all'||!!catalog?.scopes.includes(s);
 return <section className="page assistant-page" dir="rtl">
  <SectionHeader eyebrow="هوش مصنوعی محلی" title="دستیار هوشمند سازمان" subtitle="پاسخ از منابع مجاز شما؛ بدون ارسال به سرویس ابری و بدون تغییر خودکار اطلاعات."/>
  <Card padding="md"><div className="assistant-status"><div role="status">{loading?'در حال بررسی دسترسی و مدل…':catalog?(states[catalog.state]||'وضعیت مدل نامشخص است.'):''}</div><Button type="button" variant="ghost" icon="refresh" disabled={busy||loading} onClick={()=>setTick(t=>t+1)}>بررسی دوباره</Button></div>
   <p className="assistant-note">هر پرسش مستقل است؛ پاسخ را با منبع تطبیق دهید. دستیار اطلاعات را تغییر نمی‌دهد.</p>
   <details className="assistant-help"><summary>راهنمای استفاده و حریم خصوصی</summary><p className="assistant-note">برای نتیجهٔ دقیق‌تر، بخش و منبع مشخص انتخاب کنید. این دستیار جایگزین تصمیم فنی، دستورالعمل مصوب یا تأیید مسئول نیست. هر پرسش مستقل بررسی می‌شود. گفتگو فقط در حافظهٔ همین صفحه نگه داشته می‌شود و با خروج پاک می‌شود. تاریخچهٔ قبلی به مدل فرستاده نمی‌شود.</p></details>
   <div className="assistant-scopes" role="group" aria-label="بخش پرسش">{(Object.keys(labels) as Scope[]).filter(allowed).map(s=><Button key={s} type="button" variant={scope===s?'primary':'secondary'} aria-pressed={scope===s} disabled={busy||loading||!catalog} onClick={()=>changeScope(s)}>{labels[s]}</Button>)}</div>
   {catalog&&<form onSubmit={event=>{event.preventDefault();void ask();}}>
    {scope==='all'&&<p className="assistant-note">برای خلوت‌تر شدن انتخاب منابع، یکی از بخش‌های بالا را انتخاب کنید. حالت مشترک برای پرسش میان‌بخشی است.</p>}
    <fieldset disabled={busy} className="assistant-filters"><legend>محدود کردن منابع — اختیاری</legend>
     {(scope==='all'||scope==='maintenance')&&catalog.devices.length>0&&<label>دستگاه<select aria-label="دستگاه" disabled={documents.length>0} value={device} onChange={e=>{setDevice(e.target.value);setAnswers([]);setError('');}}><option value="">نمونهٔ دستگاه‌های مجاز</option>{catalog.devices.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
     {(scope==='all'||scope==='projects')&&catalog.projects.length>0&&<label>پروژه<select aria-label="پروژه" disabled={documents.length>0} value={project} onChange={e=>{setProject(e.target.value);setAnswers([]);setError('');}}><option value="">نمونهٔ پروژه‌ها و کارهای مجاز</option>{catalog.projects.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
     {(scope==='all'||scope==='documents')&&<fieldset className="assistant-documents" aria-describedby="assistant-document-help"><legend>انتخاب سند — حداکثر دو مورد</legend>
      <div className="assistant-document-header"><strong role="status" aria-live="polite">{documents.length.toLocaleString('fa-IR')} از ۲ سند انتخاب شده</strong><Button type="button" variant="ghost" disabled={!documents.length} onClick={()=>chooseDocuments([])}>پاک کردن انتخاب اسناد</Button></div>
      <p id="assistant-document-help" className="assistant-note">آمدن نام سند در فهرست به معنی انتخاب آن نیست؛ تیک کنار نام را بزنید. نیازی به Ctrl یا Shift نیست. فهرست شامل حداکثر ۳۰ سند اخیرِ مجاز است.</p>
      {documents.length>0?<div className="assistant-selected-documents" aria-label="اسناد انتخاب‌شده"><strong>پاسخ فقط از این اسناد تهیه می‌شود:</strong>{documents.map(id=><div key={id} className="assistant-selected-document"><span>{catalog.documents.find(item=>item.id===id)?.label||'سند انتخاب‌شده'}</span><button type="button" aria-label={`حذف از انتخاب: ${catalog.documents.find(item=>item.id===id)?.label||'سند'}`} onClick={()=>chooseDocuments(documents.filter(value=>value!==id))}>حذف از انتخاب ×</button></div>)}<small>فیلتر دستگاه و پروژه کنار گذاشته شده است. برای انتخاب آن‌ها، ابتدا انتخاب اسناد را پاک کنید.</small></div>:<p className="assistant-note assistant-no-document">هیچ سندی انتخاب نشده است. برای پرسش از یک فایل مشخص، تیک همان فایل را بزنید؛ بدون انتخاب، منابع مجاز به‌صورت نمونهٔ محدود بررسی می‌شوند.</p>}
      {catalog.documents.length>0&&<label className="assistant-document-search">جست‌وجو در همین فهرست<input type="search" aria-label="جست‌وجوی نام سند" autoComplete="off" maxLength={120} value={documentSearch} onChange={event=>setDocumentSearch(event.target.value)} placeholder="بخشی از نام فایل را بنویسید…"/></label>}
      {documents.length===2&&<p className="assistant-note">دو سند انتخاب شده است؛ برای انتخاب سند دیگر، ابتدا یکی را از انتخاب خارج کنید.</p>}
      <div className="assistant-document-list">{visibleDocuments.map(item=>{const checked=documents.includes(item.id);return <label key={item.id} className={`assistant-document-option${checked?' is-selected':''}`}><input type="checkbox" aria-label={`انتخاب سند: ${item.label}`} checked={checked} disabled={!checked&&documents.length>=2} onChange={event=>chooseDocuments(event.target.checked?[...documents,item.id]:documents.filter(id=>id!==item.id))}/><span>{item.label}</span><small aria-hidden="true">{checked?'انتخاب شده ✓':'انتخاب نشده'}</small></label>;})}</div>
      {!catalog.documents.length?<p className="assistant-note">سندی در فهرست مجاز شما موجود نیست. سند را در بخش «مستندات» ثبت کنید و سپس «بررسی دوباره» را بزنید.</p>:!visibleDocuments.length&&<p className="assistant-note">در همین فهرست سندی با این نام پیدا نشد؛ عبارت جست‌وجو را تغییر دهید.</p>}
     </fieldset>}

    </fieldset>
    <div className="assistant-suggestions" role="group" aria-label="پرسش‌های پیشنهادی"><span>شروع سریع — فقط متن پرسش را آماده می‌کند:</span>{suggestions[suggestedScope].map(q=><Button key={q} type="button" variant="secondary" disabled={busy||!catalog.ready} onClick={()=>{setQuestion(q);setError('');}}>{q}</Button>)}</div>
    <label className="assistant-question">پرسش شما<textarea aria-label="پرسش شما" autoComplete="off" maxLength={400} rows={4} disabled={busy} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="نام دستگاه، مشکل یا موضوع سند را مشخص کنید…"/></label>
    <div className="assistant-actions"><Button type="submit" variant="primary" icon="sparkles" disabled={busy||!catalog.ready||question.trim().length<3}>{busy?'در حال بررسی منابع و تولید پاسخ…':'پرسیدن از دستیار'}</Button><Button type="button" variant="ghost" disabled={busy||(!answers.length&&!question)} onClick={()=>{setAnswers([]);setQuestion('');setError('');}}>پاک کردن گفتگو</Button></div>
   </form>}
   {error&&<p role="alert" className="assistant-error">{error}</p>}
  </Card>
  <div ref={output} tabIndex={-1} aria-label="پاسخ‌های دستیار" className="assistant-answers">{answers.map((item,index)=><Card key={index} padding="md"><h2>{item.question}</h2><p className="assistant-context">منابع انتخاب‌شده هنگام پرسش: {item.context}</p>{item.result.sources.flatMap(source=>safePdfTables(source.tables).map((table,ti)=><div className="assistant-table-block" key={source.id+':'+ti}><div className="assistant-table-scroll" role="region" aria-label={`جدول ${ti+1} از ${source.title}`} tabIndex={0}><table dir={table.direction}><caption>جدول {ti+1} — {source.title}{source.page?` — صفحهٔ ${source.page}`:''} [{source.id}]</caption><thead><tr>{table.headers.map((header,ci)=><th scope="col" key={ci}>{header||`ستون ${ci+1}`}</th>)}</tr></thead><tbody>{table.rows.map((row,ri)=><tr key={ri}>{row.map((cell,ci)=><td key={ci}>{cell||'—'}</td>)}</tr>)}</tbody></table></div><p className="assistant-note">برای دیدن همهٔ ستون‌ها، جدول را افقی جابه‌جا کنید. بازسازی از مرز سلول‌های PDF است، نه جدولِ ساخته‌شده توسط مدل. «—» یعنی متنی از این سلول استخراج نشده است؛ برای امضا و تصویر، اصل سند را ببینید.</p></div>))}
   {item.result.sources.some(s=>s.documentFormat==='pdf')&&!item.result.sources.some(s=>safePdfTables(s.tables).length>0)&&<p className="assistant-note">ساختار جدول این بخش با اطمینان تشخیص داده نشد؛ فقط توضیح متن نمایش داده می‌شود و جدولی حدس زده نشده است.</p>}
   <h3 className="assistant-explanation-title">پاسخ و توضیح</h3><p className="assistant-answer">{item.result.answer}</p><p className="assistant-note">پاسخ مدل تأیید انسانی نشده است؛ نتیجهٔ بررسی کل سازمان یا تمام محتوای فایل نیست.</p>
   <CoverageView value={item.result.coverage}/>
   <details className="assistant-help"><summary>محدودیت‌ها و زمان بررسی</summary><p className="assistant-note">زمان آغاز بررسی منابع: {item.result.asOf}</p><ul className="assistant-note">{item.result.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul></details>
   {item.result.sources.length>0&&<div className="assistant-sources"><h3>منابع پاسخ و جدول</h3>{item.result.sources.map((s,i)=><details key={s.id+':'+i}><summary>{s.id} — {s.title}{s.citedByModel===false?' — منبع جدول، نه ادعای مدل':''}{s.page?` · صفحهٔ ${s.page}`:''}</summary><details className="assistant-technical-source"><summary>متن استخراج‌شده — نمایش فنی اختیاری</summary><p className="assistant-excerpt">{s.excerpt}</p></details><details className="assistant-technical-source"><summary>مشخصات فنی نسخهٔ منبع</summary><small>اثر انگشت نسخه: {s.version}</small></details>{safeAssistantLink(s.href)&&<Link to={s.href}>رفتن به بخش منبع</Link>}</details>)}</div>}
  </Card>)}</div>
 </section>;
}

function CoverageView({value}:{value:unknown}):JSX.Element{
 const c=safeCoverage(value);
 return <section className="assistant-coverage" aria-label="محدودهٔ بررسی پاسخ"><h3>محدودهٔ بررسی پاسخ</h3>{c?<><p>{c.selectionMode==='documents'?`${c.selectedDocumentCount.toLocaleString('fa-IR')} سند انتخاب‌شده؛ پاسخ بر پایهٔ بخش‌های محدود زیر است.`:c.selectionMode==='filtered'?'نمونهٔ محدود از منابع مجاز با فیلتر انتخاب‌شده؛ نه همهٔ سوابق.':'نمونهٔ محدود از منابع مجاز؛ هیچ منبع مشخصی انتخاب نشده بود.'}</p><p>فقط بخش‌های کوتاه زیر برای تولید پاسخ در اختیار مدل قرار گرفت؛ ذکر منبع در این فهرست، به معنی تأیید پاسخ یا بررسی کامل آن نیست.</p>{c.reviewedSources.length?<ul>{c.reviewedSources.map(r=><li key={r.id}>[{r.id}] {r.title}{r.page?` — صفحهٔ ${r.page}`:''} — {r.citedByModel?'مورد استناد مدل':'بررسی‌شده، بدون استناد مدل'}</li>)}</ul>:<p>بخشی برای تولید پاسخ پیدا نشد.</p>}<details className="assistant-help"><summary>حدود خواندن اسناد</summary><p>اسناد متنی حداکثر تا ۳۲هزار نویسه و PDF تا ۱۵ صفحهٔ نخست استخراج می‌شوند؛ از آن‌ها حداکثر سه بخش کوتاه انتخاب می‌شود. OCR انجام نمی‌شود. جدول مستقل از توضیح مدل و فقط از ساختار معتبر PDF بازسازی می‌شود.</p></details></>:<p>جزئیات محدودهٔ بررسی از سرور دریافت نشد. منابع زیر فقط ارجاع‌های پاسخ‌اند؛ بررسی کامل فایل یا کل سازمان تأیید نشده است.</p>}</section>;
}

import {useEffect,useRef,useState,type FormEvent} from 'react';
import {useApiClient} from '../core/api/apiContext';
import {persianNameError,persianUsernameError,persianNameMessage,persianUsernameMessage} from '../shared/persianIdentity';
import {ReviewDialog,type ReviewPreview} from './SuperadminReviewTools';
type Person={id:string;displayName:string;username:string;phone:string;status:string;needsCorrection:('displayName'|'username')[]};
type Rows={items:Person[];total:number;hasMore:boolean;tenantName:string};
type Request={table:'people';purpose:'persianIdentityCorrection';tenantId:string;recordId:string;changes:Record<string,string>;confirmation:string;acknowledgeUsernameChange:boolean};
export function LegacyIdentityCorrection({tenants,onChanged}:{tenants:{id:string;name:string}[];onChanged?:()=>void}){
 const api=useApiClient();const [open,setOpen]=useState(false);const [tenantId,setTenantId]=useState(tenants[0]?.id||'');const [search,setSearch]=useState('');const [applied,setApplied]=useState('');const [offset,setOffset]=useState(0);const [revision,setRevision]=useState(0);
 const [rows,setRows]=useState<Rows|null>(null);const [person,setPerson]=useState<Person|null>(null);const [loading,setLoading]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('');
 const [changeName,setChangeName]=useState(false);const [changeUsername,setChangeUsername]=useState(false);const [name,setName]=useState('');const [username,setUsername]=useState('');const [confirmation,setConfirmation]=useState('');const [ack,setAck]=useState(false);
 const [pending,setPending]=useState<{request:Request;preview:ReviewPreview}|null>(null);const heading=useRef<HTMLHeadingElement>(null);
 const issue=(e:unknown)=>e instanceof Error?e.message:'عملیات انجام نشد؛ وضعیت را تازه و دوباره بررسی کنید.';
 useEffect(()=>{if(!open||!tenantId)return;let live=true;setRows(null);setLoading(true);setError('');const params=new URLSearchParams({table:'people',purpose:'persianIdentityCorrection',tenantId,search:applied,offset:String(offset)});
 void api.get<Rows>('superadmin/panel/database?'+params,{retry:0}).then(result=>{if(live)setRows(result);}).catch(e=>{if(live)setError(issue(e));}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[api,open,tenantId,applied,offset,revision]);
 useEffect(()=>{if(person)heading.current?.focus();},[person]);
 function reset(){setPerson(null);setPending(null);setName('');setUsername('');setConfirmation('');setAck(false);setChangeName(false);setChangeUsername(false);}
 function select(row:Person){reset();setPerson(row);setChangeName(row.needsCorrection.includes('displayName'));setError('');setMessage('');}
 async function preview(event:FormEvent){event.preventDefault();if(!person||busy)return;setError('');setMessage('');const changes:Record<string,string>={};
 if(changeName){const invalid=persianNameError(name.trim());if(invalid){setError(invalid);return;}if(name.trim()!==person.displayName)changes.displayName=name.trim();}
 if(changeUsername){const invalid=persianUsernameError(username.trim());if(invalid){setError(invalid);return;}if(username.trim()!==person.username)changes.username=username.trim();}
 if(!Object.keys(changes).length){setError('یک مشخصه را برای اصلاح انتخاب و مقدار جدید را وارد کنید.');return;}
 if(changes.username&&(!ack||confirmation!==person.username)){setError('نام کاربری فعلی و تحویل شناسهٔ جدید و خروج نشست‌های عادی را تأیید کنید.');return;}
 const request:Request={table:'people',purpose:'persianIdentityCorrection',tenantId,recordId:person.id,changes,confirmation,acknowledgeUsernameChange:ack};
 setBusy(true);try{const proof=await api.post<ReviewPreview>('superadmin/panel/database/preview',{request},{retry:0});setPending({request,preview:proof});}catch(e){setError(issue(e));}finally{setBusy(false);}}
 async function commit(reason:string){if(!pending||busy)return;setBusy(true);setError('');try{const result=await api.post<{record:Person;usernameChanged:boolean;ordinarySessionsRevoked:number}>('superadmin/panel/database/commit',{request:pending.request,token:pending.preview.token,reason,confirm:true},{retry:0});reset();setMessage(result.usernameChanged?`اصلاح روی همان حساب ثبت شد. نام کاربری جدید: ${result.record.username} — شناسهٔ جدید را به شخص تحویل دهید؛ با همان رمز قبلی دوباره وارد شود. ورود مستقل مدیریت تغییر نکرد.`:'نام فارسی روی همان حساب ثبت شد؛ نام کاربری و نشست‌های ورود تغییر نکردند.');setRevision(n=>n+1);onChanged?.();}catch(e){setPending(null);setError(issue(e)+' اگر نتیجهٔ ثبت نامشخص است، قبل از تکرار فهرست و گزارش تغییرات را بررسی کنید.');}finally{setBusy(false);}}
 return <details className="sa-card" open={open} onToggle={e=>{setOpen(e.currentTarget.open);if(!e.currentTarget.open){reset();setError('');setMessage('');}}}>
 <summary onClick={e=>{if(busy||pending)e.preventDefault();}}>فارسی‌سازی حساب‌های قبلی</summary>
 {open&&<><p>فقط افراد نیازمند اصلاح در سازمان انتخاب‌شده نمایش داده می‌شوند؛ نام ناقص یا خارج از قالب جدید هم در این فهرست می‌آید. ترجمهٔ خودکار و تغییر گروهی وجود ندارد؛ معادل فارسی هر شخص را خودتان بررسی کنید.</p>
 <p className="sa-note">حساب جدید ساخته نمی‌شود. شماره، ایمیل، رمز، دسترسی‌ها و سوابق محفوظ‌اند. تغییر نام کاربری ورود عادی، نشست‌های عادی شخص را می‌بندد؛ نام کاربری مستقل مدیریت تغییر نمی‌کند.</p>
 {error&&<p className="sa-error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
 <fieldset disabled={busy||!!pending} style={{border:0,padding:0,minWidth:0}}><div className="sa-filters"><label>سازمان اصلاح مشخصات<select value={tenantId} onChange={e=>{reset();setTenantId(e.target.value);setOffset(0);setMessage('');}}>{tenants.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
 <form onSubmit={e=>{e.preventDefault();reset();setOffset(0);setApplied(search);setRevision(n=>n+1);}}><label>جست‌وجوی حساب‌های نیازمند اصلاح<input autoComplete="off" value={search} maxLength={160} onChange={e=>setSearch(e.target.value)}/></label><button>جست‌وجوی حساب‌های قبلی</button></form></div>
 <button type="button" onClick={()=>{reset();setRevision(n=>n+1);}}>تازه‌سازی فهرست اصلاح</button>
 {loading&&<p role="status">در حال بررسی مشخصات حساب‌های قبلی…</p>}
 {rows&&<><p>{rows.tenantName} — {rows.total.toLocaleString('fa-IR')} حساب نیازمند اصلاح</p><div className="sa-table"><table style={{tableLayout:"fixed",whiteSpace:"normal"}}><thead><tr><th style={{width:"60%"}}>مشخصات فعلی</th><th>بررسی</th></tr></thead><tbody>{rows.items.map(row=><tr key={row.id}><td style={{whiteSpace:"normal",overflowWrap:"anywhere"}}><strong>{row.displayName||'—'}</strong><small dir="auto">{row.username}</small><small>نیازمند اصلاح: {row.needsCorrection.map(k=>k==='displayName'?'نام کامل':'نام کاربری').join('، ')}</small></td><td style={{whiteSpace:"normal"}}><button type="button" style={{whiteSpace:"normal",padding:8,width:"100%"}} aria-label={'اصلاح مشخصات '+row.username} onClick={()=>select(row)}>بررسی و ورود معادل فارسی</button></td></tr>)}</tbody></table></div>{!rows.items.length&&<p>حسابی برای اصلاح در این جست‌وجو پیدا نشد.</p>}
 <button type="button" disabled={offset===0} onClick={()=>{reset();setOffset(n=>Math.max(0,n-50));}}>صفحهٔ قبل اصلاح</button><button type="button" disabled={!rows.hasMore} onClick={()=>{reset();setOffset(n=>n+50);}}>صفحهٔ بعد اصلاح</button></>}
 {person&&<form onSubmit={e=>void preview(e)}><h3 ref={heading} tabIndex={-1}>اصلاح همان حساب — {person.displayName||person.username}</h3><p>شناسه شخص: <span dir="ltr">{person.id}</span></p><p>نام کاربری فعلی: <b dir="auto">{person.username}</b></p>
 <label><input type="checkbox" checked={changeName} onChange={e=>{setChangeName(e.target.checked);setName('');}}/> اصلاح نام و نام خانوادگی</label>
 {changeName&&<label>نام و نام خانوادگی فارسی<input aria-label="نام و نام خانوادگی فارسی" required maxLength={160} lang="fa" dir="rtl" autoComplete="off" value={name} onChange={e=>setName(e.target.value)}/><small>{persianNameMessage}</small></label>}
 <label><input type="checkbox" checked={changeUsername} onChange={e=>{setChangeUsername(e.target.checked);setUsername('');setConfirmation('');setAck(false);}}/> اصلاح نام کاربری ورود عادی</label>
 {changeUsername&&<><label>نام کاربری فارسی جدید<input aria-label="نام کاربری فارسی جدید" required maxLength={64} lang="fa" dir="rtl" autoComplete="off" value={username} onChange={e=>{setUsername(e.target.value);setAck(false);}}/><small>{persianUsernameMessage}</small></label>
 <label>برای تأیید تغییر شناسه، نام کاربری فعلی را بنویسید<input required autoComplete="off" dir="auto" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label>
 <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/> تحویل شناسهٔ جدید به شخص و خروج همهٔ نشست‌های عادی او را تأیید می‌کنم.</label></>}
 <button disabled={!changeName&&!changeUsername}>پیش‌نمایش اصلاح مشخصات — بدون ثبت</button><button type="button" onClick={()=>{reset();setError('');}}>انصراف از اصلاح این شخص</button></form>}
 </fieldset>{pending&&<ReviewDialog key={pending.preview.token} preview={pending.preview} busy={busy} onCancel={()=>setPending(null)} onConfirm={reason=>void commit(reason)}/>}</>}
 </details>;
}

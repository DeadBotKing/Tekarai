import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
vi.mock("../app/configuration/runtimeConfig", () => ({runtimeConfig:{appName:"Tekarai",apiBaseUrl:"http://api.test.invalid",apiVersion:"v1",demoMode:false,realtimeEnabled:false}}));
vi.mock("../features/notifications/notificationService", () => ({createNotificationService:()=>({list:async()=>[],markRead:async()=>{},markAllRead:async()=>{}})}));
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { WorkOrdersPage } from "../pages/WorkOrdersPage";
let failed = true;
const envelope = (data: unknown):Response => new Response(JSON.stringify({success:true,data,meta:{},errors:[]}),{status:200,headers:{"content-type":"application/json"}});
beforeEach(()=>{
 failed=true;
 sessionStore.set({accessToken:"test",refreshToken:"test",user:{id:"admin",displayName:"مدیر",email:"admin@test.local",role:"Admin",permissions:["maintenance.workorder.list","maintenance.workorder.view","maintenance.device.list"]}});
 vi.stubGlobal("fetch",vi.fn(async(input: RequestInfo | URL)=>{
  if(String(input).includes("/maintenance/work-orders") && failed) return new Response(JSON.stringify({success:false,data:null,errors:[{code:"PERMISSION_DENIED",message:"دسترسی مجاز نیست"}]}),{status:403,headers:{"content-type":"application/json"}});
  return envelope([]);
 }));
});
afterEach(()=>{sessionStore.clear();vi.unstubAllGlobals();});
const show=():void=>{render(<AppProviders><MemoryRouter><WorkOrdersPage /></MemoryRouter></AppProviders>);};
describe("work order list error versus empty",()=>{
 it("does not label a failed list request as no registered work orders",async()=>{
  show();
  expect(await screen.findByText(/دریافت فهرست درخواست‌ها ناموفق بود/)).toBeInTheDocument();
  expect(screen.queryByText("هیچ درخواست کاری ثبت نشده است.")).not.toBeInTheDocument();
  expect(screen.getByText(/درخواست را دوباره ثبت نکنید/)).toBeInTheDocument();
 });
 it("retries fetching the list and clears the error after success",async()=>{
  show();await screen.findByText(/دریافت فهرست درخواست‌ها ناموفق بود/);
  failed=false;
  await userEvent.click(screen.getByRole("button",{name:"تلاش دوباره"}));
  expect(await screen.findByText("هیچ درخواست کاری ثبت نشده است.")).toBeInTheDocument();
  expect(screen.queryByText(/دریافت فهرست درخواست‌ها ناموفق بود/)).not.toBeInTheDocument();
 });
});

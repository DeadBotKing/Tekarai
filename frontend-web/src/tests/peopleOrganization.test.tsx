import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
vi.mock("../app/configuration/runtimeConfig", () => ({ runtimeConfig: { appName: "Tekarai", apiBaseUrl: "http://api.test.invalid", apiVersion: "v1", demoMode: false, realtimeEnabled: false } }));
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { PeopleOrganizationPage } from "../pages/PeopleOrganizationPage";
import { navigationConfig } from "../app/configuration/navigation";
const envelope = (data: unknown): Response => new Response(JSON.stringify({success:true,data,errors:[],meta:{}}), {status:200,headers:{"content-type":"application/json"}});
const person = {id:"u2",username:"reza",displayName:"رضا احمدی",email:"reza@example.test",status:"active",createdAt:"2026-10-01"};
const permissions = ["user.list","user.create","organization.department.view","organization.department.manage","organization.position.view","organization.position.manage","organization.assignment.view","organization.assignment.manage","organization.matrix.view","organization.matrix.manage"];
let failAssignment = false;
let writes: {url:string; method:string; body:any}[];
function setup(): void {
 render(<AppProviders><MemoryRouter><PeopleOrganizationPage /></MemoryRouter></AppProviders>);
}
beforeEach(() => {
 writes=[];failAssignment=false;
 sessionStore.set({accessToken:"test",refreshToken:"test",user:{id:"admin",displayName:"مدیر",email:"admin@test.local",role:"Admin",permissions}});
 vi.stubGlobal("fetch",vi.fn(async (input: RequestInfo, init?: RequestInit) => {
  const url=String(input), method=init?.method || "GET";
  if(method!=="GET") writes.push({url,method,body:JSON.parse(String(init?.body || "{}"))});
  if(url.includes("organization/departments")) return envelope({items:[{id:"d1",name:"فنی",status:"active"}]});
  if(url.includes("organization/positions")) return envelope({items:[{id:"p1",name:"تکنسین",isActive:true}]});
  if(url.includes("organization/assignments")) {
   if(method==="POST" && failAssignment) return new Response(JSON.stringify({success:false,errors:[{message:"انتساب ناموفق"}]}),{status:400,headers:{"content-type":"application/json"}});
   return envelope(method==="GET" ? {items:[]} : {id:"a1"});
  }
  if(new URL(url).pathname.endsWith("/users")) return envelope(method==="POST" ? person : [person]);
  return envelope([]);
 }));
});
afterEach(() => {sessionStore.clear();vi.unstubAllGlobals();});
async function fillForm(): Promise<void> {
 const user=userEvent.setup();
 await screen.findByText("رضا احمدی");
 await user.click(screen.getByRole("button",{name:"افزودن فرد"}));
 const modal=within(screen.getByRole("dialog"));
 await user.type(modal.getByLabelText("نام و نام خانوادگی"),"رضا احمدی");
 await user.type(modal.getByLabelText(/نام کاربری/),"reza");
 await user.type(modal.getByLabelText(/ایمیل/),"reza@example.test");
 await user.type(modal.getByLabelText(/رمز عبور/),"SafePassword2026!");
 await user.selectOptions(modal.getByLabelText("واحد سازمانی"),"d1");
 await user.selectOptions(modal.getByLabelText("سمت"),"p1");
}
describe("unified people and organization",() => {
 it("removes the separate organization entry from navigation",() => {
  expect(navigationConfig.flatMap(group=>group.children || []).some(item=>item.id==="organizationStructure")).toBe(false);
 });
 it("creates an account and assigns its unit and title from one form",async () => {
  setup();await fillForm();
  await userEvent.click(screen.getByRole("button",{name:"ثبت فرد و انتساب"}));
  await screen.findByText("فرد و جایگاه سازمانی ثبت شدند.");
  const assignment=writes.find(item=>item.url.includes("organization/assignments"));
  expect(assignment?.body).toMatchObject({userId:"u2",departmentId:"d1",positionId:"p1"});
  expect(writes.filter(item=>item.url.endsWith("/users"))).toHaveLength(1);
 });
 it("retries only assignment after partial failure and preserves the created account",async () => {
  setup();await fillForm();failAssignment=true;
  await userEvent.click(screen.getByRole("button",{name:"ثبت فرد و انتساب"}));
  await screen.findByText(/حساب ساخته شد، اما انتساب تکمیل نشد/);
  failAssignment=false;
  await userEvent.click(screen.getByRole("button",{name:"تکمیل انتساب"}));
  await screen.findByText("فرد و جایگاه سازمانی ثبت شدند.");
  expect(writes.filter(item=>item.url.endsWith("/users"))).toHaveLength(1);
  expect(writes.filter(item=>item.url.includes("organization/assignments"))).toHaveLength(2);
 });
 it("adds an assignment to an existing account without creating another account", async () => {
  setup(); await screen.findByText("رضا احمدی");
  await userEvent.click(screen.getByRole("button",{name:"مدیریت سمت‌ها"}));
  const dialog=within(screen.getByRole("dialog"));
  await userEvent.selectOptions(dialog.getByLabelText("واحد سازمانی"),"d1");
  await userEvent.selectOptions(dialog.getByLabelText("سمت"),"p1");
  await userEvent.click(dialog.getByRole("button",{name:"افزودن انتساب"}));
  await screen.findByText("انتساب فرد ذخیره شد.");
  expect(writes.filter(item=>item.url.endsWith("/users"))).toHaveLength(0);
  expect(writes.find(item=>item.url.includes("organization/assignments"))?.body.userId).toBe("u2");
 });
 it("does not offer assignment or creation actions to a read-only user", async () => {
  sessionStore.set({accessToken:"test",refreshToken:"test",user:{id:"reader",displayName:"خواننده",email:"r@test.local",role:"Member",permissions:["user.list","organization.department.view","organization.position.view","organization.assignment.view"]}});
  setup(); await screen.findByText("رضا احمدی");
  expect(screen.queryByRole("button",{name:"افزودن فرد"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"مدیریت سمت‌ها"})).not.toBeInTheDocument();
 });
 it("opens organization settings without leaving the people page",async () => {
  setup();await screen.findByText("رضا احمدی");
  await userEvent.click(screen.getByRole("button",{name:"تنظیمات سازمان و دسترسی"}));
  expect(await screen.findByRole("tab",{name:"واحدها"})).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab",{name:"سمت‌ها"}));
  expect(screen.queryByText("انتساب کاربران")).not.toBeInTheDocument();
 });
});

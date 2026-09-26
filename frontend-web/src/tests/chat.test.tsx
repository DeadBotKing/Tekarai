import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { apiEndpoints } from "../core/api/endpoints";
import type { ApiClient } from "../core/api/apiClient";
import { createChatService, toConversation, toMessage } from "../features/communication/chatService";
import { createDemoChatService, resetDemoChat } from "../features/communication/chatDemoData";
import { ChatPage } from "../pages/ChatPage";
import { navigationConfig } from "../app/configuration/navigation";
import { translate } from "../core/localization/i18n";

const authenticate = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "user-self",
      displayName: "Test User",
      email: "test@example.test",
      role: "Maintenance",
      permissions: ["dashboard.view"],
    },
  });

const renderChat = (): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/app/chat"]}>
        <Routes>
          <Route path="/app/chat" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("chat service wire mapping", () => {
  it("normalises conversation and message payloads from the communication API", () => {
    const conversation = toConversation({
      id: "c1",
      conversationType: "group",
      name: "تیم تعمیرات",
      lastMessagePreview: "سلام",
      unreadCount: 3,
    });
    expect(conversation.type).toBe("GROUP");
    expect(conversation.unreadCount).toBe(3);
    expect(conversation.description).toBe("");

    const message = toMessage({
      id: "m1",
      conversationId: "c1",
      senderId: "u2",
      body: "پمپ سرویس شد",
      deletedAt: "2026-09-20T08:00:00Z",
      reactions: [{ userId: "u3", reaction: "👍" }],
    });
    expect(message.deleted).toBe(true);
    expect(message.reactions).toEqual([{ userId: "u3", reaction: "👍" }]);
    expect(message.messageType).toBe("TEXT");
  });

  it("calls the documented communication endpoints", async () => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    const stub = {
      get: vi.fn(async (path: string) => {
        calls.push({ method: "GET", path });
        return [];
      }),
      post: vi.fn(async (path: string, body?: unknown) => {
        calls.push({ method: "POST", path, body });
        return { id: "m9" };
      }),
      patch: vi.fn(async (path: string, body?: unknown) => {
        calls.push({ method: "PATCH", path, body });
        return { id: "m9" };
      }),
      delete: vi.fn(async (path: string) => {
        calls.push({ method: "DELETE", path });
        return null;
      }),
    } as unknown as ApiClient;

    const service = createChatService(stub);
    await service.listConversations();
    await service.listMessages("c1");
    await service.sendMessage("c1", { body: "سلام", replyToId: "m1" });
    await service.editMessage("m1", "متن اصلاح‌شده");
    await service.react("m1", "👍");
    await service.markRead("c1", "m1");
    await service.deleteMessage("m1");
    await service.listParticipants("c1");
    await service.addParticipant("c1", "u2");
    await service.removeParticipant("c1", "u2");
    await service.archiveConversation("c1");

    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([
      `GET ${apiEndpoints.communication.conversations}`,
      `GET ${apiEndpoints.communication.conversationMessages("c1")}?limit=50`,
      `POST ${apiEndpoints.communication.conversationMessages("c1")}`,
      `PATCH ${apiEndpoints.communication.message("m1")}`,
      `POST ${apiEndpoints.communication.messageReactions("m1")}`,
      `POST ${apiEndpoints.communication.conversationRead("c1")}`,
      `DELETE ${apiEndpoints.communication.message("m1")}`,
      `GET ${apiEndpoints.communication.conversationParticipants("c1")}`,
      `POST ${apiEndpoints.communication.conversationParticipants("c1")}`,
      `DELETE ${apiEndpoints.communication.conversationParticipant("c1", "u2")}`,
      `POST ${apiEndpoints.communication.conversationArchive("c1")}`,
    ]);
    expect(calls[2].body).toMatchObject({ body: "سلام", messageType: "TEXT", replyToId: "m1" });
    expect(calls[5].body).toEqual({ uptoMessageId: "m1" });
  });
});

describe("offline chat store", () => {
  it("keeps sent, edited, deleted and reacted messages like a real thread", async () => {
    resetDemoChat();
    const service = createDemoChatService();

    const sent = await service.sendMessage("conv-1", { body: "کمپرسور راه‌اندازی شد" });
    expect((await service.listMessages("conv-1")).some((item) => item.id === sent.id)).toBe(true);

    const edited = await service.editMessage(sent.id, "کمپرسور راه‌اندازی و تست شد");
    expect(edited.body).toBe("کمپرسور راه‌اندازی و تست شد");
    expect(edited.editedAt).not.toBe("");

    await service.react(sent.id, "👍");
    const reacted = (await service.listMessages("conv-1")).find((item) => item.id === sent.id);
    expect(reacted?.reactions).toHaveLength(1);
    await service.removeReaction(sent.id, "👍");
    const cleared = (await service.listMessages("conv-1")).find((item) => item.id === sent.id);
    expect(cleared?.reactions).toHaveLength(0);

    await service.deleteMessage(sent.id);
    const removed = (await service.listMessages("conv-1")).find((item) => item.id === sent.id);
    expect(removed?.deleted).toBe(true);

    const found = await service.searchMessages("کمپرسور");
    expect(found.length).toBeGreaterThan(0);
  });

  it("creates direct, group and channel conversations with their members", async () => {
    resetDemoChat();
    const service = createDemoChatService();

    const direct = await service.createConversation({ kind: "direct", peerUserId: "user-3" });
    expect(direct.type).toBe("DIRECT");
    expect((await service.listParticipants(direct.id)).map((item) => item.userId)).toContain("user-3");

    const group = await service.createConversation({
      kind: "group",
      name: "کارگروه هیدرولیک",
      memberIds: ["user-2", "user-4"],
    });
    expect(group.type).toBe("GROUP");
    expect(await service.listParticipants(group.id)).toHaveLength(3);

    const channel = await service.createConversation({
      kind: "channel",
      name: "اعلان‌های ایمنی",
      code: "safety-alerts",
      visibility: "PUBLIC",
    });
    expect(channel.type).toBe("CHANNEL");

    await service.archiveConversation(channel.id);
    const open = await service.listConversations();
    expect(open.some((item) => item.id === channel.id)).toBe(false);
    const all = await service.listConversations(true);
    expect(all.some((item) => item.id === channel.id)).toBe(true);
  });
});

describe("chat page", () => {
  it("shows the conversation list and opens a thread", async () => {
    resetDemoChat();
    authenticate();
    renderChat();

    expect((await screen.findAllByText("تیم تعمیرات خط ۲")).length).toBeGreaterThan(0);
    expect(screen.getByText("اعلان‌های نگهداری پیشگیرانه")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("قطعهٔ یدکی از انبار تحویل گرفته شد.")).toBeInTheDocument(),
    );
    expect(
      screen.getByText("صبح بخیر. وضعیت کمپرسور واحد ۳ بعد از سرویس دیشب چطور است؟"),
    ).toBeInTheDocument();
  });

  it("sends a message from the composer into the thread", async () => {
    resetDemoChat();
    authenticate();
    renderChat();

    const composer = await screen.findByLabelText("پیام خود را بنویسید…");
    fireEvent.change(composer, { target: { value: "گزارش امروز ارسال شد" } });
    fireEvent.click(screen.getByRole("button", { name: /ارسال/ }));

    await waitFor(() =>
      expect(screen.getAllByText("گزارش امروز ارسال شد").length).toBeGreaterThan(0),
    );
  });

  it("opens the new-conversation dialog with direct, group and channel options", async () => {
    resetDemoChat();
    authenticate();
    renderChat();

    fireEvent.click((await screen.findAllByRole("button", { name: /گفت‌وگوی جدید/ }))[0]);
    const kind = await screen.findByLabelText("نوع گفت‌وگو");
    ["دونفره", "گروه", "کانال"].forEach((label) => {
      expect(within(kind as HTMLSelectElement).getByText(label)).toBeInTheDocument();
    });

    fireEvent.change(kind, { target: { value: "channel" } });
    expect(await screen.findByLabelText(/شناسه کانال/)).toBeInTheDocument();
    expect(screen.getByLabelText("سطح دسترسی")).toBeInTheDocument();
  });

  it("registers the chat route in the navigation with Persian labels", () => {
    const group = navigationConfig.find((item) => item.id === "communication");
    expect(group?.children?.[0].route).toBe("/app/chat");
    expect(translate("fa", "nav.chat")).toBe("گفت‌وگو");
    expect(translate("fa", "chat.title")).toBe("گفت‌وگوی سازمانی");
  });
});

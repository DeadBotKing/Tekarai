import type {
  ChatDirectoryUser,
  ChatMessage,
  Conversation,
  ConversationParticipant,
  CreateConversationInput,
  ParticipantRole,
} from "../../shared/types/domain";
import type { ChatService } from "./chatService";

/**
 * Offline chat fixtures. Demo mode keeps the whole thread in memory and mirrors
 * it into localStorage, so a page reload does not lose what the user typed.
 */

const STORAGE_KEY = "tekarai.demo.chat.v1";
/** Demo mode signs in as this identity; messages from it render as "me". */
export const DEMO_SELF_ID = "user-self";

export const demoDirectory: ChatDirectoryUser[] = [
  { id: "user-self", displayName: "مهندس میترا رادمنش", email: "mitra@tekarai.local" },
  { id: "user-2", displayName: "علی صادقی — سرپرست مکانیک", email: "sadeghi@tekarai.local" },
  { id: "user-3", displayName: "سمیرا کاظمی — برق و ابزار دقیق", email: "kazemi@tekarai.local" },
  { id: "user-4", displayName: "رضا موحد — تأسیسات", email: "movahed@tekarai.local" },
  { id: "user-5", displayName: "نگار حسینی — انبار قطعات", email: "hosseini@tekarai.local" },
  { id: "user-6", displayName: "کاوه امیری — بهره‌بردار خط ۲", email: "amiri@tekarai.local" },
];

const nameOf = (userId: string): string =>
  demoDirectory.find((user) => user.id === userId)?.displayName ?? userId;

interface ChatStore {
  conversations: Conversation[];
  participants: ConversationParticipant[];
  messages: ChatMessage[];
  sequence: number;
}

const iso = (minutesAgo: number): string =>
  new Date(Date.parse("2026-09-26T09:00:00Z") - minutesAgo * 60_000).toISOString();

const seedStore = (): ChatStore => {
  const conversations: Conversation[] = [
    {
      id: "conv-1",
      type: "GROUP",
      name: "تیم تعمیرات خط ۲",
      description: "هماهنگی روزانهٔ نگهداری خط تولید ۲",
      topic: "",
      visibility: "",
      isActive: true,
      archivedAt: "",
      createdAt: iso(4320),
      lastMessageAt: iso(12),
      lastMessagePreview: "قطعهٔ یدکی از انبار تحویل گرفته شد.",
      unreadCount: 2,
    },
    {
      id: "conv-2",
      type: "DIRECT",
      name: "علی صادقی — سرپرست مکانیک",
      description: "",
      topic: "",
      visibility: "",
      isActive: true,
      archivedAt: "",
      createdAt: iso(2880),
      lastMessageAt: iso(95),
      lastMessagePreview: "گزارش لرزش پمپ P-101 را فرستادم.",
      unreadCount: 0,
    },
    {
      id: "conv-3",
      type: "CHANNEL",
      name: "اعلان‌های نگهداری پیشگیرانه",
      description: "کانال عمومی اطلاع‌رسانی PM",
      topic: "PM هفتگی",
      visibility: "PUBLIC",
      isActive: true,
      archivedAt: "",
      createdAt: iso(10080),
      lastMessageAt: iso(240),
      lastMessagePreview: "چک‌لیست PM هیدرولیک این هفته منتشر شد.",
      unreadCount: 1,
    },
  ];

  const participantRows: [string, string, ParticipantRole][] = [
    ["conv-1", "user-self", "OWNER"],
    ["conv-1", "user-2", "ADMIN"],
    ["conv-1", "user-3", "MEMBER"],
    ["conv-1", "user-5", "MEMBER"],
    ["conv-2", "user-self", "MEMBER"],
    ["conv-2", "user-2", "MEMBER"],
    ["conv-3", "user-self", "MEMBER"],
    ["conv-3", "user-4", "OWNER"],
    ["conv-3", "user-6", "MEMBER"],
  ];

  const participants: ConversationParticipant[] = participantRows.map(
    ([conversationId, userId, role], index) => ({
      id: `part-${index + 1}`,
      conversationId,
      userId,
      displayName: nameOf(userId),
      role,
      joinedAt: iso(4320),
      leftAt: "",
      isMuted: false,
      isActive: true,
    }),
  );

  const rows: [string, string, string, number, string][] = [
    ["conv-1", "user-2", "صبح بخیر. وضعیت کمپرسور واحد ۳ بعد از سرویس دیشب چطور است؟", 180, ""],
    ["conv-1", "user-self", "فشار خروجی پایدار شده؛ صدای غیرعادی هم برطرف شد.", 172, ""],
    ["conv-1", "user-3", "سنسور دمای خروجی را هم کالیبره کردم، خطای قبلی تکرار نشد.", 150, "msg-2"],
    ["conv-1", "user-5", "قطعهٔ یدکی از انبار تحویل گرفته شد.", 12, ""],
    ["conv-2", "user-2", "گزارش لرزش پمپ P-101 را فرستادم.", 95, ""],
    ["conv-3", "user-4", "چک‌لیست PM هیدرولیک این هفته منتشر شد.", 240, ""],
  ];

  const messages: ChatMessage[] = rows.map(([conversationId, senderId, body, minutes, replyTo], index) => ({
    id: `msg-${index + 1}`,
    conversationId,
    senderId,
    senderName: nameOf(senderId),
    messageType: "TEXT",
    body,
    createdAt: iso(minutes),
    replyToId: replyTo,
    editedAt: "",
    deleted: false,
    reactions: index === 1 ? [{ reaction: "👍", userId: "user-2" }] : [],
  }));

  return { conversations, participants, messages, sequence: messages.length };
};

const load = (): ChatStore => {
  if (typeof window === "undefined") return seedStore();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return seedStore();
    const parsed = JSON.parse(raw) as ChatStore;
    if (!Array.isArray(parsed.conversations) || !Array.isArray(parsed.messages)) return seedStore();
    return parsed;
  } catch {
    return seedStore();
  }
};

let store: ChatStore = load();

const persist = (): void => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* storage disabled — memory copy still works for this session */
  }
};

/** Test/helper hook: drop persisted demo chat state and reseed. */
export const resetDemoChat = (): void => {
  store = seedStore();
  persist();
};

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const nextId = (prefix: string): string => {
  store.sequence += 1;
  return `${prefix}-${store.sequence}`;
};

const touchConversation = (conversationId: string, preview: string): void => {
  store.conversations = store.conversations.map((item) =>
    item.id === conversationId
      ? { ...item, lastMessageAt: new Date().toISOString(), lastMessagePreview: preview }
      : item,
  );
};

/** An in-memory {@link ChatService} used when demo mode is active. */
export const createDemoChatService = (): ChatService => ({
  listConversations: async (includeArchived = false) =>
    clone(
      store.conversations
        .filter((item) => includeArchived || !item.archivedAt)
        .sort((left, right) => right.lastMessageAt.localeCompare(left.lastMessageAt)),
    ),
  createConversation: async (input: CreateConversationInput) => {
    const peerName = input.peerUserId ? nameOf(input.peerUserId) : "";
    const created: Conversation = {
      id: nextId("conv"),
      type: input.kind === "direct" ? "DIRECT" : input.kind === "channel" ? "CHANNEL" : "GROUP",
      name: input.kind === "direct" ? peerName : (input.name ?? ""),
      description: input.description ?? "",
      topic: input.topic ?? "",
      visibility: input.visibility ?? "",
      isActive: true,
      archivedAt: "",
      createdAt: new Date().toISOString(),
      lastMessageAt: new Date().toISOString(),
      lastMessagePreview: "",
      unreadCount: 0,
    };
    store.conversations = [created, ...store.conversations];
    const members = [DEMO_SELF_ID, ...(input.peerUserId ? [input.peerUserId] : []), ...(input.memberIds ?? [])];
    store.participants = [
      ...store.participants,
      ...Array.from(new Set(members)).map((userId, index) => ({
        id: nextId("part"),
        conversationId: created.id,
        userId,
        displayName: nameOf(userId),
        role: (index === 0 ? "OWNER" : "MEMBER") as ParticipantRole,
        joinedAt: created.createdAt,
        leftAt: "",
        isMuted: false,
        isActive: true,
      })),
    ];
    persist();
    return clone(created);
  },
  archiveConversation: async (conversationId) => {
    store.conversations = store.conversations.map((item) =>
      item.id === conversationId ? { ...item, archivedAt: new Date().toISOString() } : item,
    );
    persist();
  },
  listParticipants: async (conversationId) =>
    clone(store.participants.filter((item) => item.conversationId === conversationId)),
  addParticipant: async (conversationId, userId, role = "MEMBER") => {
    const created: ConversationParticipant = {
      id: nextId("part"),
      conversationId,
      userId,
      displayName: nameOf(userId),
      role,
      joinedAt: new Date().toISOString(),
      leftAt: "",
      isMuted: false,
      isActive: true,
    };
    store.participants = [...store.participants, created];
    persist();
    return clone(created);
  },
  removeParticipant: async (conversationId, userId) => {
    store.participants = store.participants.filter(
      (item) => !(item.conversationId === conversationId && item.userId === userId),
    );
    persist();
  },
  listMessages: async (conversationId) =>
    clone(
      store.messages
        .filter((item) => item.conversationId === conversationId)
        .sort((left, right) => left.createdAt.localeCompare(right.createdAt)),
    ),
  sendMessage: async (conversationId, input) => {
    const created: ChatMessage = {
      id: nextId("msg"),
      conversationId,
      senderId: DEMO_SELF_ID,
      senderName: nameOf(DEMO_SELF_ID),
      messageType: "TEXT",
      body: input.body,
      createdAt: new Date().toISOString(),
      replyToId: input.replyToId ?? "",
      editedAt: "",
      deleted: false,
      reactions: [],
    };
    store.messages = [...store.messages, created];
    touchConversation(conversationId, input.body);
    persist();
    return clone(created);
  },
  editMessage: async (messageId, body) => {
    store.messages = store.messages.map((item) =>
      item.id === messageId ? { ...item, body, editedAt: new Date().toISOString() } : item,
    );
    persist();
    return clone(store.messages.find((item) => item.id === messageId) as ChatMessage);
  },
  deleteMessage: async (messageId) => {
    store.messages = store.messages.map((item) =>
      item.id === messageId ? { ...item, deleted: true, body: "" } : item,
    );
    persist();
  },
  react: async (messageId, reaction) => {
    store.messages = store.messages.map((item) =>
      item.id === messageId
        ? {
            ...item,
            reactions: item.reactions.some(
              (entry) => entry.userId === DEMO_SELF_ID && entry.reaction === reaction,
            )
              ? item.reactions
              : [...item.reactions, { reaction, userId: DEMO_SELF_ID }],
          }
        : item,
    );
    persist();
  },
  removeReaction: async (messageId, reaction) => {
    store.messages = store.messages.map((item) =>
      item.id === messageId
        ? {
            ...item,
            reactions: item.reactions.filter(
              (entry) => !(entry.userId === DEMO_SELF_ID && entry.reaction === reaction),
            ),
          }
        : item,
    );
    persist();
  },
  markRead: async (conversationId) => {
    store.conversations = store.conversations.map((item) =>
      item.id === conversationId ? { ...item, unreadCount: 0 } : item,
    );
    persist();
  },
  searchMessages: async (term) => {
    const needle = term.trim().toLowerCase();
    if (!needle) return [];
    return clone(
      store.messages.filter((item) => !item.deleted && item.body.toLowerCase().includes(needle)),
    );
  },
  listDirectory: async (search = "") => {
    const needle = search.trim().toLowerCase();
    return clone(
      demoDirectory.filter(
        (user) =>
          user.id !== DEMO_SELF_ID &&
          (!needle || `${user.displayName} ${user.email}`.toLowerCase().includes(needle)),
      ),
    );
  },
});

import type { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  ChatDirectoryUser,
  ChatMessage,
  Conversation,
  ConversationParticipant,
  ConversationType,
  CreateConversationInput,
  MessageReaction,
  ParticipantRole,
  SendMessageInput,
} from "../../shared/types/domain";

/** Wire shapes — exactly what `/api/v1/communication/**` returns. */
interface ConversationWire {
  id: string;
  type?: string;
  conversationType?: string;
  name?: string;
  description?: string;
  topic?: string;
  visibility?: string;
  isActive?: boolean;
  archivedAt?: string;
  createdAt?: string;
  lastMessageAt?: string;
  lastMessagePreview?: string;
  unreadCount?: number;
}

interface ParticipantWire {
  id: string;
  conversationId?: string;
  userId?: string;
  displayName?: string;
  role?: string;
  joinedAt?: string;
  leftAt?: string;
  isMuted?: boolean;
  isActive?: boolean;
}

interface MessageWire {
  id: string;
  conversationId?: string;
  senderId?: string;
  senderName?: string;
  messageType?: string;
  body?: string;
  createdAt?: string;
  replyToId?: string;
  editedAt?: string;
  deletedAt?: string;
  deleted?: boolean;
  reactions?: { userId?: string; reaction?: string }[];
}

interface UserWire {
  id: string;
  displayName?: string;
  username?: string;
  email?: string;
}

export const toConversation = (wire: ConversationWire): Conversation => ({
  id: wire.id,
  type: ((wire.type ?? wire.conversationType ?? "DIRECT").toUpperCase() as ConversationType),
  name: wire.name ?? "",
  description: wire.description ?? "",
  topic: wire.topic ?? "",
  visibility: wire.visibility ?? "",
  isActive: wire.isActive ?? true,
  archivedAt: wire.archivedAt ?? "",
  createdAt: wire.createdAt ?? "",
  lastMessageAt: wire.lastMessageAt ?? "",
  lastMessagePreview: wire.lastMessagePreview ?? "",
  unreadCount: wire.unreadCount ?? 0,
});

export const toParticipant = (wire: ParticipantWire): ConversationParticipant => ({
  id: wire.id,
  conversationId: wire.conversationId ?? "",
  userId: wire.userId ?? "",
  displayName: wire.displayName ?? "",
  role: ((wire.role ?? "MEMBER").toUpperCase() as ParticipantRole),
  joinedAt: wire.joinedAt ?? "",
  leftAt: wire.leftAt ?? "",
  isMuted: wire.isMuted ?? false,
  isActive: wire.isActive ?? true,
});

export const toMessage = (wire: MessageWire): ChatMessage => ({
  id: wire.id,
  conversationId: wire.conversationId ?? "",
  senderId: wire.senderId ?? "",
  senderName: wire.senderName ?? "",
  messageType: wire.messageType ?? "TEXT",
  body: wire.body ?? "",
  createdAt: wire.createdAt ?? "",
  replyToId: wire.replyToId ?? "",
  editedAt: wire.editedAt ?? "",
  deleted: wire.deleted ?? Boolean(wire.deletedAt),
  reactions: (wire.reactions ?? []).map(
    (item): MessageReaction => ({
      reaction: item.reaction ?? "",
      userId: item.userId ?? "",
    }),
  ),
});

export interface ChatService {
  listConversations(includeArchived?: boolean): Promise<Conversation[]>;
  createConversation(input: CreateConversationInput): Promise<Conversation>;
  archiveConversation(conversationId: string): Promise<void>;
  listParticipants(conversationId: string): Promise<ConversationParticipant[]>;
  addParticipant(
    conversationId: string,
    userId: string,
    role?: ParticipantRole,
  ): Promise<ConversationParticipant>;
  removeParticipant(conversationId: string, userId: string): Promise<void>;
  listMessages(conversationId: string, beforeId?: string): Promise<ChatMessage[]>;
  sendMessage(conversationId: string, input: SendMessageInput): Promise<ChatMessage>;
  editMessage(messageId: string, body: string): Promise<ChatMessage>;
  deleteMessage(messageId: string): Promise<void>;
  react(messageId: string, reaction: string): Promise<void>;
  removeReaction(messageId: string, reaction: string): Promise<void>;
  markRead(conversationId: string, uptoMessageId: string): Promise<void>;
  searchMessages(term: string): Promise<ChatMessage[]>;
  listDirectory(search?: string): Promise<ChatDirectoryUser[]>;
}

/** Live implementation — talks to the Phase 8/10/14 communication API. */
export function createChatService(api: ApiClient): ChatService {
  const endpoints = apiEndpoints.communication;
  return {
    async listConversations(includeArchived = false) {
      const query = includeArchived ? "?includeArchived=true" : "";
      const rows = await api.get<ConversationWire[]>(`${endpoints.conversations}${query}`);
      return (rows ?? []).map(toConversation);
    },
    async createConversation(input) {
      const wire = await api.post<ConversationWire>(endpoints.conversations, {
        kind: input.kind,
        ...(input.peerUserId ? { peerUserId: input.peerUserId } : {}),
        ...(input.name ? { name: input.name } : {}),
        ...(input.description ? { description: input.description } : {}),
        ...(input.memberIds ? { memberIds: input.memberIds } : {}),
        ...(input.code ? { code: input.code } : {}),
        ...(input.topic ? { topic: input.topic } : {}),
        ...(input.visibility ? { visibility: input.visibility } : {}),
      });
      return toConversation(wire);
    },
    async archiveConversation(conversationId) {
      await api.post(endpoints.conversationArchive(conversationId), {});
    },
    async listParticipants(conversationId) {
      const rows = await api.get<ParticipantWire[]>(
        endpoints.conversationParticipants(conversationId),
      );
      return (rows ?? []).map(toParticipant);
    },
    async addParticipant(conversationId, userId, role = "MEMBER") {
      const wire = await api.post<ParticipantWire>(
        endpoints.conversationParticipants(conversationId),
        { userId, role },
      );
      return toParticipant(wire);
    },
    async removeParticipant(conversationId, userId) {
      await api.delete(endpoints.conversationParticipant(conversationId, userId));
    },
    async listMessages(conversationId, beforeId = "") {
      const query = beforeId ? `?beforeId=${encodeURIComponent(beforeId)}&limit=50` : "?limit=50";
      const rows = await api.get<MessageWire[]>(
        `${endpoints.conversationMessages(conversationId)}${query}`,
      );
      return (rows ?? []).map(toMessage);
    },
    async sendMessage(conversationId, input) {
      const wire = await api.post<MessageWire>(endpoints.conversationMessages(conversationId), {
        body: input.body,
        messageType: "TEXT",
        ...(input.replyToId ? { replyToId: input.replyToId } : {}),
        ...(input.clientRequestId ? { clientRequestId: input.clientRequestId } : {}),
      });
      return toMessage(wire);
    },
    async editMessage(messageId, body) {
      const wire = await api.patch<MessageWire>(endpoints.message(messageId), { body });
      return toMessage(wire);
    },
    async deleteMessage(messageId) {
      await api.delete(endpoints.message(messageId));
    },
    async react(messageId, reaction) {
      await api.post(endpoints.messageReactions(messageId), { reaction });
    },
    async removeReaction(messageId, reaction) {
      await api.delete(`${endpoints.messageReactions(messageId)}?reaction=${encodeURIComponent(reaction)}`);
    },
    async markRead(conversationId, uptoMessageId) {
      await api.post(endpoints.conversationRead(conversationId), { uptoMessageId });
    },
    async searchMessages(term) {
      const rows = await api.get<MessageWire[]>(
        `${endpoints.messageSearch}?q=${encodeURIComponent(term)}`,
      );
      return (rows ?? []).map(toMessage);
    },
    async listDirectory(search = "") {
      const query = search ? `?search=${encodeURIComponent(search)}&pageSize=50` : "?pageSize=50";
      const rows = await api.get<UserWire[]>(`${apiEndpoints.users}${query}`);
      return (rows ?? []).map((row) => ({
        id: row.id,
        displayName: row.displayName || row.username || row.email || row.id,
        email: row.email ?? "",
      }));
    },
  };
}

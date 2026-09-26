import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { useAuth } from "../core/auth/authContext";
import { useLocalization } from "../core/localization/localizationContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createChatService } from "../features/communication/chatService";
import { createDemoChatService, DEMO_SELF_ID } from "../features/communication/chatDemoData";
import { useChatRealtime } from "../features/communication/useChatRealtime";
import {
  CONVERSATION_TYPES,
  PARTICIPANT_ROLES,
  QUICK_REACTIONS,
  type ChatDirectoryUser,
  type ChatMessage,
  type ChannelVisibility,
  type Conversation,
  type ConversationParticipant,
  type ConversationType,
} from "../shared/types/domain";
import { Modal, Toast, ConfirmDialog } from "../shared/components/overlays";
import {
  Avatar,
  Badge,
  Button,
  Card,
  EmptyState,
  IconButton,
  LoadingState,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

type NewKind = "direct" | "group" | "channel";

const CHANNEL_CODE_PATTERN = /^[a-z0-9_-]{2,64}$/;

const timeLabel = (iso: string): string => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("fa-IR", { hour: "2-digit", minute: "2-digit" }).format(date);
};

const dayLabel = (iso: string): string => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("fa-IR", { year: "numeric", month: "long", day: "numeric" }).format(date);
};

const conversationIcon = (type: ConversationType): "users" | "hash" | "user" =>
  type === "GROUP" ? "users" : type === "CHANNEL" ? "hash" : "user";

/** Group reactions by emoji so each one renders as a single counted chip. */
const groupReactions = (message: ChatMessage): { reaction: string; count: number; mine: boolean; userIds: string[] }[] => {
  const map = new Map<string, string[]>();
  message.reactions.forEach((entry) => {
    map.set(entry.reaction, [...(map.get(entry.reaction) ?? []), entry.userId]);
  });
  return Array.from(map.entries()).map(([reaction, userIds]) => ({
    reaction,
    count: userIds.length,
    mine: false,
    userIds,
  }));
};

/** Internal messenger: conversation list, message thread, members and composer. */
export function ChatPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const { session } = useAuth();
  const chat = useMemo(
    () => (runtimeConfig.demoMode ? createDemoChatService() : createChatService(api)),
    [api],
  );
  const selfId = runtimeConfig.demoMode ? DEMO_SELF_ID : (session?.user.id ?? "");

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [participants, setParticipants] = useState<ConversationParticipant[]>([]);
  const [directory, setDirectory] = useState<ChatDirectoryUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [toastTone, setToastTone] = useState<"success" | "error">("success");
  const [filter, setFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);

  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [editing, setEditing] = useState<ChatMessage | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ChatMessage | null>(null);
  const [reactionFor, setReactionFor] = useState("");

  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ChatMessage[] | null>(null);

  const [newOpen, setNewOpen] = useState(false);
  const [newKind, setNewKind] = useState<NewKind>("direct");
  const [newPeer, setNewPeer] = useState("");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [newVisibility, setNewVisibility] = useState<ChannelVisibility>("PRIVATE");
  const [newMembers, setNewMembers] = useState<string[]>([]);
  const [newError, setNewError] = useState("");
  const [saving, setSaving] = useState(false);

  const [addMemberId, setAddMemberId] = useState("");
  const [pendingRemove, setPendingRemove] = useState<ConversationParticipant | null>(null);
  const [pendingArchive, setPendingArchive] = useState(false);

  const threadRef = useRef<HTMLDivElement | null>(null);
  const typingTimer = useRef<number | null>(null);

  const notify = useCallback((message: string, tone: "success" | "error" = "success") => {
    setToastTone(tone);
    setToast(message);
  }, []);

  const loadConversations = useCallback(
    async (preserveId = "") => {
      setLoading(true);
      try {
        const rows = await chat.listConversations(showArchived);
        setConversations(rows);
        setActiveId((current) => {
          const wanted = preserveId || current;
          if (wanted && rows.some((row) => row.id === wanted)) return wanted;
          return rows[0]?.id ?? "";
        });
      } catch {
        notify(t("chat.error.loadFailed"), "error");
      } finally {
        setLoading(false);
      }
    },
    [chat, notify, showArchived, t],
  );

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    void chat
      .listDirectory()
      .then(setDirectory)
      .catch(() => setDirectory([]));
  }, [chat]);

  const loadThread = useCallback(
    async (conversationId: string) => {
      if (!conversationId) {
        setMessages([]);
        setParticipants([]);
        return;
      }
      setThreadLoading(true);
      try {
        const [thread, members] = await Promise.all([
          chat.listMessages(conversationId),
          chat.listParticipants(conversationId).catch(() => [] as ConversationParticipant[]),
        ]);
        setMessages(thread);
        setParticipants(members);
        const last = thread[thread.length - 1];
        if (last) {
          await chat.markRead(conversationId, last.id).catch(() => undefined);
          setConversations((current) =>
            current.map((item) => (item.id === conversationId ? { ...item, unreadCount: 0 } : item)),
          );
        }
      } catch {
        notify(t("chat.error.loadFailed"), "error");
      } finally {
        setThreadLoading(false);
      }
    },
    [chat, notify, t],
  );

  useEffect(() => {
    void loadThread(activeId);
  }, [activeId, loadThread]);

  useEffect(() => {
    const node = threadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages]);

  /** Live gateway events keep the open thread and the sidebar in sync. */
  const handleRealtime = useCallback(
    (event: { type: string; conversationId?: string; payload?: Record<string, unknown> }) => {
      if (!event.type.startsWith("message.")) return;
      if (!event.conversationId || event.conversationId === activeId) {
        void loadThread(activeId);
        return;
      }
      // A thread we are not looking at moved — bump its unread badge and preview.
      const preview = String(event.payload?.body ?? "");
      setConversations((current) =>
        current.map((item) =>
          item.id === event.conversationId
            ? {
                ...item,
                unreadCount: item.unreadCount + (event.type === "message.created" ? 1 : 0),
                lastMessageAt: new Date().toISOString(),
                lastMessagePreview: preview || item.lastMessagePreview,
              }
            : item,
        ),
      );
    },
    [activeId, loadThread],
  );

  const realtime = useChatRealtime({
    enabled: Boolean(activeId),
    conversationId: activeId,
    onEvent: handleRealtime,
  });

  const active = conversations.find((item) => item.id === activeId) ?? null;

  const visibleConversations = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter((item) =>
      `${item.name} ${item.description} ${item.lastMessagePreview}`.toLowerCase().includes(needle),
    );
  }, [conversations, filter]);

  const nameFor = useCallback(
    (userId: string): string => {
      if (userId === selfId) return session?.user.displayName ?? "";
      return (
        participants.find((item) => item.userId === userId)?.displayName ||
        directory.find((item) => item.id === userId)?.displayName ||
        userId
      );
    },
    [directory, participants, selfId, session?.user.displayName],
  );

  const handleSend = async (): Promise<void> => {
    const body = draft.trim();
    if (!body || !activeId) return;
    const clientRequestId = `c-${Date.now()}`;
    const optimistic: ChatMessage = {
      id: clientRequestId,
      conversationId: activeId,
      senderId: selfId,
      senderName: session?.user.displayName ?? "",
      messageType: "TEXT",
      body,
      createdAt: new Date().toISOString(),
      replyToId: replyTo?.id ?? "",
      editedAt: "",
      deleted: false,
      pending: true,
      reactions: [],
    };
    setMessages((current) => [...current, optimistic]);
    setDraft("");
    setReplyTo(null);
    try {
      const saved = await chat.sendMessage(activeId, {
        body,
        replyToId: replyTo?.id,
        clientRequestId,
      });
      setMessages((current) => current.map((item) => (item.id === clientRequestId ? saved : item)));
      setConversations((current) =>
        current.map((item) =>
          item.id === activeId
            ? { ...item, lastMessagePreview: body, lastMessageAt: saved.createdAt }
            : item,
        ),
      );
    } catch {
      setMessages((current) =>
        current.map((item) =>
          item.id === clientRequestId ? { ...item, pending: false, failed: true } : item,
        ),
      );
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleDraftChange = (value: string): void => {
    setDraft(value);
    realtime.sendTyping(true);
    if (typingTimer.current) window.clearTimeout(typingTimer.current);
    typingTimer.current = window.setTimeout(() => realtime.sendTyping(false), 2000);
  };

  const handleEditSave = async (): Promise<void> => {
    if (!editing) return;
    const body = editDraft.trim();
    if (!body) return;
    try {
      const updated = await chat.editMessage(editing.id, body);
      setMessages((current) => current.map((item) => (item.id === editing.id ? updated : item)));
      setEditing(null);
      setEditDraft("");
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      await chat.deleteMessage(target.id);
      setMessages((current) =>
        current.map((item) => (item.id === target.id ? { ...item, deleted: true, body: "" } : item)),
      );
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleReaction = async (message: ChatMessage, reaction: string): Promise<void> => {
    setReactionFor("");
    const mine = message.reactions.some(
      (entry) => entry.userId === selfId && entry.reaction === reaction,
    );
    try {
      if (mine) {
        await chat.removeReaction(message.id, reaction);
        setMessages((current) =>
          current.map((item) =>
            item.id === message.id
              ? {
                  ...item,
                  reactions: item.reactions.filter(
                    (entry) => !(entry.userId === selfId && entry.reaction === reaction),
                  ),
                }
              : item,
          ),
        );
      } else {
        await chat.react(message.id, reaction);
        setMessages((current) =>
          current.map((item) =>
            item.id === message.id
              ? { ...item, reactions: [...item.reactions, { reaction, userId: selfId }] }
              : item,
          ),
        );
      }
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleSearch = async (): Promise<void> => {
    const term = searchTerm.trim();
    if (!term) {
      setSearchResults(null);
      return;
    }
    try {
      setSearchResults(await chat.searchMessages(term));
    } catch {
      setSearchResults([]);
    }
  };

  const resetNewForm = (): void => {
    setNewKind("direct");
    setNewPeer("");
    setNewName("");
    setNewDescription("");
    setNewCode("");
    setNewTopic("");
    setNewVisibility("PRIVATE");
    setNewMembers([]);
    setNewError("");
  };

  const handleCreate = async (): Promise<void> => {
    setNewError("");
    if (newKind === "direct" && !newPeer) {
      setNewError(t("chat.error.peerRequired"));
      return;
    }
    if (newKind !== "direct" && !newName.trim()) {
      setNewError(t("chat.error.nameRequired"));
      return;
    }
    if (newKind === "channel" && !CHANNEL_CODE_PATTERN.test(newCode.trim())) {
      setNewError(t("chat.error.codeInvalid"));
      return;
    }
    setSaving(true);
    try {
      const created = await chat.createConversation({
        kind: newKind,
        ...(newKind === "direct" ? { peerUserId: newPeer } : {}),
        ...(newKind !== "direct" ? { name: newName.trim(), description: newDescription.trim() } : {}),
        ...(newKind === "group" ? { memberIds: newMembers } : {}),
        ...(newKind === "channel"
          ? { code: newCode.trim(), topic: newTopic.trim(), visibility: newVisibility }
          : {}),
      });
      setNewOpen(false);
      resetNewForm();
      notify(t("chat.new.created"));
      await loadConversations(created.id);
      setActiveId(created.id);
    } catch {
      setNewError(t("chat.error.sendFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleAddMember = async (): Promise<void> => {
    if (!addMemberId || !activeId) return;
    try {
      const created = await chat.addParticipant(activeId, addMemberId, "MEMBER");
      setParticipants((current) => [...current, created]);
      setAddMemberId("");
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleRemoveMember = async (): Promise<void> => {
    if (!pendingRemove || !activeId) return;
    const target = pendingRemove;
    setPendingRemove(null);
    try {
      await chat.removeParticipant(activeId, target.userId);
      setParticipants((current) => current.filter((item) => item.userId !== target.userId));
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const handleArchive = async (): Promise<void> => {
    if (!activeId) return;
    setPendingArchive(false);
    try {
      await chat.archiveConversation(activeId);
      await loadConversations();
    } catch {
      notify(t("chat.error.sendFailed"), "error");
    }
  };

  const directoryOptions = directory
    .filter((user) => user.id !== selfId)
    .map((user) => ({ value: user.id, label: user.displayName }));

  const nonMembers = directoryOptions.filter(
    (option) => !participants.some((member) => member.userId === option.value),
  );

  const statusTone =
    realtime.status === "online" ? "success" : realtime.status === "offline" ? "danger" : "neutral";
  const statusLabel =
    realtime.status === "online"
      ? t("chat.online")
      : realtime.status === "offline"
        ? t("chat.offline")
        : t("chat.realtimeOff");

  let lastDay = "";

  return (
    <div className="page chat-page">
      <SectionHeader
        title={t("chat.title")}
        subtitle={t("chat.subtitle")}
        actions={
          <div className="chat-header-actions">
            <Badge tone={statusTone} dot>
              {statusLabel}
            </Badge>
            <Button icon="plus" onClick={() => setNewOpen(true)}>
              {t("chat.newConversation")}
            </Button>
          </div>
        }
      />

      <div className="chat-layout">
        <Card className="chat-sidebar" padding="none">
          <div className="chat-sidebar-head">
            <TextInput
              icon="search"
              placeholder={t("chat.searchConversations")}
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label={t("chat.searchConversations")}
            />
            <label className="chat-archived-toggle">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              <span>{t("chat.showArchived")}</span>
            </label>
          </div>
          {loading ? (
            <LoadingState label={t("common.loading")} />
          ) : visibleConversations.length === 0 ? (
            <EmptyState
              icon="message"
              title={t("chat.noConversations")}
              description={t("chat.noConversationsHint")}
              action={
                <Button icon="plus" onClick={() => setNewOpen(true)}>
                  {t("chat.newConversation")}
                </Button>
              }
            />
          ) : (
            <ul className="chat-conversation-list">
              {visibleConversations.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`chat-conversation ${item.id === activeId ? "is-active" : ""}`}
                    onClick={() => setActiveId(item.id)}
                  >
                    <Avatar name={item.name || t(`chat.type.${item.type}`)} size="md" />
                    <span className="chat-conversation-body">
                      <span className="chat-conversation-title">
                        <Icon name={conversationIcon(item.type)} size={14} />
                        <strong>{item.name || t(`chat.type.${item.type}`)}</strong>
                        {item.archivedAt ? <Badge tone="neutral">{t("chat.archived")}</Badge> : null}
                      </span>
                      <span className="chat-conversation-preview">{item.lastMessagePreview}</span>
                    </span>
                    <span className="chat-conversation-meta">
                      <span className="chat-time">{timeLabel(item.lastMessageAt)}</span>
                      {item.unreadCount > 0 ? (
                        <Badge tone="danger">{item.unreadCount.toLocaleString("fa-IR")}</Badge>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="chat-thread-card" padding="none">
          {!active ? (
            <EmptyState
              icon="message"
              title={t("chat.selectConversation")}
              description={t("chat.selectConversationHint")}
            />
          ) : (
            <>
              <header className="chat-thread-head">
                <div className="chat-thread-identity">
                  <Avatar name={active.name || t(`chat.type.${active.type}`)} size="md" />
                  <div>
                    <h2>{active.name || t(`chat.type.${active.type}`)}</h2>
                    <p>
                      <Badge tone="info">{t(`chat.type.${active.type}`)}</Badge>{" "}
                      {t("chat.memberCount", { count: participants.length.toLocaleString("fa-IR") })}
                      {active.topic ? ` · ${active.topic}` : ""}
                    </p>
                  </div>
                </div>
                <div className="chat-thread-tools">
                  <TextInput
                    icon="search"
                    placeholder={t("chat.searchMessages")}
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void handleSearch();
                    }}
                    aria-label={t("chat.searchMessages")}
                  />
                  <IconButton icon="users" label={t("chat.members")} onClick={() => setMembersOpen(true)} />
                  <IconButton
                    icon="archive"
                    label={t("chat.archive")}
                    onClick={() => setPendingArchive(true)}
                  />
                </div>
              </header>

              {searchResults ? (
                <div className="chat-search-results">
                  <div className="chat-search-head">
                    <strong>{t("chat.searchResults")}</strong>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setSearchResults(null);
                        setSearchTerm("");
                      }}
                    >
                      {t("chat.clearSearch")}
                    </Button>
                  </div>
                  {searchResults.length === 0 ? (
                    <p className="chat-empty-inline">{t("chat.noSearchResults")}</p>
                  ) : (
                    <ul>
                      {searchResults.map((item) => (
                        <li key={item.id}>
                          <strong>{nameFor(item.senderId)}</strong>
                          <span>{item.body}</span>
                          <span className="chat-time">{timeLabel(item.createdAt)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}

              <div className="chat-thread" ref={threadRef}>
                {threadLoading ? (
                  <LoadingState label={t("common.loading")} />
                ) : messages.length === 0 ? (
                  <EmptyState
                    icon="message"
                    title={t("chat.noMessages")}
                    description={t("chat.noMessagesHint")}
                  />
                ) : (
                  messages.map((message) => {
                    const mine = message.senderId === selfId;
                    const day = dayLabel(message.createdAt);
                    const showDay = day !== lastDay;
                    lastDay = day;
                    const parent = message.replyToId
                      ? messages.find((item) => item.id === message.replyToId)
                      : undefined;
                    return (
                      <div key={message.id}>
                        {showDay ? <div className="chat-day-divider">{day}</div> : null}
                        <article className={`chat-message ${mine ? "is-mine" : ""}`}>
                          {!mine ? <Avatar name={nameFor(message.senderId)} size="sm" /> : null}
                          <div className="chat-bubble-wrap">
                            {!mine ? (
                              <span className="chat-sender">{nameFor(message.senderId)}</span>
                            ) : null}
                            {parent ? (
                              <div className="chat-quote">
                                <span>{t("chat.replyingTo")}</span>
                                <strong>{nameFor(parent.senderId)}</strong>
                                <em>{parent.body.slice(0, 80)}</em>
                              </div>
                            ) : null}
                            <div
                              className={`chat-bubble ${message.deleted ? "is-deleted" : ""} ${
                                message.failed ? "is-failed" : ""
                              }`}
                            >
                              {message.deleted ? (
                                <em>{t("chat.deleted")}</em>
                              ) : (
                                <p>{message.body}</p>
                              )}
                              <span className="chat-bubble-meta">
                                <span className="chat-time">{timeLabel(message.createdAt)}</span>
                                {message.editedAt ? <span>· {t("chat.edited")}</span> : null}
                                {message.pending ? <span>· {t("chat.sending")}</span> : null}
                                {message.failed ? <span>· {t("chat.failed")}</span> : null}
                              </span>
                            </div>

                            {groupReactions(message).length > 0 ? (
                              <div className="chat-reactions">
                                {groupReactions(message).map((entry) => (
                                  <button
                                    key={entry.reaction}
                                    type="button"
                                    className={`chat-reaction ${
                                      entry.userIds.includes(selfId) ? "is-mine" : ""
                                    }`}
                                    onClick={() => void handleReaction(message, entry.reaction)}
                                  >
                                    <span>{entry.reaction}</span>
                                    <small>{entry.count.toLocaleString("fa-IR")}</small>
                                  </button>
                                ))}
                              </div>
                            ) : null}

                            {!message.deleted ? (
                              <div className="chat-message-actions">
                                <button type="button" onClick={() => setReplyTo(message)}>
                                  {t("chat.reply")}
                                </button>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setReactionFor(reactionFor === message.id ? "" : message.id)
                                  }
                                >
                                  {t("chat.react")}
                                </button>
                                {mine ? (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setEditing(message);
                                        setEditDraft(message.body);
                                      }}
                                    >
                                      {t("chat.edit")}
                                    </button>
                                    <button type="button" onClick={() => setPendingDelete(message)}>
                                      {t("chat.delete")}
                                    </button>
                                  </>
                                ) : null}
                              </div>
                            ) : null}

                            {reactionFor === message.id ? (
                              <div className="chat-reaction-picker">
                                {QUICK_REACTIONS.map((emoji) => (
                                  <button
                                    key={emoji}
                                    type="button"
                                    onClick={() => void handleReaction(message, emoji)}
                                  >
                                    {emoji}
                                  </button>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        </article>
                      </div>
                    );
                  })
                )}
              </div>

              {realtime.typingUserIds.length > 0 ? (
                <div className="chat-typing">
                  {realtime.typingUserIds.map(nameFor).join("، ")} {t("chat.typing")}
                </div>
              ) : null}

              <footer className="chat-composer">
                {replyTo ? (
                  <div className="chat-reply-banner">
                    <span>
                      {t("chat.replyingTo")} <strong>{nameFor(replyTo.senderId)}</strong>:{" "}
                      {replyTo.body.slice(0, 60)}
                    </span>
                    <IconButton icon="close" label={t("common.cancel")} onClick={() => setReplyTo(null)} />
                  </div>
                ) : null}
                <div className="chat-composer-row">
                  <TextArea
                    label=""
                    rows={2}
                    value={draft}
                    placeholder={t("chat.messagePlaceholder")}
                    aria-label={t("chat.messagePlaceholder")}
                    onChange={(event) => handleDraftChange(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void handleSend();
                      }
                    }}
                  />
                  <Button icon="send" onClick={() => void handleSend()} disabled={!draft.trim()}>
                    {t("chat.send")}
                  </Button>
                </div>
              </footer>
            </>
          )}
        </Card>
      </div>

      <Modal
        open={newOpen}
        title={t("chat.newConversation")}
        onClose={() => {
          setNewOpen(false);
          resetNewForm();
        }}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setNewOpen(false);
                resetNewForm();
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void handleCreate()} disabled={saving}>
              {t("chat.new.create")}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <SelectInput
            label={t("chat.new.kind")}
            value={newKind}
            onChange={(event) => setNewKind(event.target.value as NewKind)}
            options={CONVERSATION_TYPES.map((type) => ({
              value: type.toLowerCase(),
              label: t(`chat.type.${type}`),
            }))}
          />
          {newKind === "direct" ? (
            <SelectInput
              label={t("chat.new.peer")}
              value={newPeer}
              onChange={(event) => setNewPeer(event.target.value)}
              options={[{ value: "", label: "—" }, ...directoryOptions]}
            />
          ) : (
            <>
              <TextInput
                label={t("chat.new.name")}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
              <TextArea
                label={t("chat.new.description")}
                rows={2}
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
              />
            </>
          )}
          {newKind === "group" ? (
            <div className="chat-member-picker">
              <span className="field-label">{t("chat.new.members")}</span>
              {directoryOptions.map((option) => (
                <label key={option.value} className="chat-member-option">
                  <input
                    type="checkbox"
                    checked={newMembers.includes(option.value)}
                    onChange={(event) =>
                      setNewMembers((current) =>
                        event.target.checked
                          ? [...current, option.value]
                          : current.filter((item) => item !== option.value),
                      )
                    }
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          ) : null}
          {newKind === "channel" ? (
            <>
              <TextInput
                label={t("chat.new.code")}
                hint={t("chat.new.codeHint")}
                value={newCode}
                onChange={(event) => setNewCode(event.target.value)}
              />
              <TextInput
                label={t("chat.new.topic")}
                value={newTopic}
                onChange={(event) => setNewTopic(event.target.value)}
              />
              <SelectInput
                label={t("chat.new.visibility")}
                value={newVisibility}
                onChange={(event) => setNewVisibility(event.target.value as ChannelVisibility)}
                options={(["PUBLIC", "PRIVATE", "RESTRICTED"] as ChannelVisibility[]).map((value) => ({
                  value,
                  label: t(`chat.visibility.${value}`),
                }))}
              />
            </>
          ) : null}
          {newError ? <p className="form-error">{newError}</p> : null}
        </div>
      </Modal>

      <Modal
        open={Boolean(editing)}
        title={t("chat.editMessage")}
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void handleEditSave()}>{t("common.save")}</Button>
          </>
        }
      >
        <TextArea
          label={t("chat.editMessage")}
          rows={4}
          value={editDraft}
          onChange={(event) => setEditDraft(event.target.value)}
        />
      </Modal>

      <Modal open={membersOpen} title={t("chat.members")} onClose={() => setMembersOpen(false)}>
        <ul className="chat-member-list">
          {participants.map((member) => (
            <li key={member.id}>
              <Avatar name={nameFor(member.userId)} size="sm" />
              <span className="chat-member-name">{nameFor(member.userId)}</span>
              <Badge tone="info">{t(`chat.role.${member.role}`)}</Badge>
              {member.userId !== selfId ? (
                <IconButton
                  icon="xCircle"
                  label={t("chat.removeMember")}
                  onClick={() => setPendingRemove(member)}
                />
              ) : null}
            </li>
          ))}
        </ul>
        {nonMembers.length > 0 ? (
          <div className="chat-add-member">
            <SelectInput
              label={t("chat.addMember")}
              value={addMemberId}
              onChange={(event) => setAddMemberId(event.target.value)}
              options={[{ value: "", label: "—" }, ...nonMembers]}
            />
            <Button icon="plus" onClick={() => void handleAddMember()} disabled={!addMemberId}>
              {t("chat.addMember")}
            </Button>
          </div>
        ) : null}
        <p className="chat-role-hint">
          {PARTICIPANT_ROLES.map((role) => t(`chat.role.${role}`)).join(" · ")}
        </p>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={t("chat.delete")}
        description={t("chat.deleteConfirm")}
        onConfirm={() => void handleDelete()}
        onClose={() => setPendingDelete(null)}
        danger
      />
      <ConfirmDialog
        open={Boolean(pendingRemove)}
        title={t("chat.removeMember")}
        description={t("chat.removeMemberConfirm")}
        onConfirm={() => void handleRemoveMember()}
        onClose={() => setPendingRemove(null)}
        danger
      />
      <ConfirmDialog
        open={pendingArchive}
        title={t("chat.archive")}
        description={t("chat.archiveConfirm")}
        onConfirm={() => void handleArchive()}
        onClose={() => setPendingArchive(false)}
      />

      {toast ? <Toast message={toast} tone={toastTone} onClose={() => setToast("")} /> : null}
    </div>
  );
}

export default ChatPage;

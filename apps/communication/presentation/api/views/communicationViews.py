"""Communication REST views (Phase 08 §30).

Management, history, scheduling and admin surfaces stay REST; the live
transport (messages/typing/presence/signaling/read receipts) is WebSocket.
Views are thin: authenticate → map transport → call use case → envelope.
"""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.application.commands.communicationCommands import (
    AcceptCallCommand,
    AddParticipantCommand,
    ArchiveConversationCommand,
    CancelMeetingCommand,
    ChangeParticipantRoleCommand,
    CreateChannelCommand,
    CreateDirectConversationCommand,
    CreateGroupConversationCommand,
    CreateLetterCommand,
    CreateMeetingCommand,
    DeleteMessageCommand,
    DispatchLetterCommand,
    EditMessageCommand,
    EndCallCommand,
    EndMeetingCommand,
    JoinChannelCommand,
    JoinMeetingCommand,
    LeaveConversationCommand,
    LeaveMeetingCommand,
    MarkConversationReadCommand,
    PinMessageCommand,
    ReactToMessageCommand,
    ReceiveLetterCommand,
    RejectCallCommand,
    RelaySignalCommand,
    RemoveParticipantCommand,
    RsvpMeetingCommand,
    SendMessageCommand,
    SignLetterCommand,
    StartCallCommand,
    StartMeetingCommand,
    StartRecordingCommand,
    StopRecordingCommand,
    SubmitLetterCommand,
    UnpinMessageCommand,
    UpdateConversationCommand,
    UpdateParticipantPreferencesCommand,
    UpdatePresenceCommand,
)
from apps.communication.application.queries.communicationQueries import (
    GetCallQuery,
    GetConversationQuery,
    GetMeetingQuery,
    ListConversationsQuery,
    ListLettersQuery,
    ListMeetingsQuery,
    ListMessagesQuery,
    ListParticipantsQuery,
    ListPinsQuery,
    ListRecordingsQuery,
    PresenceQuery,
    SearchMessagesQuery,
)
from apps.communication.application.services.communicationSupport import UserDirectory
from apps.communication.infrastructure import container
from apps.communication.presentation.api.serializers.communicationSerializers import (
    AddParticipantSerializer,
    ChangeRoleSerializer,
    CreateChannelSerializer,
    CreateDirectSerializer,
    CreateGroupSerializer,
    CreateLetterSerializer,
    CreateMeetingSerializer,
    EditMessageSerializer,
    MarkReadSerializer,
    PreferencesSerializer,
    ReactSerializer,
    RelaySignalSerializer,
    RsvpSerializer,
    SendMessageSerializer,
    StartCallSerializer,
    UpdateConversationSerializer,
    UpdatePresenceSerializer,
)
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope

COMM_ERRORS = [
    "PERM_PERMISSION_DENIED",
    "TENANT_ACCESS_DENIED",
    "DUP_IDENTIFIER",
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "SYS_CONCURRENCY_CONFLICT",
]


def _dto(obj: object) -> dict:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return dict(obj)


# -- conversations ------------------------------------------------------------------


class ConversationListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        dto = container.listConversationsUseCase().execute(
            ListConversationsQuery(
                includeArchived=request.query_params.get("includeArchived") == "true"
            )
        )
        return Response(successEnvelope([_dto(item) for item in dto]))

    @enforceRateLimit("communication:createConversation")
    def post(self, request: Request) -> Response:
        kind = str(request.data.get("kind", "direct")).lower()
        if kind == "group":
            serializer = CreateGroupSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            dto = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(
                    name=data["name"],
                    description=data["description"],
                    memberIds=[str(value) for value in data["memberIds"]],
                )
            )
        elif kind == "channel":
            serializer = CreateChannelSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            dto = container.createChannelUseCase().execute(
                CreateChannelCommand(
                    name=data["name"],
                    code=data["code"],
                    topic=data["topic"],
                    visibility=data["visibility"],
                    description=data["description"],
                )
            )
        else:
            serializer = CreateDirectSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            dto = container.createDirectUseCase().execute(
                CreateDirectConversationCommand(
                    peerUserId=str(serializer.validated_data["peerUserId"])
                )
            )
        return Response(successEnvelope(_dto(dto)), status=201)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversationId: str) -> Response:
        dto = container.getConversationUseCase().execute(
            GetConversationQuery(conversationId=conversationId)
        )
        return Response(successEnvelope(_dto(dto)))

    def patch(self, request: Request, conversationId: str) -> Response:
        serializer = UpdateConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.updateConversationUseCase().execute(
            UpdateConversationCommand(
                conversationId=conversationId,
                name=data.get("name", ""),
                description=data.get("description", ""),
                topic=data.get("topic", ""),
                visibility=data.get("visibility", ""),
            )
        )
        return Response(successEnvelope(_dto(dto)))


class ConversationArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversationId: str) -> Response:
        dto = container.archiveConversationUseCase().execute(
            ArchiveConversationCommand(conversationId=conversationId)
        )
        return Response(successEnvelope(_dto(dto)))


class ParticipantListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversationId: str) -> Response:
        dto = container.listParticipantsUseCase().execute(
            ListParticipantsQuery(conversationId=conversationId)
        )
        return Response(successEnvelope([_dto(item) for item in dto]))

    def post(self, request: Request, conversationId: str) -> Response:
        serializer = AddParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.addParticipantUseCase().execute(
            AddParticipantCommand(
                conversationId=conversationId,
                userId=str(data["userId"]),
                role=data["role"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class ParticipantDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(
        self, request: Request, conversationId: str, userId: str
    ) -> Response:
        dto = container.removeParticipantUseCase().execute(
            RemoveParticipantCommand(conversationId=conversationId, userId=userId)
        )
        return Response(successEnvelope(dto))

    def patch(self, request: Request, conversationId: str, userId: str) -> Response:
        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeParticipantRoleUseCase().execute(
            ChangeParticipantRoleCommand(
                conversationId=conversationId,
                userId=userId,
                role=serializer.validated_data["role"],
            )
        )
        return Response(successEnvelope(_dto(dto)))


class ParticipantLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversationId: str) -> Response:
        dto = container.leaveConversationUseCase().execute(
            LeaveConversationCommand(conversationId=conversationId)
        )
        return Response(successEnvelope(dto))


class ParticipantPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, conversationId: str) -> Response:
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.updateParticipantPreferencesUseCase().execute(
            UpdateParticipantPreferencesCommand(
                conversationId=conversationId,
                isMuted=data.get("isMuted"),
                notificationLevel=data.get("notificationLevel", ""),
            )
        )
        return Response(successEnvelope(_dto(dto)))


class ChannelJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversationId: str) -> Response:
        dto = container.joinChannelUseCase().execute(
            JoinChannelCommand(conversationId=conversationId)
        )
        return Response(successEnvelope(_dto(dto)))


# -- messages -------------------------------------------------------------------------


class MessageListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversationId: str) -> Response:
        page = container.listMessagesUseCase().execute(
            ListMessagesQuery(
                conversationId=conversationId,
                beforeId=str(request.query_params.get("beforeId", "") or ""),
                threadRootId=str(request.query_params.get("threadRootId", "") or ""),
                limit=min(int(request.query_params.get("limit", 50) or 50), 100),
            )
        )
        return Response(
            successEnvelope(
                [_dto(item) for item in page.items],
                meta={"totalCount": page.totalCount, "hasNext": page.hasNext},
            )
        )

    @enforceRateLimit("communication:sendMessage")
    def post(self, request: Request, conversationId: str) -> Response:
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.sendMessageUseCase().execute(
            SendMessageCommand(
                conversationId=conversationId,
                body=data["body"],
                messageType=data["messageType"],
                replyToId=str(data["replyToId"]) if data["replyToId"] else "",
                clientRequestId=data["clientRequestId"],
                attachments=list(data["attachments"]),
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class MessageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, messageId: str) -> Response:
        serializer = EditMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.editMessageUseCase().execute(
            EditMessageCommand(messageId=messageId, body=serializer.validated_data["body"])
        )
        return Response(successEnvelope(_dto(dto)))

    def delete(self, request: Request, messageId: str) -> Response:
        result = container.deleteMessageUseCase().execute(
            DeleteMessageCommand(messageId=messageId)
        )
        return Response(successEnvelope(result))


class MessageReactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, messageId: str) -> Response:
        serializer = ReactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.reactToMessageUseCase().execute(
            ReactToMessageCommand(
                messageId=messageId, reaction=serializer.validated_data["reaction"]
            )
        )
        return Response(successEnvelope(result), status=201)

    def delete(self, request: Request, messageId: str) -> Response:
        reaction = str(request.query_params.get("reaction", "") or "")
        result = container.removeReactionUseCase().execute(
            RemoveReactionCommand(messageId=messageId, reaction=reaction)  # type: ignore[arg-type]
        )
        return Response(successEnvelope(result))


class ConversationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conversationId: str) -> Response:
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.markConversationReadUseCase().execute(
            MarkConversationReadCommand(
                conversationId=conversationId,
                uptoMessageId=str(serializer.validated_data["uptoMessageId"]),
            )
        )
        return Response(successEnvelope(result))


class PinListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, conversationId: str) -> Response:
        pins = container.listPinsUseCase().execute(
            ListPinsQuery(conversationId=conversationId)
        )
        return Response(successEnvelope([_dto(pin) for pin in pins]))

    def post(self, request: Request, conversationId: str) -> Response:
        messageId = str(request.data.get("messageId", "") or "")
        dto = container.pinMessageUseCase().execute(
            PinMessageCommand(conversationId=conversationId, messageId=messageId)
        )
        return Response(successEnvelope(_dto(dto)), status=201)

    def delete(self, request: Request, conversationId: str, messageId: str) -> Response:
        result = container.unpinMessageUseCase().execute(
            UnpinMessageCommand(conversationId=conversationId, messageId=messageId)
        )
        return Response(successEnvelope(result))


class MessageSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        hits = container.searchMessagesUseCase().execute(
            SearchMessagesQuery(
                query=str(request.query_params.get("q", "") or ""),
                limit=min(int(request.query_params.get("limit", 25) or 25), 100),
            )
        )
        return Response(successEnvelope([_dto(hit) for hit in hits]))


# -- meetings -------------------------------------------------------------------------


class MeetingListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        meetings = container.listMeetingsUseCase().execute(
            ListMeetingsQuery(
                conversationId=str(request.query_params.get("conversationId", "") or "")
            )
        )
        return Response(successEnvelope([_dto(item) for item in meetings]))

    @enforceRateLimit("communication:meetingCreate")
    def post(self, request: Request) -> Response:
        serializer = CreateMeetingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.createMeetingUseCase().execute(
            CreateMeetingCommand(
                conversationId=str(data["conversationId"]),
                title=data["title"],
                description=data["description"],
                scheduledStart=data["scheduledStart"],
                scheduledEnd=data["scheduledEnd"],
                inviteeIds=[str(value) for value in data["inviteeIds"]],
                clientRequestId=data["clientRequestId"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class MeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, meetingId: str) -> Response:
        dto = container.getMeetingUseCase().execute(GetMeetingQuery(meetingId=meetingId))
        return Response(successEnvelope(_dto(dto)))


class MeetingLifecycleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str, action: str) -> Response:
        if action == "start":
            dto = container.startMeetingUseCase().execute(
                StartMeetingCommand(meetingId=meetingId)
            )
        elif action == "end":
            dto = container.endMeetingUseCase().execute(EndMeetingCommand(meetingId=meetingId))
        elif action == "cancel":
            dto = container.cancelMeetingUseCase().execute(
                CancelMeetingCommand(meetingId=meetingId)
            )
        elif action == "join":
            dto = container.joinMeetingUseCase().execute(
                JoinMeetingCommand(meetingId=meetingId)
            )
        elif action == "leave":
            dto = container.leaveMeetingUseCase().execute(
                LeaveMeetingCommand(meetingId=meetingId)
            )
        else:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"action": "unsupported"})
        return Response(successEnvelope(_dto(dto) if not isinstance(dto, dict) else dto))


class MeetingRsvpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = RsvpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.rsvpMeetingUseCase().execute(
            RsvpMeetingCommand(
                meetingId=meetingId, accepted=serializer.validated_data["accepted"]
            )
        )
        return Response(successEnvelope(result))


class MeetingSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        from apps.communication.application.queries.communicationQueries import (
            GenerateMeetingSummaryQuery,
        )

        dto = container.generateMeetingSummaryUseCase().execute(
            GenerateMeetingSummaryQuery(meetingId=meetingId)
        )
        return Response(successEnvelope(_dto(dto)))


# -- recordings ------------------------------------------------------------------------


class RecordingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, meetingId: str) -> Response:
        recordings = container.listRecordingsUseCase().execute(
            ListRecordingsQuery(meetingId=meetingId)
        )
        return Response(successEnvelope([_dto(item) for item in recordings]))

    def post(self, request: Request, meetingId: str) -> Response:
        dto = container.startRecordingUseCase().execute(
            StartRecordingCommand(meetingId=meetingId)
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class RecordingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, recordingId: str, action: str) -> Response:
        if action == "stop":
            dto = container.stopRecordingUseCase().execute(
                StopRecordingCommand(recordingId=recordingId)
            )
        elif action == "publish":
            from apps.communication.application.commands.communicationCommands import (
                PublishRecordingCommand,
            )

            dto = container.publishRecordingUseCase().execute(
                PublishRecordingCommand(
                    recordingId=recordingId,
                    storageRef=str(request.data.get("storageRef", "") or ""),
                    failed=bool(request.data.get("failed", False)),
                    reason=str(request.data.get("reason", "") or ""),
                )
            )
        else:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"action": "unsupported"})
        return Response(successEnvelope(_dto(dto)))


# -- calls & signaling --------------------------------------------------------------------


class CallView(APIView):
    permission_classes = [IsAuthenticated]

    @enforceRateLimit("communication:callStart")
    def post(self, request: Request) -> Response:
        serializer = StartCallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.startCallUseCase().execute(
            StartCallCommand(
                conversationId=str(data["conversationId"]) if data["conversationId"] else "",
                meetingId=str(data["meetingId"]) if data["meetingId"] else "",
                mediaType=data["mediaType"],
                clientRequestId=data["clientRequestId"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class CallDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, callId: str) -> Response:
        dto = container.getCallUseCase().execute(GetCallQuery(callId=callId))
        return Response(successEnvelope(_dto(dto)))


class CallActionView(APIView):
    """REST fallback for call control; the live path is the WS gateway."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, callId: str, action: str) -> Response:
        if action == "accept":
            dto = container.acceptCallUseCase().execute(AcceptCallCommand(callId=callId))
        elif action == "reject":
            dto = container.rejectCallUseCase().execute(RejectCallCommand(callId=callId))
        elif action == "end":
            dto = container.endCallUseCase().execute(EndCallCommand(callId=callId))
        elif action == "signal":
            serializer = RelaySignalSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            result = container.relaySignalUseCase().execute(
                RelaySignalCommand(
                    envelope=data["envelope"],
                    targetUserId=str(data["targetUserId"]) if data["targetUserId"] else "",
                )
            )
            return Response(successEnvelope(result))
        else:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"action": "unsupported"})
        return Response(successEnvelope(_dto(dto)))


# -- presence (§7) --------------------------------------------------------------------------


class PresenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.getPresenceUseCase().execute(
            PresenceQuery(userIds=str(request.query_params.get("userIds", "") or ""))
        )
        return Response(successEnvelope(result))

    @enforceRateLimit("communication:presenceUpdate")
    def put(self, request: Request) -> Response:
        serializer = UpdatePresenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.updatePresenceUseCase().execute(
            UpdatePresenceCommand(status=serializer.validated_data["status"])
        )
        return Response(successEnvelope(result))


# -- official letters (§16) --------------------------------------------------------------------


class LetterListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        letters = container.listLettersUseCase().execute(
            ListLettersQuery(
                status=str(request.query_params.get("status", "") or ""),
                limit=min(int(request.query_params.get("limit", 50) or 50), 200),
            )
        )
        return Response(successEnvelope([_dto(item) for item in letters]))

    def post(self, request: Request) -> Response:
        serializer = CreateLetterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.createLetterUseCase().execute(
            CreateLetterCommand(
                recipientId=str(data["recipientId"]),
                subject=data["subject"],
                body=data["body"],
                recipientOrganization=data["recipientOrganization"],
                recipientUnit=data["recipientUnit"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class LetterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, letterId: str, action: str) -> Response:
        commands = {
            "submit": SubmitLetterCommand,
            "approve": SubmitLetterCommand,  # transitions carry their own action
            "sign": SignLetterCommand,
            "dispatch": DispatchLetterCommand,
            "receive": ReceiveLetterCommand,
        }
        if action == "approve":
            command = SubmitLetterCommand(letterId=letterId, action="approve")
        else:
            commandClass = commands[action]
            command = commandClass(letterId=letterId)
        dto = container.letterTransitionUseCase().execute(command)
        return Response(successEnvelope(_dto(dto)))


# -- metrics (§39) ---------------------------------------------------------------------------


class CommunicationMetricsView(APIView):
    """Operational snapshot (§39). Bodies/tokens are never in metrics."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        return Response(successEnvelope(communicationMetrics().snapshot()))


# -- OpenAPI registration -----------------------------------------------------------------------


def registerCommunicationEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/communication/conversations",
            summary="List conversations for the current user.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/conversations",
            summary="Create a direct/group conversation or channel (kind=direct|group|channel).",
            permission="conversation.create",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/conversations/{conversationId}",
            summary="Conversation detail.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/communication/conversations/{conversationId}",
            summary="Update conversation/channel profile.",
            permission="conversation.update",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/conversations/{conversationId}/archive",
            summary="Archive conversation.",
            permission="conversation.moderate",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/conversations/{conversationId}/join",
            summary="Join a public channel.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/conversations/{conversationId}/messages",
            summary="Message history (cursor pagination, thread filter).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/conversations/{conversationId}/messages",
            summary="Send message (idempotent via clientRequestId).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/conversations/{conversationId}/read",
            summary="Bulk read receipt up to a message.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/messages/search",
            summary="Search messages across the caller's conversations.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/meetings",
            summary="Schedule meeting (idempotent via clientRequestId).",
            permission="meeting.manage",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/meetings/{meetingId}/{action}",
            summary="Meeting lifecycle: start|end|cancel|join|leave.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/calls",
            summary="Start call session (WebRTC signaling over WS).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="PUT",
            path="api/v1/communication/presence",
            summary="Update ephemeral presence.",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/letters",
            summary="Create official letter (dedicated §16 model).",
            permission="letter.create",
            errorCodes=COMM_ERRORS,
        ),
        # -- Phase 10 surfaces ------------------------------------------------
        EndpointSpec(
            method="GET",
            path="api/v1/communication/messages/{messageId}/revisions",
            summary="Message edit history for compliance/audit (Phase 10 §11).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/meetings/{meetingId}/transcript",
            summary="Request a meeting transcript (idempotent per meeting, §34).",
            permission="meeting.manage",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/meetings/{meetingId}/transcript",
            summary="Fetch transcript and its segments once READY (§34/§35).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/transcripts/{transcriptId}/complete",
            summary="Mark transcript READY with content reference + segments.",
            permission="meeting.manage",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/meetings/{meetingId}/capabilities",
            summary="Set a per-user granular meeting capability override (§30).",
            permission="meeting.manage",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/meetings/{meetingId}/capabilities",
            summary="Resolve an effective meeting capability (role matrix + override).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/communication/blocks",
            summary="List the caller's active user blocks (§70).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/blocks",
            summary="Block a user for direct message / call / meeting invite (§70).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/communication/blocks/{blockedUserId}",
            summary="Lift (unblock) a previously blocked user (§70).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/communication/call-sessions",
            summary="Provider-agnostic call session bootstrap (§25).",
            permission="authenticated",
            errorCodes=COMM_ERRORS,
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)

"""Permit-to-work API.

Thin on purpose. Every refusal in here comes from
``domain/services/permitRules`` via ``application/services/permitService``;
this layer resolves the tenant and the actor, shapes JSON, and turns a
``PermitRuleViolation`` into a 422 that carries both a stable machine code
and the Persian sentence the person at the keyboard needs.

A safety refusal is returned as 422 rather than 400 because the request was
well-formed — the *plant* was not ready — and the client has to tell those
apart to show the right thing.
"""

from __future__ import annotations

import uuid

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.safety.application.services.permitService import (
    Actor,
    activatePermit,
    applyIsolation,
    approvePermit,
    cancelPermit,
    closePermit,
    completePermit,
    confirmPrecaution,
    createPermit,
    permitReadiness,
    permitValidityView,
    rejectPermit,
    removeIsolation,
    resumePermit,
    scanPermitExpiry,
    submitPermit,
    suspendPermit,
    verifyIsolation,
)
from apps.safety.domain.services.permitRules import PermitRuleViolation
from apps.safety.domain.valueObjects.permitState import (
    ENERGY_LABELS_FA,
    ENERGY_TYPES,
    PERMIT_STATUS_LABELS_FA,
    PERMIT_STATUSES,
    PERMIT_TYPE_LABELS_FA,
    PERMIT_TYPES,
    RISK_LABELS_FA,
    RISK_LEVELS,
    maxValidityHoursFor,
    requiresIsolation,
)
from apps.safety.infrastructure.permitRepository import (
    PermitNotFound,
    createIsolationRow,
    eventRows,
    isolationRows,
    listPermits,
    loadPermit,
    precautionRows,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.response import successEnvelope


def tenant() -> uuid.UUID:
    context = currentContext()
    value = context.tenantId or context.actorTenantId
    if not value:
        raise ValueError("Tenant scope could not be resolved.")
    return uuid.UUID(str(value))


def actor() -> Actor:
    """Who is acting, from the request context.

    The display name matters as much as the id here: it is written onto the
    permit and must stay readable after the account is gone.
    """
    context = currentContext()
    rawId = getattr(context, "actorId", "")
    try:
        actorId: uuid.UUID | None = uuid.UUID(str(rawId))
    except (ValueError, TypeError):
        actorId = None
    name = (
        getattr(context, "actorDisplayName", "")
        or getattr(context, "actorName", "")
        or getattr(context, "actorEmail", "")
        or ""
    )
    return Actor(id=actorId, name=str(name)[:160])


def permitRow(permit, *, now=None) -> dict:
    """List-shaped permit: enough to triage, not the whole file."""
    return {
        "id": str(permit.id),
        "number": permit.number,
        "permitType": permit.permitType,
        "permitTypeLabel": PERMIT_TYPE_LABELS_FA.get(permit.permitType, permit.permitType),
        "status": permit.status,
        "statusLabel": PERMIT_STATUS_LABELS_FA.get(permit.status, permit.status),
        "title": permit.title,
        "riskLevel": permit.riskLevel,
        "riskLabel": RISK_LABELS_FA.get(permit.riskLevel, permit.riskLevel),
        "deviceId": str(permit.deviceId) if permit.deviceId else None,
        "workOrderId": str(permit.workOrderId) if permit.workOrderId else None,
        "locationName": permit.locationName,
        "requesterName": permit.requesterName,
        "performerName": permit.performerName,
        "contractorName": permit.contractorName,
        "personnelCount": permit.personnelCount,
        "approverName": permit.approverName,
        "validFrom": permit.validFrom.isoformat() if permit.validFrom else None,
        "validTo": permit.validTo.isoformat() if permit.validTo else None,
        "createdAt": permit.createdAt.isoformat() if permit.createdAt else None,
        "requiresIsolation": requiresIsolation(permit.permitType),
        "validity": permitValidityView(permit, now=now),
    }


def permitDetail(tenantId: uuid.UUID, permit) -> dict:
    now = timezone.now()
    payload = permitRow(permit, now=now)
    payload.update(
        {
            "description": permit.description,
            "maxValidityHours": maxValidityHoursFor(permit.permitType),
            "suspensionReason": permit.suspensionReason,
            "rejectionReason": permit.rejectionReason,
            "cancellationReason": permit.cancellationReason,
            "closureNote": permit.closureNote,
            "closedByName": permit.closedByName,
            "readiness": permitReadiness(tenantId, permit),
            "precautions": [
                {
                    "id": str(x.id),
                    "code": x.code,
                    "text": x.text,
                    "isMandatory": x.isMandatory,
                    "confirmed": x.confirmed,
                    "confirmedByName": x.confirmedByName,
                    "confirmedAt": x.confirmedAt.isoformat() if x.confirmedAt else None,
                    "note": x.note,
                }
                for x in precautionRows(tenantId, permit.id)
            ],
            "isolations": [
                {
                    "id": str(x.id),
                    "pointCode": x.pointCode,
                    "description": x.description,
                    "energyType": x.energyType,
                    "energyLabel": ENERGY_LABELS_FA.get(x.energyType, x.energyType),
                    "isolationMethod": x.isolationMethod,
                    "lockTag": x.lockTag,
                    "appliedByName": x.appliedByName,
                    "appliedAt": x.appliedAt.isoformat() if x.appliedAt else None,
                    "verifiedByName": x.verifiedByName,
                    "verifiedAt": x.verifiedAt.isoformat() if x.verifiedAt else None,
                    "removedByName": x.removedByName,
                    "removedAt": x.removedAt.isoformat() if x.removedAt else None,
                    "isApplied": bool(x.appliedById) and not x.removedById,
                    "isVerified": bool(x.verifiedById) and not x.removedById,
                    "isRemoved": bool(x.removedById),
                }
                for x in isolationRows(tenantId, permit.id)
            ],
            # The trail is part of the document, not a separate audit screen.
            # If it takes a second click, it is not read.
            "events": [
                {
                    "id": str(x.id),
                    "action": x.action,
                    "fromStatus": x.fromStatus,
                    "toStatus": x.toStatus,
                    "toStatusLabel": PERMIT_STATUS_LABELS_FA.get(x.toStatus, x.toStatus),
                    "actorName": x.actorName,
                    "note": x.note,
                    "occurredAt": x.occurredAt.isoformat() if x.occurredAt else None,
                }
                for x in eventRows(tenantId, permit.id)
            ],
        }
    )
    return payload


def safetyRefusal(error: PermitRuleViolation) -> Response:
    """422: the request was fine, the plant was not ready."""
    return Response(
        {
            "success": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "category": "safetyRule",
            },
        },
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


class Base(APIView):
    authentication_classes = [BearerSessionAuthentication]

    def get_permissions(self):
        path = self.request.path
        method = self.request.method

        action = "safety.permit.view"
        if method in ("POST", "PATCH", "PUT"):
            if "/isolations" in path:
                action = "safety.permit.isolate"
            elif path.endswith(("/approve", "/reject", "/suspend", "/cancel")):
                action = "safety.permit.approve"
            elif path.endswith("/close"):
                action = "safety.permit.close"
            else:
                # create, submit, activate, resume, complete, confirm a
                # precaution — all things the crew doing the work does.
                action = "safety.permit.request"
        return [IsAuthenticated(), actionPermission(action)()]

    def handle_exception(self, exc):
        if isinstance(exc, PermitRuleViolation):
            return safetyRefusal(exc)
        if isinstance(exc, PermitNotFound):
            return Response(
                {"success": False, "error": {"code": "permit.notFound", "message": "مجوز یافت نشد."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return super().handle_exception(exc)


class PermitCreateSerializer(serializers.Serializer):
    permitType = serializers.ChoiceField(choices=PERMIT_TYPES)
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    riskLevel = serializers.ChoiceField(choices=RISK_LEVELS, default="medium")
    deviceId = serializers.UUIDField(required=False, allow_null=True)
    workOrderId = serializers.UUIDField(required=False, allow_null=True)
    locationId = serializers.UUIDField(required=False, allow_null=True)
    locationName = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=240
    )
    performerName = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=240
    )
    contractorName = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=240
    )
    personnelCount = serializers.IntegerField(required=False, min_value=1, default=1)
    validFrom = serializers.DateTimeField(required=False, allow_null=True)
    validTo = serializers.DateTimeField(required=False, allow_null=True)
    extraPrecautions = serializers.ListField(child=serializers.DictField(), required=False)


class IsolationCreateSerializer(serializers.Serializer):
    pointCode = serializers.CharField(max_length=60)
    description = serializers.CharField(max_length=500)
    energyType = serializers.ChoiceField(choices=ENERGY_TYPES)
    isolationMethod = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=240
    )
    lockTag = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=60
    )


class PermitListView(Base):
    def get(self, request):
        tenantId = tenant()
        permits = listPermits(
            tenantId,
            status=request.query_params.get("status", "").strip(),
            permitType=request.query_params.get("permitType", "").strip(),
            deviceId=request.query_params.get("deviceId") or None,
            liveOnly=request.query_params.get("liveOnly") == "true",
        )
        now = timezone.now()
        return Response(
            successEnvelope(
                {
                    "items": [permitRow(x, now=now) for x in permits],
                    # Shipped with the list so the form never has to guess
                    # which types demand an isolation register, and so the
                    # Persian labels live in exactly one place.
                    "options": {
                        "statuses": [
                            {"value": x, "label": PERMIT_STATUS_LABELS_FA.get(x, x)}
                            for x in PERMIT_STATUSES
                        ],
                        "types": [
                            {
                                "value": x,
                                "label": PERMIT_TYPE_LABELS_FA.get(x, x),
                                "requiresIsolation": requiresIsolation(x),
                                "maxValidityHours": maxValidityHoursFor(x),
                            }
                            for x in PERMIT_TYPES
                        ],
                        "riskLevels": [
                            {"value": x, "label": RISK_LABELS_FA.get(x, x)}
                            for x in RISK_LEVELS
                        ],
                        "energyTypes": [
                            {"value": x, "label": ENERGY_LABELS_FA.get(x, x)}
                            for x in ENERGY_TYPES
                        ],
                    },
                }
            )
        )

    def post(self, request):
        serializer = PermitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenantId = tenant()
        permit = createPermit(
            tenantId,
            permitType=data["permitType"],
            title=data["title"],
            actor=actor(),
            description=data.get("description", ""),
            riskLevel=data.get("riskLevel", "medium"),
            deviceId=data.get("deviceId"),
            workOrderId=data.get("workOrderId"),
            locationId=data.get("locationId"),
            locationName=data.get("locationName", ""),
            performerName=data.get("performerName", ""),
            contractorName=data.get("contractorName", ""),
            personnelCount=data.get("personnelCount", 1),
            validFrom=data.get("validFrom"),
            validTo=data.get("validTo"),
            extraPrecautions=data.get("extraPrecautions"),
        )
        return Response(
            successEnvelope(permitDetail(tenantId, permit)), status=status.HTTP_201_CREATED
        )


class PermitDetailView(Base):
    def get(self, request, permitId):
        tenantId = tenant()
        return Response(successEnvelope(permitDetail(tenantId, loadPermit(tenantId, permitId))))


class PermitActionView(Base):
    """One endpoint for the lifecycle, dispatched on the URL verb.

    Each branch is a distinct safety decision and the service enforces it;
    this is only routing.
    """

    def post(self, request, permitId, action):
        tenantId = tenant()
        who = actor()
        reason = str(request.data.get("reason", "")).strip()
        note = str(request.data.get("note", "")).strip()

        if action == "submit":
            permit = submitPermit(tenantId, permitId, actor=who)
        elif action == "approve":
            permit = approvePermit(tenantId, permitId, actor=who, note=note)
        elif action == "reject":
            permit = rejectPermit(tenantId, permitId, actor=who, reason=reason)
        elif action == "activate":
            permit = activatePermit(tenantId, permitId, actor=who)
        elif action == "suspend":
            permit = suspendPermit(tenantId, permitId, actor=who, reason=reason)
        elif action == "resume":
            permit = resumePermit(tenantId, permitId, actor=who)
        elif action == "complete":
            permit = completePermit(tenantId, permitId, actor=who, note=note)
        elif action == "close":
            permit = closePermit(tenantId, permitId, actor=who, note=note)
        elif action == "cancel":
            permit = cancelPermit(tenantId, permitId, actor=who, reason=reason)
        else:
            raise serializers.ValidationError({"action": "عملیات نامعتبر است."})

        return Response(successEnvelope(permitDetail(tenantId, permit)))


class PermitPrecautionView(Base):
    def post(self, request, permitId, precautionId):
        tenantId = tenant()
        confirmPrecaution(
            tenantId,
            permitId,
            precautionId,
            actor=actor(),
            note=str(request.data.get("note", "")),
        )
        return Response(successEnvelope(permitDetail(tenantId, loadPermit(tenantId, permitId))))


class PermitIsolationListView(Base):
    def post(self, request, permitId):
        tenantId = tenant()
        permit = loadPermit(tenantId, permitId)
        if permit.status not in ("draft", "submitted"):
            raise PermitRuleViolation(
                "permit.isolation.registerLocked",
                "پس از صدور مجوز نمی‌توان نقطه جداسازی جدید اضافه کرد؛ "
                "در صورت نیاز، مجوز جدید صادر کنید.",
            )
        serializer = IsolationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        createIsolationRow(
            tenantId=tenantId, permitId=permitId, now=timezone.now(), **serializer.validated_data
        )
        return Response(
            successEnvelope(permitDetail(tenantId, permit)), status=status.HTTP_201_CREATED
        )


class PermitIsolationActionView(Base):
    def post(self, request, permitId, isolationId, action):
        tenantId = tenant()
        who = actor()
        if action == "apply":
            applyIsolation(tenantId, permitId, isolationId, actor=who)
        elif action == "verify":
            verifyIsolation(tenantId, permitId, isolationId, actor=who)
        elif action == "remove":
            removeIsolation(tenantId, permitId, isolationId, actor=who)
        else:
            raise serializers.ValidationError({"action": "عملیات نامعتبر است."})
        return Response(successEnvelope(permitDetail(tenantId, loadPermit(tenantId, permitId))))


class PermitExpiryScanView(Base):
    """Preview of what is running out of time.

    Read-only here. The write path is the ``scanPermitExpiry`` command on a
    schedule, so a casual page refresh can never expire a permit.
    """

    def get(self, request):
        return Response(successEnvelope(scanPermitExpiry(tenant(), apply=False)))

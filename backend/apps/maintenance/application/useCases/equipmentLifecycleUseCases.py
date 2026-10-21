"""Use cases for life-cycle evidence and repair-scope suggestions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.maintenance.application.dto.equipmentLifecycleDtos import (
    DeviceLifecycleAnalysisDto,
    RepairScopeSuggestionDto,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.services.equipmentLifecycle import (
    EquipmentLifecycleSnapshot,
    LifecyclePartUse,
    REPAIR_SCOPES,
    RepairScopeSuggestion,
    analyzeEquipmentLifecycle,
    suggestRepairScope,
)
from apps.sharedKernel.application.messaging import Query
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError


@dataclass(frozen=True)
class GetDeviceLifecycleAnalysisQuery(Query):
    deviceId: str
    language: str = "fa"


@dataclass(frozen=True)
class SuggestRepairScopeCommand:
    workOrderId: str
    failureSymptom: str = ""
    rootCause: str = ""
    actionTaken: str = ""


class GetDeviceLifecycleAnalysisUseCase(UseCase):
    """Compute a tenant-scoped, explainable, advisory device analysis."""

    requiredAction = "maintenance.device.view"

    def __init__(
        self,
        *,
        deviceRepository,
        lifecycleRepository,
        aiAdvisor=None,
        **kwargs,
    ) -> None:  # noqa: ANN001
        super().__init__(**kwargs)
        self.deviceRepository = deviceRepository
        self.lifecycleRepository = lifecycleRepository
        self.aiAdvisor = aiAdvisor

    def validateCommand(self, query: GetDeviceLifecycleAnalysisQuery) -> None:
        try:
            uuid.UUID(str(query.deviceId))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationFailedError(
                "Device id must be a UUID.", fieldErrors={"deviceId": "invalid"}
            ) from error

    def perform(self, query: GetDeviceLifecycleAnalysisQuery) -> DeviceLifecycleAnalysisDto:
        tenantId = resolveTenantId("")
        deviceId = uuid.UUID(query.deviceId)
        if self.deviceRepository.getById(tenantId, deviceId) is None:
            raise EntityNotFoundError("Device")
        now = self.clock.nowUtc()
        snapshot: EquipmentLifecycleSnapshot = self.lifecycleRepository.getSnapshot(
            tenantId, deviceId, now
        )
        result = analyzeEquipmentLifecycle(snapshot, asOf=now, deviceId=str(deviceId))
        analysisMethod = str(result["analysisMethod"])
        aiAdvisory = None
        if self.aiAdvisor is not None:
            try:
                candidate = self.aiAdvisor.advise(
                    tenantId=tenantId,
                    language=query.language,
                    analysis=result,
                )
            except Exception:
                candidate = None
            if isinstance(candidate, dict):
                rawSummary = candidate.get("summary")
                rawRecommendations = candidate.get("recommendations", ())
                recommendations = [
                    item.strip()[:400]
                    for item in tuple(rawRecommendations or ())[:3]
                    if isinstance(item, str) and item.strip()
                ] if isinstance(rawRecommendations, (list, tuple)) else []
                if isinstance(rawSummary, str) and rawSummary.strip():
                    aiAdvisory = {
                        "summary": rawSummary.strip()[:1200],
                        "recommendations": recommendations,
                    }
                    analysisMethod = "provider-assisted-advisory-v1"
        return DeviceLifecycleAnalysisDto(
            deviceId=str(result["deviceId"]),
            generatedAt=str(result["generatedAt"]),
            advisoryOnly=bool(result["advisoryOnly"]),
            analysisMethod=analysisMethod,
            condition=str(result["condition"]),
            confidence=str(result["confidence"]),
            confidenceReason=str(result["confidenceReason"]),
            summary=str(result["summary"]),
            events=dict(result["events"]),
            reliability=dict(result["reliability"]),
            performance=dict(result["performance"]),
            lifeEstimate=dict(result["lifeEstimate"]),
            partLifeEstimates=list(result["partLifeEstimates"]),
            indicators=list(result["indicators"]),
            limitations=list(result["limitations"]),
            aiAdvisory=aiAdvisory,
        )


class SuggestRepairScopeUseCase(UseCase):
    """Suggest a repair scope from the work order's evidence, never persist it."""

    requiredAction = "maintenance.workorder.update"

    def __init__(
        self,
        *,
        workOrderRepository,
        sparePartRepository,
        aiAdvisor=None,
        **kwargs,
    ) -> None:  # noqa: ANN001
        super().__init__(**kwargs)
        self.workOrderRepository = workOrderRepository
        self.sparePartRepository = sparePartRepository
        self.aiAdvisor = aiAdvisor

    def validateCommand(self, command: SuggestRepairScopeCommand) -> None:
        try:
            uuid.UUID(str(command.workOrderId))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationFailedError(
                "Work-order id must be a UUID.", fieldErrors={"workOrderId": "invalid"}
            ) from error
        for fieldName, value in (
            ("failureSymptom", command.failureSymptom),
            ("rootCause", command.rootCause),
            ("actionTaken", command.actionTaken),
        ):
            if len(str(value or "")) > 6000:
                raise ValidationFailedError(
                    "Repair description is too long.", fieldErrors={fieldName: "maxLength"}
                )

    def perform(self, command: SuggestRepairScopeCommand) -> RepairScopeSuggestionDto:
        tenantId = resolveTenantId("")
        workOrderId = uuid.UUID(command.workOrderId)
        order = self.workOrderRepository.getById(tenantId, workOrderId)
        if order is None:
            raise EntityNotFoundError("WorkOrder", str(workOrderId))
        if str(order.orderType) != "corrective":
            return RepairScopeSuggestionDto(
                suggestedScope="unclassified",
                confidence="low",
                reasons=["پیشنهاد شدت تعمیر فقط برای دستورکار اصلاحی کاربرد دارد."],
                requiresHumanConfirmation=True,
                analysisMethod="explainable-rule-fallback",
            )

        usages = self.sparePartRepository.listUsage(tenantId, workOrderId)
        parts = tuple(
            LifecyclePartUse(
                workOrderId=str(usage.workOrderId),
                partCode=usage.partCode,
                partName=usage.partName,
                quantity=usage.quantity,
                lifecycleImpact=usage.lifecycleImpact,
            )
            for usage in usages
        )
        failureSymptom = command.failureSymptom or order.failureSymptom
        rootCause = command.rootCause or order.rootCause
        actionTaken = command.actionTaken or order.actionTaken
        suggestion = suggestRepairScope(
            title=order.title,
            description=order.description,
            failureSymptom=failureSymptom,
            rootCause=rootCause,
            actionTaken=actionTaken,
            partUses=parts,
        )
        analysisMethod = "explainable-rule-fallback"
        if self.aiAdvisor is not None and suggestion.confidence != "high":
            try:
                aiSuggestion = self.aiAdvisor.suggest(
                    tenantId=tenantId,
                    evidence={
                        "title": order.title,
                        "description": order.description,
                        "failureSymptom": failureSymptom,
                        "rootCause": rootCause,
                        "actionTaken": actionTaken,
                        "parts": [
                            {"name": use.partName or use.partCode, "lifecycleImpact": use.lifecycleImpact}
                            for use in parts
                        ],
                    },
                )
            except Exception:
                aiSuggestion = None
            if aiSuggestion is not None:
                scope = aiSuggestion.suggestedScope
                # Never let a model promote explicit small/consumable evidence
                # to major/overhaul. Nor may it upgrade a major-part hint to a
                # full overhaul without explicit overhaul evidence.
                contradictsMinorEvidence = (
                    suggestion.suggestedScope == "minor" and scope in {"major", "overhaul"}
                )
                unsupportedOverhaul = (
                    suggestion.suggestedScope == "major" and scope == "overhaul"
                )
                if (
                    scope in REPAIR_SCOPES
                    and not contradictsMinorEvidence
                    and not unsupportedOverhaul
                ):
                    suggestion = RepairScopeSuggestion(
                        suggestedScope=scope,
                        confidence="low" if aiSuggestion.confidence == "low" else "medium",
                        reasons=tuple(aiSuggestion.reasons)
                        + ("پیشنهاد مدلِ پیکربندی‌شده است؛ تأیید تکنسین لازم است.",),
                        requiresHumanConfirmation=True,
                    )
                    analysisMethod = "configured-provider"
        return RepairScopeSuggestionDto(
            suggestedScope=suggestion.suggestedScope,
            confidence=suggestion.confidence,
            reasons=list(suggestion.reasons),
            requiresHumanConfirmation=True,
            analysisMethod=analysisMethod,
        )

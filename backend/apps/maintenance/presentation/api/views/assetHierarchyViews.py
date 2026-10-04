"""Asset hierarchy API views (Phase 27) — HTTP orchestration only."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.assetHierarchyUseCases import (
    AssetAncestryQuery,
    AssetMovementsQuery,
    AssetTreeQuery,
    MoveAssetCommand,
    ReinstateAssetCommand,
    RetireAssetCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.registrySerializers import (
    MoveAssetSerializer,
    ReinstateAssetSerializer,
    RetireAssetSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class AssetHierarchyView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


def _isTrue(raw: str) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes"}


class AssetTreeView(AssetHierarchyView):
    """``GET assets/tree`` — the plant as one nested structure.

    ``?rootId=`` scopes the answer to one subtree; ``?includeRetired=true``
    keeps assets that have left the plant in the picture.
    """

    def get(self, request: Request) -> Response:
        payload = container.getAssetTreeUseCase().execute(
            AssetTreeQuery(
                rootLocationId=str(request.query_params.get("rootId", "") or ""),
                includeRetired=_isTrue(request.query_params.get("includeRetired", "")),
            )
        )
        return Response(successEnvelope(payload))


class AssetAncestryView(AssetHierarchyView):
    """``GET devices/<id>/ancestry`` — upstream assets, locations and children."""

    def get(self, request: Request, deviceId: str) -> Response:
        payload = container.getAssetAncestryUseCase().execute(
            AssetAncestryQuery(deviceId=str(deviceId))
        )
        return Response(successEnvelope(payload))


class AssetMovementListView(AssetHierarchyView):
    """``GET`` the transfer ledger of one asset, ``POST`` a new transfer."""

    def get(self, request: Request, deviceId: str) -> Response:
        rows = container.listAssetMovementsUseCase().execute(
            AssetMovementsQuery(deviceId=str(deviceId))
        )
        return Response(successEnvelope(rows))

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = MoveAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = container.moveAssetUseCase().execute(
            MoveAssetCommand(
                deviceId=str(deviceId),
                toLocationId=str(data["toLocationId"]),
                toParentDeviceId=str(data["toParentDeviceId"]),
                movedOn=str(data["movedOn"]),
                reason=str(data["reason"]),
                performedBy=str(data["performedBy"]),
                note=str(data["note"]),
                updateInstalledOn=bool(data["updateInstalledOn"]),
                clearLocation=bool(data["clearLocation"]),
                clearParent=bool(data["clearParent"]),
            )
        )
        return Response(successEnvelope(payload), status=201)


class AssetRetirementView(AssetHierarchyView):
    """``POST`` takes an asset out of service, ``DELETE`` puts it back."""

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = RetireAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = container.retireAssetUseCase().execute(
            RetireAssetCommand(
                deviceId=str(deviceId),
                retiredOn=str(data["retiredOn"]),
                reason=str(data["reason"]),
                retireChildren=bool(data["retireChildren"]),
            )
        )
        return Response(successEnvelope(payload))

    def delete(self, request: Request, deviceId: str) -> Response:
        # A DELETE body is awkward for browser clients (our ApiClient omits
        # one), so the status may arrive either way.
        payload = dict(request.data or {})
        if not payload.get("status"):
            payload["status"] = request.query_params.get("status", "") or "operational"
        serializer = ReinstateAssetSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        payload = container.reinstateAssetUseCase().execute(
            ReinstateAssetCommand(
                deviceId=str(deviceId),
                status=str(serializer.validated_data["status"] or "operational"),
            )
        )
        return Response(successEnvelope(payload))

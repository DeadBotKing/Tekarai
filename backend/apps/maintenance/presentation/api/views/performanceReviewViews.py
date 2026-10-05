"""Performance review API views (Phase 29) — HTTP orchestration only."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.performanceReviewUseCases import (
    ComputeCycleCommand,
    CycleQuery,
    DeleteScoreCommand,
    SaveCycleCommand,
    SaveRaterScoreCommand,
)
from apps.maintenance.infrastructure import container
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class PerformanceReviewBaseView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


def _weightMap(raw: object) -> dict:
    """Role weights from JSON, ignoring anything that is not a number.

    Validation of the role names themselves belongs to the use case; this only
    gets the shape right.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


class ReviewCycleListView(PerformanceReviewBaseView):
    """``GET|POST performance-reviews/cycles`` — list the rounds, or save one."""

    def get(self, request: Request) -> Response:
        payload = container.listReviewCyclesUseCase().execute(CycleQuery())
        return Response(successEnvelope(payload))

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveReviewCycleUseCase().execute(
            SaveCycleCommand(
                id=str(body.get("id", "") or ""),
                code=str(body.get("code", "") or ""),
                name=str(body.get("name", "") or ""),
                fromDate=str(body.get("fromDate", "") or ""),
                toDate=str(body.get("toDate", "") or ""),
                status=str(body.get("status", "") or "draft"),
                systemWeightPercent=int(body.get("systemWeightPercent", 30) or 0),
                roleWeights=_weightMap(body.get("roleWeights")),
                note=str(body.get("note", "") or ""),
            )
        )
        return Response(successEnvelope(payload))


class ReviewCycleDetailView(PerformanceReviewBaseView):
    """``DELETE performance-reviews/cycles/<id>`` — retire a round."""

    def delete(self, request: Request, cycleId: str) -> Response:
        payload = container.deleteReviewCycleUseCase().execute(CycleQuery(cycleId=str(cycleId)))
        return Response(successEnvelope(payload))


class RaterScoreView(PerformanceReviewBaseView):
    """``GET|POST performance-reviews/scores`` — the marks in one cycle."""

    def get(self, request: Request) -> Response:
        payload = container.listRaterScoresUseCase().execute(
            CycleQuery(cycleId=str(request.query_params.get("cycleId", "") or ""))
        )
        return Response(successEnvelope(payload))

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveRaterScoreUseCase().execute(
            SaveRaterScoreCommand(
                cycleId=str(body.get("cycleId", "") or ""),
                personnelId=str(body.get("personnelId", "") or ""),
                raterRole=str(body.get("raterRole", "") or ""),
                score=body.get("score", 0),
                raterName=str(body.get("raterName", "") or ""),
                note=str(body.get("note", "") or ""),
            )
        )
        return Response(successEnvelope(payload))


class RaterScoreDetailView(PerformanceReviewBaseView):
    """``DELETE performance-reviews/scores/<id>`` — withdraw a mark."""

    def delete(self, request: Request, scoreId: str) -> Response:
        payload = container.deleteRaterScoreUseCase().execute(
            DeleteScoreCommand(scoreId=str(scoreId))
        )
        return Response(successEnvelope(payload))


class ComputeReviewView(PerformanceReviewBaseView):
    """``POST performance-reviews/compute`` — merge opinion with record."""

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.computeReviewCycleUseCase().execute(
            ComputeCycleCommand(cycleId=str(body.get("cycleId", "") or ""))
        )
        return Response(successEnvelope(payload))


class ReviewResultsView(PerformanceReviewBaseView):
    """``GET performance-reviews/results`` — the ranked comparison read model."""

    def get(self, request: Request) -> Response:
        payload = container.getReviewResultsUseCase().execute(
            CycleQuery(cycleId=str(request.query_params.get("cycleId", "") or ""))
        )
        return Response(successEnvelope(payload))

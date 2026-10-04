"""Work calendar API views (Phase 28) — HTTP orchestration only."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.workCalendarUseCases import (
    CalendarQuery,
    CapacityPlanQuery,
    DeleteCommand,
    SaveCalendarCommand,
    SaveHolidayCommand,
    SaveShiftAssignmentCommand,
    SaveShiftCommand,
    WorkingDayQuery,
)
from apps.maintenance.infrastructure import container
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class WorkCalendarBaseView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


def _intTuple(raw: object) -> tuple[int, ...]:
    """Weekday list from JSON, tolerant of strings and CSV.

    The UI sends ``[4]``; a curl user sends ``"4,3"``. Both are reasonable and
    neither should 400.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts: list[object] = [part for part in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        return ()
    out: list[int] = []
    for part in parts:
        try:
            out.append(int(str(part).strip()))
        except (TypeError, ValueError):
            continue
    return tuple(out)


class WorkCalendarListView(WorkCalendarBaseView):
    """``GET|POST work-calendars`` — list every calendar, or save one."""

    def get(self, request: Request) -> Response:
        payload = container.listWorkCalendarsUseCase().execute(CalendarQuery())
        return Response(successEnvelope(payload))

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveWorkCalendarUseCase().execute(
            SaveCalendarCommand(
                id=str(body.get("id", "") or ""),
                code=str(body.get("code", "") or ""),
                name=str(body.get("name", "") or ""),
                locationId=str(body.get("locationId", "") or ""),
                timezone=str(body.get("timezone", "") or "Asia/Tehran"),
                weekendDays=_intTuple(body.get("weekendDays")),
                rollPolicy=str(body.get("rollPolicy", "") or "forward"),
                isDefault=bool(body.get("isDefault", False)),
                active=bool(body.get("active", True)),
                note=str(body.get("note", "") or ""),
            )
        )
        return Response(successEnvelope(payload), status=201)


class WorkCalendarDetailView(WorkCalendarBaseView):
    """``DELETE work-calendars/<uuid>`` — retire a calendar and its contents."""

    def delete(self, request: Request, calendarId: str) -> Response:
        payload = container.deleteCalendarEntryUseCase().execute(
            DeleteCommand(id=str(calendarId), kind="calendar")
        )
        return Response(successEnvelope(payload))


class CalendarHolidayView(WorkCalendarBaseView):
    """``GET|POST work-calendars/holidays`` — closures on one calendar."""

    def get(self, request: Request) -> Response:
        payload = container.listHolidaysUseCase().execute(
            CapacityPlanQuery(
                calendarId=str(request.query_params.get("calendarId", "") or ""),
                locationId=str(request.query_params.get("locationId", "") or ""),
                fromDate=str(request.query_params.get("fromDate", "") or ""),
                toDate=str(request.query_params.get("toDate", "") or ""),
            )
        )
        return Response(successEnvelope(payload))

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveHolidayUseCase().execute(
            SaveHolidayCommand(
                id=str(body.get("id", "") or ""),
                calendarId=str(body.get("calendarId", "") or ""),
                onDate=str(body.get("onDate", "") or ""),
                name=str(body.get("name", "") or ""),
                kind=str(body.get("kind", "") or "official"),
                recursAnnually=bool(body.get("recursAnnually", False)),
                jalaliMonth=int(body.get("jalaliMonth") or 0),
                jalaliDay=int(body.get("jalaliDay") or 0),
            )
        )
        return Response(successEnvelope(payload), status=201)


class CalendarHolidayDetailView(WorkCalendarBaseView):
    """``DELETE work-calendars/holidays/<uuid>``."""

    def delete(self, request: Request, holidayId: str) -> Response:
        payload = container.deleteCalendarEntryUseCase().execute(
            DeleteCommand(id=str(holidayId), kind="holiday")
        )
        return Response(successEnvelope(payload))


class WorkShiftView(WorkCalendarBaseView):
    """``POST work-calendars/shifts`` — create or update a shift window."""

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveShiftUseCase().execute(
            SaveShiftCommand(
                id=str(body.get("id", "") or ""),
                calendarId=str(body.get("calendarId", "") or ""),
                code=str(body.get("code", "") or ""),
                name=str(body.get("name", "") or ""),
                kind=str(body.get("kind", "") or "general"),
                startTime=str(body.get("startTime", "") or ""),
                endTime=str(body.get("endTime", "") or ""),
                weekdays=_intTuple(body.get("weekdays")),
                headcount=int(body.get("headcount") or 0),
                active=bool(body.get("active", True)),
            )
        )
        return Response(successEnvelope(payload), status=201)


class WorkShiftDetailView(WorkCalendarBaseView):
    """``DELETE work-calendars/shifts/<uuid>``."""

    def delete(self, request: Request, shiftId: str) -> Response:
        payload = container.deleteCalendarEntryUseCase().execute(
            DeleteCommand(id=str(shiftId), kind="shift")
        )
        return Response(successEnvelope(payload))


class ShiftAssignmentView(WorkCalendarBaseView):
    """``POST work-calendars/assignments`` — roster a technician."""

    def post(self, request: Request) -> Response:
        body = request.data or {}
        payload = container.saveShiftAssignmentUseCase().execute(
            SaveShiftAssignmentCommand(
                shiftId=str(body.get("shiftId", "") or ""),
                personnelId=str(body.get("personnelId", "") or ""),
                fromDate=str(body.get("fromDate", "") or ""),
                toDate=str(body.get("toDate", "") or ""),
            )
        )
        return Response(successEnvelope(payload), status=201)


class ShiftAssignmentDetailView(WorkCalendarBaseView):
    """``DELETE work-calendars/assignments/<uuid>``."""

    def delete(self, request: Request, assignmentId: str) -> Response:
        payload = container.deleteCalendarEntryUseCase().execute(
            DeleteCommand(id=str(assignmentId), kind="assignment")
        )
        return Response(successEnvelope(payload))


class CapacityPlanView(WorkCalendarBaseView):
    """``GET work-calendars/capacity`` — demand vs capacity, day by day."""

    def get(self, request: Request) -> Response:
        payload = container.getCapacityPlanUseCase().execute(
            CapacityPlanQuery(
                calendarId=str(request.query_params.get("calendarId", "") or ""),
                locationId=str(request.query_params.get("locationId", "") or ""),
                fromDate=str(request.query_params.get("fromDate", "") or ""),
                toDate=str(request.query_params.get("toDate", "") or ""),
            )
        )
        return Response(successEnvelope(payload))


class WorkingDayView(WorkCalendarBaseView):
    """``GET work-calendars/working-day`` — is this date workable, and if not, when?"""

    def get(self, request: Request) -> Response:
        payload = container.getWorkingDayUseCase().execute(
            WorkingDayQuery(
                onDate=str(request.query_params.get("onDate", "") or ""),
                calendarId=str(request.query_params.get("calendarId", "") or ""),
                locationId=str(request.query_params.get("locationId", "") or ""),
                deviceId=str(request.query_params.get("deviceId", "") or ""),
                addWorkingDays=int(request.query_params.get("addWorkingDays") or 0),
            )
        )
        return Response(successEnvelope(payload))

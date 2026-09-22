"""OpenAPI endpoint registration for the maintenance context (Phase 21)."""

from __future__ import annotations

from apps.maintenance.presentation.api.views.deviceViews import MAINTENANCE_ERRORS
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint


def registerMaintenanceEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/maintenance/devices",
            summary="List maintainable devices.",
            permission="maintenance.device.list",
            errorCodes=MAINTENANCE_ERRORS,
            paginated=True,
            filterable=("status",),
            sortable=("createdAt", "code", "name", "status"),
            searchable=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/devices",
            summary="Register a device (idempotent).",
            permission="maintenance.device.manage",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"code": "PUMP-01", "name": "Coolant pump", "pmIntervalDays": 30},
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/maintenance/devices/{deviceId}",
            summary="Device detail with PM schedule.",
            permission="maintenance.device.view",
            errorCodes=MAINTENANCE_ERRORS,
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/maintenance/devices/{deviceId}",
            summary="Update device details and PM interval.",
            permission="maintenance.device.manage",
            errorCodes=MAINTENANCE_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/devices/{deviceId}/status",
            summary="Change device status (idempotent).",
            permission="maintenance.device.manage",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"target": "underMaintenance"},
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/devices/{deviceId}/pm",
            summary="Record a completed preventive-maintenance cycle.",
            permission="maintenance.device.manage",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"performedOn": "2026-09-22"},
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/maintenance/devices/due-pm",
            summary="List devices whose preventive maintenance is due or overdue.",
            permission="maintenance.device.list",
            errorCodes=MAINTENANCE_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/maintenance/work-orders",
            summary="List work orders (maintenance requests).",
            permission="maintenance.workorder.list",
            errorCodes=MAINTENANCE_ERRORS,
            paginated=True,
            filterable=("status", "orderType", "priority", "deviceId"),
            sortable=("createdAt", "title", "status", "priority"),
            searchable=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/work-orders",
            summary="Submit a work order against a device (idempotent).",
            permission="maintenance.workorder.create",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"deviceId": "…", "title": "Bearing noise", "priority": "high"},
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/maintenance/work-orders/{workOrderId}",
            summary="Work order detail.",
            permission="maintenance.workorder.view",
            errorCodes=MAINTENANCE_ERRORS,
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/maintenance/work-orders/{workOrderId}",
            summary="Update a work order.",
            permission="maintenance.workorder.update",
            errorCodes=MAINTENANCE_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/work-orders/{workOrderId}/assign",
            summary="Assign a technician (idempotent).",
            permission="maintenance.workorder.assign",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"assignedToName": "Reza Ahmadi"},
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/maintenance/work-orders/{workOrderId}/status",
            summary="Transition a work order status (idempotent).",
            permission="maintenance.workorder.update",
            errorCodes=MAINTENANCE_ERRORS,
            idempotent=True,
            requestExample={"target": "inProgress"},
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)


registerMaintenanceEndpoints()

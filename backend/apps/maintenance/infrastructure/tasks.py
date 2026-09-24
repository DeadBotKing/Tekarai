"""Scheduled maintenance jobs.

Celery Beat invokes these entry points without a user request. The domain use
cases remain the single place where PM eligibility, work-order construction,
routing, audit logging, and duplicate prevention are enforced.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="maintenance.generatePmWorkOrders")
def generateDuePmWorkOrders() -> dict[str, object]:
    """Create preventive work orders for every tenant's due PM devices."""
    from apps.maintenance.application.commands.maintenanceCommands import (
        GeneratePmWorkOrdersCommand,
    )
    from apps.maintenance.infrastructure import container
    from apps.maintenance.infrastructure.models import DeviceModel

    tenantIds = list(
        DeviceModel.objects.filter(deletedAt__isnull=True)
        .values_list("tenantId", flat=True)
        .distinct()
    )
    tenantResults: list[dict[str, object]] = []
    totalCreated = 0
    for tenantId in tenantIds:
        useCase = container.generatePmWorkOrdersUseCase()
        # Trusted system job: retain permission checks on the public endpoint.
        useCase.requiredAction = ""
        result = useCase.execute(GeneratePmWorkOrdersCommand(tenantId=str(tenantId)))
        totalCreated += result.totalCount
        tenantResults.append(
            {
                "tenantId": str(tenantId),
                "createdCount": result.totalCount,
                "workOrderIds": [item.id for item in result.items],
            }
        )
    return {
        "tenantCount": len(tenantIds),
        "createdCount": totalCreated,
        "tenants": tenantResults,
    }


__all__ = ["generateDuePmWorkOrders"]

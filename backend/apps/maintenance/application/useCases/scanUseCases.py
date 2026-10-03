"""Resolve a scanned QR / barcode to the thing the technician is standing at.

The client *could* parse deep links itself — and it does, as a fast path —
but resolution has to happen on the server too, for three reasons a purely
client-side parser cannot cover:

* a 1D barcode carries only ``PUMP-204``; mapping that to an id needs the
  tenant's data;
* a vendor's serial-number sticker is a legitimate label, and only the
  database knows which device wears it;
* the answer must be tenant-scoped. A code from another plant must 404, not
  silently open someone else's equipment.

The response carries the ``route`` the UI should navigate to, so adding a new
scannable entity later does not require shipping a new mobile build.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    ScanCodeUnreadableError,
    ScanTargetNotFoundError,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    ScanResolutionRepository,
)
from apps.maintenance.domain.services.scanCodeRules import parseScan
from apps.sharedKernel.application.messaging import Query
from apps.sharedKernel.application.useCase import UseCase


@dataclass(frozen=True)
class ResolveScanQuery(Query):
    code: str
    symbology: str = "manual"


@dataclass(frozen=True)
class ScanResultDto:
    kind: str
    id: str
    code: str
    title: str
    subtitle: str
    route: str
    status: str
    symbology: str
    scannedText: str


class ResolveScanUseCase(UseCase):
    """``GET /maintenance/scan?code=…`` — one code in, one target out."""

    requiredAction = "maintenance.device.view"

    def __init__(self, scanRepository: ScanResolutionRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.scanRepository = scanRepository

    def perform(self, query: ResolveScanQuery) -> ScanResultDto:
        intent = parseScan(query.code)
        if intent.isEmpty:
            raise ScanCodeUnreadableError(
                "This code is not readable as a Tekarai label.",
                fieldErrors={"code": "unreadable"},
            )
        tenantId = resolveTenantId("")
        target = self.scanRepository.resolve(tenantId, intent)
        if target is None:
            raise ScanTargetNotFoundError(
                "No equipment, work order, part or location carries this code."
            )
        return ScanResultDto(
            kind=target.kind,
            id=target.id,
            code=target.code,
            title=target.title,
            subtitle=target.subtitle,
            route=target.route,
            status=target.status,
            symbology=(query.symbology or "manual").strip()[:20],
            scannedText=intent.raw[:512],
        )

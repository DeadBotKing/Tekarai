from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command, Query


@dataclass(frozen=True)
class CreateSparePartCommand(Command):
    code: str
    name: str
    unit: str = "عدد"
    quantityOnHand: str = "0"
    minimumStock: str = "0"


@dataclass(frozen=True)
class UpdateSparePartCommand(Command):
    partId: str
    name: str
    unit: str = "عدد"
    quantityOnHand: str = "0"
    minimumStock: str = "0"


@dataclass(frozen=True)
class ConsumeSparePartCommand(Command):
    workOrderId: str
    partId: str
    quantity: str
    note: str = ""


@dataclass(frozen=True)
class ListSparePartsQuery(Query):
    search: str = ""


@dataclass(frozen=True)
class ListWorkOrderPartUsageQuery(Query):
    workOrderId: str

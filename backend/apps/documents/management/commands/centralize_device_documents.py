"""Idempotent metadata transfer; original rows and file bytes are retained."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.documents.infrastructure.models import DocumentModel
from apps.maintenance.infrastructure.models import DeviceModel, MaintenanceAttachmentModel


class Command(BaseCommand):
    help = "Check/transfer active device attachments to the central library without moving file bytes."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Read-only preflight; no records are changed.")

    def handle(self, *args, **options):
        rows = list(MaintenanceAttachmentModel.objects.filter(targetType="device", deletedAt__isnull=True).order_by("id"))
        # Check every source before making any changes, including missing/truncated files.
        for row in rows:
            if not DeviceModel.objects.filter(id=row.targetId, tenantId=row.tenantId).exists():
                raise CommandError(f"Missing/cross-tenant device for attachment {row.id}; no transfer performed.")
            if not row.file.name or not row.file.storage.exists(row.file.name) or row.file.storage.size(row.file.name) != row.sizeBytes:
                raise CommandError(f"Missing/truncated file for attachment {row.id}; no transfer performed.")
            existing = DocumentModel.objects.filter(id=row.id).first()
            if existing and (not existing.legacyDeviceDocument or existing.tenantId != row.tenantId or existing.file.name != row.file.name):
                raise CommandError(f"Conflicting central document id {row.id}; no transfer performed.")
        if options["check"]:
            self.stdout.write(f"DEVICE_DOCUMENTS_PREFLIGHT_OK sources={len(rows)}")
            return
        created = 0
        with transaction.atomic():
            for row in rows:
                document, isNew = DocumentModel.objects.get_or_create(id=row.id, defaults={
                    "tenantId": row.tenantId, "name": row.originalName,
                    "contentType": row.mimeType, "sizeBytes": row.sizeBytes,
                    "category": {"manual": "دفترچه راهنما", "failurePhoto": "عکس خرابی", "invoice": "فاکتور", "other": "سایر"}.get(row.category, row.category),
                    "description": "انتقال از مدارک دستگاه", "file": row.file.name,
                    "uploadedByIdentifier": "", "uploadedAt": row.uploadedAt,
                    "legacyDeviceDocument": True,
                })
                if isNew:
                    document.relatedDevices.add(row.targetId)
                    created += 1
                # A rerun never resurrects deleted documents or overwrites edited links.
                if document.tenantId != row.tenantId or document.file.name != row.file.name:
                    raise CommandError("Transfer verification failed; transaction rolled back.")
        self.stdout.write(f"DEVICE_DOCUMENTS_CENTRALIZED sources={len(rows)} created={created} alreadyPresent={len(rows)-created}")
        self.stdout.write("Original file bytes and attachment records were retained. Work-order attachments were not changed.")

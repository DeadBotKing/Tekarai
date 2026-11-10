"""Tenant-bound, read-only evidence. Authorization precedes reading text or inference."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import re
import uuid
from django.utils import timezone
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import PermissionDeniedError
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from apps.documents.infrastructure.models import DocumentModel
from apps.maintenance.infrastructure.models import DeviceModel
from apps.projects.infrastructure.models import ProjectModel
from apps.tasks.infrastructure.models import TaskModel
from .extraction import extract, MAX_BYTES

SCOPES = {'maintenance', 'documents', 'projects'}
LABELS = {'maintenance': 'تجهیزات و تعمیرات', 'documents': 'مستندات', 'projects': 'پروژه‌ها و کارها'}

def normalize(text):
    return text.casefold().replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')

def clean(text):
    value = str(text)
    value = re.sub(r'(?i)(?:bearer\s+\S+|sk-[a-z0-9_-]{12,}|(?:password|api[_-]?key|secret)\s*[:=]\s*\S+)', '[حذف اطلاعات حساس]', value)
    return ''.join(c for c in value if c in '\n\t' or not (ord(c) < 32 or c in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'))[:12000]

@dataclass
class Source:
    kind: str
    record: str
    title: str
    text: str
    href: str
    version: str
    page: int | None = None
    tables: list = field(default_factory=list)
    documentFormat: str = ''

class Reader:
    def __init__(self):
        context = currentContext()
        try:
            self.actor = uuid.UUID(context.actorId)
            self.tenant = uuid.UUID(context.actorTenantId)
        except (ValueError, TypeError, AttributeError):
            raise PermissionDeniedError() from None
        from apps.tenancy.infrastructure.services.organizationWorkspace import profile
        if 'assistant' not in profile(self.tenant)['enabledModules']:
            raise PermissionDeniedError('دستیار این سازمان هنوز فعال نشده است.')
        self.gate = sharedKernelProvider('permissionGate')()
        self.warnings = ['شواهد نمونهٔ محدود از رکوردهای مجاز است، نه گزارش جامع کل سازمان.']
        self.sources: list[Source] = []

    def has(self, action, record=None):
        return self.gate.hasPermission(self.actor, action, tenantId=self.tenant, targetTenantId=self.tenant, targetId=uuid.UUID(str(record)) if record else None)

    def capabilities(self):
        return {
            'maintenance': (self.has('maintenance.device.list') and self.has('maintenance.device.view')) or (self.has('maintenance.workorder.list') and self.has('maintenance.workorder.view')),
            'documents': self.has('maintenance.document.view'),
            'projects': (self.has('project.list') and self.has('project.view')) or (self.has('task.list') and self.has('task.view')),
        }

    def document_allowed(self, row):
        return self.has('maintenance.document.view', row.id) and (not row.legacyDeviceDocument or self.has('maintenance.attachment.view', row.id))

    def queryset(self, model):
        return model.objects.filter(tenantId=self.tenant, deletedAt__isnull=True)

    def choices(self):
        cap = self.capabilities()
        result = {'scopes': [key for key, yes in cap.items() if yes], 'devices': [], 'projects': [], 'documents': []}
        for kind, model, list_action, view_action, title in [
            ('devices', DeviceModel, 'maintenance.device.list', 'maintenance.device.view', 'name'),
            ('projects', ProjectModel, 'project.list', 'project.view', 'name'),
        ]:
            if self.has(list_action) and self.has(view_action):
                result[kind] = [{'id': str(row.id), 'label': clean(getattr(row, title))[:160]} for row in self.queryset(model).order_by('-createdAt', 'id')[:30] if self.has(view_action, row.id)]
        if cap['documents']:
            result['documents'] = [{'id': str(row.id), 'label': clean(row.name)[:160]} for row in self.queryset(DocumentModel).order_by('-uploadedAt', 'id')[:30] if self.document_allowed(row) and self.safe_name(row.name)]
        return result

    @staticmethod
    def safe_name(name):
        return not re.search(r'(?i)(\.env|\.pem$|\.key$|credential|private.?key|password|secret|رمز.?عبور|گذرواژه)', name)

    def add(self, kind, row, fields, href, title=None):
        values = {key: clean(getattr(row, key, ''))[:1000] for key in fields}
        raw = json.dumps(values, ensure_ascii=False, sort_keys=True)
        self.sources.append(Source(kind, str(row.id), clean(title or getattr(row, 'name', getattr(row, 'title', ''))), raw, href, hashlib.sha256(raw.encode()).hexdigest()))

    def collect(self, scope, *, deviceId='', projectId='', documentIds=(), question=''):
        cap = self.capabilities()
        # Explicit documents mean document-grounded evidence, never other records.
        scopes = {'documents'} if documentIds else ({key for key, yes in cap.items() if yes} if scope == 'all' else {scope})
        if not scopes or any(not cap.get(s, False) for s in scopes):
            raise PermissionDeniedError('این بخش فعال نیست یا دسترسی لازم را ندارید.')
        if deviceId:
            row = self.queryset(DeviceModel).filter(id=deviceId).first()
            if row is None or not self.has('maintenance.device.list') or not self.has('maintenance.device.view', row.id):
                raise PermissionDeniedError('منبع انتخاب‌شده در دسترس نیست.')
        if projectId:
            row = self.queryset(ProjectModel).filter(id=projectId).first()
            if row is None or not self.has('project.list') or not self.has('project.view', row.id):
                raise PermissionDeniedError('منبع انتخاب‌شده در دسترس نیست.')
        if 'maintenance' in scopes:
            if self.has('maintenance.device.list') and self.has('maintenance.device.view'):
                rows = self.queryset(DeviceModel)
                if deviceId: rows = rows.filter(id=deviceId)
                for row in rows.order_by('-createdAt', 'id')[:30]:
                    if self.has('maintenance.device.view', row.id):
                        self.add('device', row, ['code', 'name', 'status', 'criticality', 'manufacturer', 'modelNumber', 'pmIntervalDays', 'lastPmDate', 'notes'], f'/app/maintenance/devices/{row.id}/profile')
            if self.has('maintenance.workorder.list') and self.has('maintenance.workorder.view'):
                from apps.maintenance.infrastructure import container
                from apps.maintenance.application.queries.maintenanceQueries import ListWorkOrdersQuery
                page = container.listWorkOrdersUseCase().execute(ListWorkOrdersQuery(actorUserId=str(self.actor), deviceId=deviceId, pageSize=30))
                for row in page.items:
                    if self.has('maintenance.workorder.view', row.id):
                        self.add('workorder', row, ['title', 'status', 'priority', 'description', 'failureSymptom', 'rootCause', 'actionTaken', 'closedAt', 'overdue', 'slaDueAt'], '/app/maintenance/work-orders?search=' + str(row.id))
        if 'projects' in scopes:
            if self.has('project.list') and self.has('project.view'):
                rows = self.queryset(ProjectModel)
                if projectId: rows = rows.filter(id=projectId)
                for row in rows.order_by('-createdAt', 'id')[:30]:
                    if self.has('project.view', row.id):
                        self.add('project', row, ['code', 'name', 'status', 'progress', 'health', 'dueDate', 'description'], '/app/projects')
            if self.has('task.list') and self.has('task.view'):
                rows = self.queryset(TaskModel)
                if projectId: rows = rows.filter(projectId=projectId)
                for row in rows.order_by('-createdAt', 'id')[:30]:
                    if self.has('task.view', row.id):
                        self.add('task', row, ['title', 'status', 'priority', 'dueDate', 'estimate'], '/app/tasks')
        if 'documents' in scopes:
            rows = self.queryset(DocumentModel)
            if documentIds: rows = rows.filter(id__in=documentIds)
            if deviceId: rows = rows.filter(relatedDevices__id=deviceId)
            candidates = [row for row in rows.order_by('-uploadedAt', 'id')[:30] if self.document_allowed(row) and self.safe_name(row.name)]
            if documentIds and {str(r.id) for r in candidates} != set(map(str, documentIds)):
                raise PermissionDeniedError('منبع انتخاب‌شده در دسترس نیست.')
            candidates.sort(key=lambda r: self.score(question, r.name + ' ' + r.description), reverse=True)
            for row in candidates[:2]:
                if row.sizeBytes > MAX_BYTES:
                    if documentIds:
                        raise ValidationFailedError('سند انتخاب‌شده بزرگ‌تر از ۴ مگابایت است؛ پاسخی از منابع دیگر تولید نشد.')
                    self.warnings.append('سندی بزرگ‌تر از ۴ مگابایت کنار گذاشته شد.'); continue
                from apps.documents.infrastructure import container
                from apps.documents.application.commands import DownloadDocumentQuery
                result = container.downloadDocumentUseCase().execute(DownloadDocumentQuery(documentId=str(row.id)))
                try:
                    data = result.stream.read(MAX_BYTES + 1)
                finally:
                    result.stream.close()
                segments = extract(data, row.name)
                version = hashlib.sha256(data).hexdigest()
                if not segments or not any(s['text'].strip() for s in segments):
                    if documentIds:
                        raise ValidationFailedError('متن سند انتخاب‌شده قابل استخراج نبود؛ پاسخی از منابع دیگر تولید نشد.')
                    self.warnings.append('سندی متن قابل استخراج نداشت؛ PDF تصویری، فایل رمزدار یا قالب نامعتبر نیاز به بررسی دارد.'); continue
                self.warnings.append('استخراج سند محدود به ۱۵ صفحهٔ نخست و ۳۲هزار نویسه است؛ OCR انجام نمی‌شود.')
                for segment in segments:
                    text = clean(segment['text'])
                    for offset in range(0, len(text), 600):
                        self.sources.append(Source('document', str(row.id), clean(row.name), text[offset:offset + 750], '/app/documents', version, segment.get('page'), [{**table,'headers':[clean(c) for c in table['headers']],'rows':[[clean(c) for c in cells] for cells in table['rows']]} for table in segment.get('tables',[])], 'pdf' if row.name.lower().endswith('.pdf') else ''))
        return self.sources

    @staticmethod
    def score(question, text):
        words = set(re.findall(r'[\w\u0600-\u06ff]{2,}', normalize(question))) - {'است', 'برای', 'کدام', 'چیست', 'های', 'بگو', 'درباره', 'این', 'را'}
        haystack = normalize(text)
        return sum(1 for word in words if word in haystack)

    def evidence(self, question):
        # Sample at most three excerpts. Prompt bytes, not character counts,
        # bound memory/context; IDs are assigned only after final selection.
        from .runtime import SYSTEM
        overhead = len(SYSTEM.encode()) + len(json.dumps({'question': question, 'evidence': []}, ensure_ascii=False, separators=(',', ':')).encode())
        budget = max(0, 3050 - overhead)
        ranked = sorted(self.sources, key=lambda s: self.score(question, s.title + ' ' + s.text), reverse=True)
        selected, evidence = [], []
        for row in ranked:
            if len(selected) >= 3 or budget < 180:
                break
            if any(s.kind == row.kind and s.record == row.record and s.page == row.page for s in selected):
                continue
            snippet = (row.title[:70] + '\n' + row.text).encode()[:min(700, budget - 65)].decode('utf-8', errors='ignore')
            item = {'id': 'S' + str(len(selected) + 1), 'text': snippet}
            cost = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) + 2
            if cost > budget:
                continue
            budget -= cost; evidence.append(item); selected.append(row)
        return evidence, selected

    def revalidate(self, selected):
        from apps.tenancy.infrastructure.services.organizationWorkspace import profile
        if 'assistant' not in profile(self.tenant)['enabledModules']:
            raise PermissionDeniedError('دستیار این سازمان غیرفعال شده است.')
        actions = {'device': 'maintenance.device.view', 'workorder': 'maintenance.workorder.view', 'project': 'project.view', 'task': 'task.view', 'document': 'maintenance.document.view'}
        models = {'device': DeviceModel, 'project': ProjectModel, 'task': TaskModel, 'document': DocumentModel}
        for source in selected:
            lists = {'device':'maintenance.device.list','workorder':'maintenance.workorder.list','project':'project.list','task':'task.list'}
            if not self.has(actions[source.kind], source.record) or (source.kind in lists and not self.has(lists[source.kind])):
                raise PermissionDeniedError('دسترسی تغییر کرده است؛ پاسخ نمایش داده نشد.')
            if source.kind in models:
                row = self.queryset(models[source.kind]).filter(id=source.record).first()
                if row is None or (source.kind == 'document' and not self.document_allowed(row)):
                    raise PermissionDeniedError('منبع تغییر کرده یا دیگر در دسترس نیست.')
            else:
                from apps.maintenance.infrastructure import container
                from apps.maintenance.application.queries.maintenanceQueries import ListWorkOrdersQuery
                rows = container.listWorkOrdersUseCase().execute(ListWorkOrdersQuery(actorUserId=str(self.actor), pageSize=200)).items
                row = next((r for r in rows if str(r.id) == source.record), None)
                if row is None:
                    raise PermissionDeniedError('منبع دیگر در محدودهٔ دسترسی نیست.')
            if source.kind == 'document':
                from apps.documents.infrastructure import container
                from apps.documents.application.commands import DownloadDocumentQuery
                result = container.downloadDocumentUseCase().execute(DownloadDocumentQuery(documentId=source.record))
                try:
                    data = result.stream.read(MAX_BYTES + 1)
                finally:
                    result.stream.close()
                version = hashlib.sha256(data).hexdigest()
            else:
                fields = json.loads(source.text)
                raw = json.dumps({key: clean(getattr(row, key, ''))[:1000] for key in fields}, ensure_ascii=False, sort_keys=True)
                version = hashlib.sha256(raw.encode()).hexdigest()
            if version != source.version:
                raise PermissionDeniedError('منبع هنگام تولید پاسخ تغییر کرده است؛ دوباره بپرسید.')
        return True

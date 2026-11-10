"""Authenticated local assistant API; capability and tenant guards remain server-side."""
from django.urls import path
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import PermissionDeniedError
from .records import Reader
from .runtime import readiness, generate, inference_slot, rate_limit, LocalAiUnavailable

class Question(serializers.Serializer):
    question = serializers.CharField(min_length=3, max_length=400, trim_whitespace=True)
    scope = serializers.ChoiceField(choices=['all', 'maintenance', 'documents', 'projects'], default='all')
    deviceId = serializers.UUIDField(required=False)
    projectId = serializers.UUIDField(required=False)
    documentIds = serializers.ListField(child=serializers.UUIDField(), max_length=2, default=list)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': 'فقط فیلدهای مجاز پرسش پذیرفته می‌شوند.'})
        return super().to_internal_value(data)

    def validate(self, values):
        if len(values['question'].encode('utf-8')) > 1000:
            raise serializers.ValidationError('پرسش را کوتاه‌تر بنویسید.')
        if len(set(values['documentIds'])) != len(values['documentIds']):
            raise serializers.ValidationError('سند تکراری پذیرفته نمی‌شود.')
        scope = values['scope']
        if (scope not in {'all', 'maintenance', 'documents'} and values.get('deviceId')) or (scope not in {'all', 'projects'} and values.get('projectId')) or (scope not in {'all', 'documents'} and values['documentIds']):
            raise serializers.ValidationError('فیلتر انتخاب‌شده به این بخش مربوط نیست.')
        return values

class AssistantBase(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

class AssistantStatus(AssistantBase):
    def get(self, request):
        reader = Reader()
        choices = reader.choices()
        if not choices['scopes']:
            raise PermissionDeniedError('دسترسی خواندن هیچ‌یک از منابع دستیار را ندارید.')
        return Response(successEnvelope({**readiness(), **choices, 'readOnly': True, 'localOnly': True, 'limits': {'candidateRecordsPerType': 30, 'documentsPerQuestion': 2, 'pdfPages': 15, 'documentBytes': 4194304}}))

class AssistantAsk(AssistantBase):
    def post(self, request):
        serializer = Question(data=request.data); serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        reader = Reader()
        cap = reader.capabilities()
        if not any(cap.values()) or (values['scope'] != 'all' and not cap.get(values['scope'])):
            raise PermissionDeniedError('به منابع این بخش دسترسی ندارید.')
        from django.utils import timezone
        as_of = timezone.now().isoformat()
        rate_limit(str(reader.actor))
        with inference_slot():
            if not readiness()['ready']:
                raise LocalAiUnavailable()
            reader.collect(values['scope'], deviceId=str(values.get('deviceId', '')), projectId=str(values.get('projectId', '')), documentIds=tuple(map(str, values['documentIds'])), question=values['question'])
            evidence, selected = reader.evidence(values['question'])
            answer, citations = generate(values['question'], evidence) if evidence else ('در نمونهٔ منابع مجاز اطلاعات کافی پیدا نشد؛ یک دستگاه، پروژه یا سند مشخص انتخاب کنید.', [])
            # A revoked/expired session must not receive a long-running response.
            principal = sharedKernelProvider('sessionVerifier')().verifyToken(request.auth)
            if str(principal.userId) != str(reader.actor) or str(principal.tenantId) != str(reader.tenant):
                raise PermissionDeniedError()
            reader.revalidate(selected)
            sources = [{'id': item['id'], 'kind': source.kind, 'recordId': source.record, 'title': source.title, 'href': source.href, 'version': source.version, 'page': source.page, 'excerpt': item['text'], 'tables': source.tables, 'documentFormat': source.documentFormat, 'citedByModel': item['id'] in citations} for item, source in zip(evidence, selected) if item['id'] in citations or source.tables]
        from django.utils import timezone
        return Response(successEnvelope({'answer': answer, 'sources': sources, 'warnings': list(dict.fromkeys(reader.warnings)), 'model': readiness_model(), 'coverage': {'scope': values['scope'], 'selectionMode': 'documents' if values['documentIds'] else ('filtered' if values.get('deviceId') or values.get('projectId') else 'sample'), 'selectedDocumentCount': len(values['documentIds']), 'excerptOnly': True, 'reviewedSources': [{'id': item['id'], 'title': source.title, 'page': source.page, 'documentFormat': source.documentFormat, 'citedByModel': item['id'] in citations} for item, source in zip(evidence, selected)]}, 'asOf': as_of, 'readOnly': True, 'localOnly': True}))

def readiness_model():
    from .runtime import MODEL
    return MODEL

urlpatterns = [path('status', AssistantStatus.as_view()), path('ask', AssistantAsk.as_view())]

"""Non-cacheable, non-idempotency-stored credential issuance endpoints."""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.identity.infrastructure.services.mobileOnboarding import createMobileAccount, updateMobile, issueTemporaryPassword, completeFirstPassword, _authorize
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.response import successEnvelope
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit

from apps.identity.presentation.api.serializers.identitySerializers import CreateUserSerializer

class MobileSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=40)

class FirstPasswordSerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=2000, trim_whitespace=False)
    newPassword = serializers.CharField(min_length=12, max_length=200, trim_whitespace=False, write_only=True)

def privateResponse(data, status=200):
    response = Response(successEnvelope(data), status=status)
    response['Cache-Control'] = 'no-store'
    response['Pragma'] = 'no-cache'
    return response

def createAccountResponse(request):
    _authorize("user.create")
    serializer = CreateUserSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return privateResponse(createMobileAccount(**serializer.validated_data), 201)

class MobileEditView(APIView):
    permission_classes = [IsAuthenticated, actionPermission("user.update")]
    def patch(self, request, userId):
        serializer = MobileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return privateResponse(updateMobile(userId, serializer.validated_data['phone']))

class TemporaryPasswordView(APIView):
    permission_classes = [IsAuthenticated, actionPermission("user.update")]
    def post(self, request, userId):
        return privateResponse(issueTemporaryPassword(userId))

class FirstPasswordView(APIView):
    authentication_classes = []
    permission_classes = []
    @enforceRateLimit('auth:first-password')
    def post(self, request):
        serializer = FirstPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return privateResponse(completeFirstPassword(**serializer.validated_data))


def registerMobileEndpoints():
    from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
    registerEndpoint(EndpointSpec(method='POST', path='api/v1/auth/password/first', summary='Consume a scoped first-password challenge; returns no session.', authentication='none', rateLimitScope='auth:first-password', requestExample={'challenge':'…','newPassword':'…'}))
    registerEndpoint(EndpointSpec(method='PATCH', path='api/v1/users/{userId}/mobile', summary='Change mobile without changing account identity or assignments.', permission='user.update', requestExample={'phone':'09123456789'}))
    registerEndpoint(EndpointSpec(method='POST', path='api/v1/users/{userId}/temporary-password', summary='Issue a replacement temporary password once and revoke sessions.', permission='user.update'))

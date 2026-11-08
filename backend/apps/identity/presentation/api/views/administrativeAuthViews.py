"""Separate non-cacheable privileged login; never public account registration."""
from rest_framework import serializers
from rest_framework.views import APIView
from apps.identity.infrastructure.services import administrativeLogin
from apps.identity.presentation.api.views.mobileViews import privateResponse
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class PasswordSerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=4000, trim_whitespace=False)
    newPassword = serializers.CharField(min_length=12, max_length=1024, trim_whitespace=False, write_only=True)


class MfaSerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=4000, trim_whitespace=False)
    code = serializers.CharField(max_length=100, trim_whitespace=False, write_only=True)


class AdministrativeLoginView(APIView):
    authentication_classes = []
    permission_classes = []

    @enforceRateLimit('auth:login')
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return privateResponse(administrativeLogin.login(**serializer.validated_data))


class AdministrativeFirstPasswordView(APIView):
    authentication_classes = []
    permission_classes = []

    @enforceRateLimit('auth:login')
    def post(self, request):
        serializer = PasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return privateResponse(administrativeLogin.changeFirstPassword(
            serializer.validated_data['challenge'], serializer.validated_data['newPassword']))


class AdministrativeMfaView(APIView):
    authentication_classes = []
    permission_classes = []

    @enforceRateLimit('auth:mfa')
    def post(self, request):
        serializer = MfaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return privateResponse(administrativeLogin.verifyMfa(serializer.validated_data['challenge'], serializer.validated_data['code']))


def registerAdministrativeAuthEndpoints():
    from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
    for suffix, summary in [('login','Independent administrative password proof; never grants before MFA.'),
                             ('password','Replace temporary administrative password with a distinct personal password.'),
                             ('mfa','Verify TOTP or one-use recovery; issue session-bound administrative tokens.')]:
        registerEndpoint(EndpointSpec(method='POST', path='api/v1/superadmin/auth/'+suffix,
            summary=summary, authentication='none', errorCodes=['AUTH_CREDENTIALS_INVALID','AUTH_AUTHENTICATION_REQUIRED','SYS_RATE_LIMITED']))

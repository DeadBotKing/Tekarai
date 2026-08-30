"""Identity routes — mounted under /api/v1/ (Phase 06 §13 + Phase 07 §32)."""

from __future__ import annotations

from django.urls import path

from apps.identity.presentation.api.views.authViews import (
    LoginView,
    LogoutView,
    MfaChallengeView,
    RefreshView,
    registerAuthEndpoints,
)
from apps.identity.presentation.api.views.phase7Views import (
    ApiKeyDetailView,
    ApiKeyListView,
    ChangePasswordView,
    LogoutAllView,
    MfaConfirmView,
    MfaDisableView,
    MfaSetupView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RoleDetailView,
    RoleListView,
    SendVerificationView,
    ServiceAccountDetailView,
    ServiceAccountListView,
    SessionListView,
    SessionRevokeView,
    UserRoleView,
    VerifyEmailView,
    VerifyPhoneView,
    registerPhase7Endpoints,
)
from apps.identity.presentation.api.views.userViews import (
    MeView,
    UserDetailView,
    UserListView,
    UserMembershipView,
    registerUserEndpoints,
)

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="authLogin"),
    path("auth/mfa/challenge", MfaChallengeView.as_view(), name="authMfaChallenge"),
    path("auth/refresh", RefreshView.as_view(), name="authRefresh"),
    path("auth/logout", LogoutView.as_view(), name="authLogout"),
    path("auth/password/change", ChangePasswordView.as_view(), name="authPasswordChange"),
    path(
        "auth/password/reset/request",
        PasswordResetRequestView.as_view(),
        name="authPasswordResetRequest",
    ),
    path(
        "auth/password/reset/confirm",
        PasswordResetConfirmView.as_view(),
        name="authPasswordResetConfirm",
    ),
    path("auth/verify-email", VerifyEmailView.as_view(), name="authVerifyEmail"),
    path("auth/verify-phone", VerifyPhoneView.as_view(), name="authVerifyPhone"),
    path(
        "auth/verification/send",
        SendVerificationView.as_view(),
        name="authVerificationSend",
    ),
    path("me", MeView.as_view(), name="currentAccount"),
    path("me/mfa/setup", MfaSetupView.as_view(), name="mfaSetup"),
    path("me/mfa/confirm", MfaConfirmView.as_view(), name="mfaConfirm"),
    path("me/mfa/disable", MfaDisableView.as_view(), name="mfaDisable"),
    path("me/sessions", SessionListView.as_view(), name="sessionList"),
    path("me/sessions/revoke-all", LogoutAllView.as_view(), name="logoutAll"),
    path("me/sessions/<uuid:sessionId>", SessionRevokeView.as_view(), name="sessionRevoke"),
    path("roles", RoleListView.as_view(), name="roleList"),
    path("roles/<uuid:roleId>", RoleDetailView.as_view(), name="roleDetail"),
    path("users", UserListView.as_view(), name="userList"),
    path("users/<uuid:userId>", UserDetailView.as_view(), name="userDetail"),
    path("users/<uuid:userId>/memberships", UserMembershipView.as_view(), name="userMembership"),
    path("users/<uuid:userId>/roles", UserRoleView.as_view(), name="userRoles"),
    path("api-keys", ApiKeyListView.as_view(), name="apiKeyList"),
    path("api-keys/<uuid:apiKeyId>", ApiKeyDetailView.as_view(), name="apiKeyDetail"),
    path(
        "service-accounts",
        ServiceAccountListView.as_view(),
        name="serviceAccountList",
    ),
    path(
        "service-accounts/<uuid:accountId>",
        ServiceAccountDetailView.as_view(),
        name="serviceAccountDetail",
    ),
]

registerAuthEndpoints()
registerUserEndpoints()
registerPhase7Endpoints()

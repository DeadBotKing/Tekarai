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

from apps.identity.presentation.api.views.mobileViews import FirstPasswordView, MobileEditView, TemporaryPasswordView, registerMobileEndpoints

from apps.identity.presentation.api.views.administrativeAuthViews import (
    AdministrativeLoginView, AdministrativeFirstPasswordView, AdministrativeMfaView,
)

from apps.identity.presentation.api.views.administrativePanelViews import SetupView, PanelView, AppearanceView, CurrentAppearanceView, OrganizationEntryView, DiagnosticsView, ReviewPreviewView, ReviewCommitView, ReviewReportView, DatabaseConsoleView, DatabasePreviewView, DatabaseCommitView

urlpatterns = [
    path("superadmin/setup", SetupView.as_view(), name="administrativeSetup"),
    path("superadmin/panel/people/<uuid:userId>/diagnostics", DiagnosticsView.as_view(), name="administrativeDiagnostics"),
    path("superadmin/panel/preview", ReviewPreviewView.as_view(), name="administrativePreview"),
    path("superadmin/panel/commit", ReviewCommitView.as_view(), name="administrativeCommit"),
    path("superadmin/panel/database", DatabaseConsoleView.as_view(), name="administrativeDatabase"),
    path("superadmin/panel/database/preview", DatabasePreviewView.as_view(), name="administrativeDatabasePreview"),
    path("superadmin/panel/database/commit", DatabaseCommitView.as_view(), name="administrativeDatabaseCommit"),
    path("superadmin/panel/reports", ReviewReportView.as_view(), name="administrativeReports"),
    path("superadmin/panel", PanelView.as_view(), name="administrativePanel"),
    path("organization-appearance/current", CurrentAppearanceView.as_view(), name="currentAppearance"),
    path("organization-entry", OrganizationEntryView.as_view(), name="organizationEntry"),
    path("organization-appearance/<slug:code>", AppearanceView.as_view(), name="organizationAppearance"),
    path("superadmin/auth/login", AdministrativeLoginView.as_view(), name="administrativeLogin"),
    path("superadmin/auth/password", AdministrativeFirstPasswordView.as_view(), name="administrativeFirstPassword"),
    path("superadmin/auth/mfa", AdministrativeMfaView.as_view(), name="administrativeMfa"),
    path("auth/password/first", FirstPasswordView.as_view(), name="firstPassword"),
    path("users/<uuid:userId>/mobile", MobileEditView.as_view(), name="userMobile"),
    path("users/<uuid:userId>/temporary-password", TemporaryPasswordView.as_view(), name="userTemporaryPassword"),
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

registerMobileEndpoints()

from apps.identity.presentation.api.views.administrativeAuthViews import registerAdministrativeAuthEndpoints
from apps.identity.presentation.api.views.administrativePanelViews import registerAdministrativePanelEndpoints
registerAdministrativeAuthEndpoints()
registerAdministrativePanelEndpoints()

from apps.tenancy.presentation.api.workspaceViews import CurrentWorkspaceView, ManageWorkspaceView
urlpatterns += [path('organization-workspace/current',CurrentWorkspaceView.as_view(),name='currentWorkspace'),path('superadmin/organizations/<uuid:tenantId>/workspace',ManageWorkspaceView.as_view(),name='manageWorkspace')]

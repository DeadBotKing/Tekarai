"""Identity routes — mounted under /api/v1/ (§13)."""

from __future__ import annotations

from django.urls import path

from apps.identity.presentation.api.views.authViews import (
    LoginView,
    LogoutView,
    RefreshView,
    registerAuthEndpoints,
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
    path("auth/refresh", RefreshView.as_view(), name="authRefresh"),
    path("auth/logout", LogoutView.as_view(), name="authLogout"),
    path("me", MeView.as_view(), name="currentAccount"),
    path("users", UserListView.as_view(), name="userList"),
    path("users/<uuid:userId>", UserDetailView.as_view(), name="userDetail"),
    path(
        "users/<uuid:userId>/memberships",
        UserMembershipView.as_view(),
        name="userMembership",
    ),
]

registerAuthEndpoints()
registerUserEndpoints()

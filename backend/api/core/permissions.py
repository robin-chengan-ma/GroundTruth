from rest_framework import permissions


class IsBusinessAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role.role == "admin")


class AuthenticatedReadAdminWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        role = getattr(request.user, "role", None)
        return bool(role and role.role == "admin")

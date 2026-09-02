from rest_framework import permissions

from services.rbac_service import user_has_permission


class HasPermissionCode(permissions.BasePermission):
    """以 View 宣告的 permission code 授權；未宣告即拒絕，避免默認放行。"""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        permission_code = getattr(view, "required_permission", None)
        return bool(
            user
            and user.is_authenticated
            and permission_code
            and user_has_permission(user, permission_code)
        )


class IsBusinessAdmin(permissions.BasePermission):
    """相容名稱：管理 API 改由 identity.manage 權限控制，不再判斷角色字串。"""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user_has_permission(user, "identity.manage")
        )


class AuthenticatedReadAdminWrite(permissions.BasePermission):
    """主檔相容權限：讀取與管理皆使用正式 permission code。"""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if not hasattr(user, "id"):
            return request.method in permissions.SAFE_METHODS
        if request.method in permissions.SAFE_METHODS:
            return user_has_permission(user, "master_data.read")
        return user_has_permission(user, "master_data.manage")

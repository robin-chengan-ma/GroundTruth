from repositories.core import RbacRepository


def get_permission_codes(user, *, at=None):
    """取得指定時間有效的多角色權限；舊 users.role 不在此新服務中隱式放大權限。"""
    role_ids = RbacRepository.active_role_ids(user.id, at=at)
    return set(RbacRepository.permission_codes_for_roles(role_ids))


def user_has_permission(user, permission_code, *, at=None):
    return permission_code in get_permission_codes(user, at=at)

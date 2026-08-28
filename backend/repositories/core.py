"""封裝 core（roles/users）的 DB 存取。Phase 1 CRUD 直接透過 ORM QuerySet，
之後 services 層若需要更複雜查詢邏輯，統一經由這裡而不是在 api/ 直接操作 ORM。"""

from apps.core.models import Role, User


class RoleRepository:
    model = Role

    @staticmethod
    def all():
        return Role.objects.order_by("id")

    @staticmethod
    def get(pk):
        return Role.objects.get(pk=pk)


class UserRepository:
    model = User

    @staticmethod
    def all():
        return User.objects.select_related("role").order_by("id")

    @staticmethod
    def get(pk):
        return User.objects.select_related("role").get(pk=pk)

    @staticmethod
    def find_by_role(role_code: str):
        return User.objects.select_related("role").filter(role__role=role_code)

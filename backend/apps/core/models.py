from django.db import models


class Role(models.Model):
    """角色。employee／admin 為保留值，其餘可自由新增簽核相關角色。"""

    role = models.CharField(max_length=50, unique=True)
    approval_amount_limit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="該角色的簽核金額上限；null＝無上限（admin 固定 null）；employee 不參與簽核路由",
    )

    class Meta:
        db_table = "roles"

    def __str__(self):
        return self.role


class User(models.Model):
    """業務層使用者（非 Django contrib.auth.User，密碼以 Django 內建雜湊儲存）。"""

    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, unique=True)
    password = models.CharField(max_length=255, help_text="Django 內建雜湊儲存（PBKDF2），非明碼")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users", db_column="role_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email

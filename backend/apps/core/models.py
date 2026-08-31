from django.db import models
from django.db.models.functions import Now


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

    @property
    def is_authenticated(self):
        """讓業務 User 可套用 DRF 的 IsAuthenticated，不混用 Django auth User。"""
        return True


class Permission(models.Model):
    """可授予角色的最小操作能力。"""

    code = models.CharField(max_length=100, unique=True, db_comment="權限代碼，例如 purchase_request.create")
    name = models.CharField(max_length=100, db_comment="權限顯示名稱")
    description = models.TextField(blank=True, db_comment="權限用途說明")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "permissions"
        db_table_comment = "RBAC 權限主檔"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(code=""),
                name="permissions_code_not_empty",
            ),
        ]

    def __str__(self):
        return self.code


class UserRole(models.Model):
    """使用者可同時持有多個角色；users.role_id 暫留供舊流程 dual-read。"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_roles",
        db_column="user_id",
        db_comment="持有角色的 users.id",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="user_roles",
        db_column="role_id",
        db_comment="授予的 roles.id",
    )
    valid_from = models.DateTimeField(db_default=Now(), db_comment="角色生效時間")
    valid_until = models.DateTimeField(null=True, blank=True, db_comment="角色失效時間；NULL 表示持續有效")
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_user_roles",
        db_column="assigned_by_id",
        db_comment="授予角色的 users.id；資料遷移可為 NULL",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "user_roles"
        db_table_comment = "使用者與角色的多對多指派及有效期間"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="user_roles_user_role_unique"),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="user_roles_valid_period_check",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "valid_until"], name="user_roles_active_idx"),
        ]


class RolePermission(models.Model):
    """角色所包含的操作能力。"""

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
        db_column="role_id",
        db_comment="對應 roles.id",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
        db_column="permission_id",
        db_comment="對應 permissions.id",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "role_permissions"
        db_table_comment = "RBAC 角色與權限對照"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="role_permissions_pair_unique"),
        ]


class RefreshSession(models.Model):
    """Refresh Token rotation／撤銷狀態；只保存 Token 雜湊，不落地明文。"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
        db_column="user_id",
        db_comment="對應 users.id 的登入使用者",
    )
    jti = models.CharField(max_length=36, unique=True, db_comment="JWT 唯一識別碼，不含 Token 明文")
    token_hash = models.CharField(
        max_length=64, unique=True, db_comment="Refresh Token 的 SHA-256 雜湊，不儲存 Token 明文"
    )
    created_at = models.DateTimeField(
        db_default=Now(), editable=False, db_comment="Session 建立時間（由資料庫產生）"
    )
    expires_at = models.DateTimeField(db_comment="Refresh Token 到期時間")
    revoked_at = models.DateTimeField(null=True, blank=True, db_comment="撤銷時間；NULL 表示尚未撤銷")
    replaced_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="replaced_by_id",
        related_name="replaces",
        db_comment="Rotation 後接替此 Token 的 refresh_sessions.id",
    )

    class Meta:
        db_table = "refresh_sessions"
        db_table_comment = "使用者 Refresh Token session，供 rotation、登出撤銷與重放防護使用"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="refresh_sessions_expiry_check",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "expires_at"],
                condition=models.Q(revoked_at__isnull=True),
                name="refresh_user_active_idx",
            ),
        ]

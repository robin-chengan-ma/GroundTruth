"""灌入 Phase 1 demo 假資料，供後續 Phase 手動測試與 API 驗收使用。
可重複執行（get_or_create），不會產生重複資料。"""
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Permission, Role, RolePermission, User, UserRole
from apps.crm.models import Supplier
from apps.erp.models import Inventory, Product
from apps.procurement.models import ApprovalPolicy, ApprovalPolicyStep, Quote


class Command(BaseCommand):
    help = "灌入 Phase 1 demo 假資料（roles/users/suppliers/products/inventory/quotes）"

    @transaction.atomic
    def handle(self, *args, **options):
        roles = self._seed_roles()
        users = self._seed_users(roles)
        self._seed_rbac(roles, users)
        self._seed_approval_policies(roles)
        suppliers = self._seed_suppliers()
        products = self._seed_products()
        self._seed_inventory(products)
        self._seed_quotes(users, suppliers, products)
        self.stdout.write(self.style.SUCCESS("Demo 假資料灌入完成。"))

    def _seed_roles(self):
        specs = [
            ("employee", None),
            ("approver_10k", Decimal("10000.00")),
            ("approver_100k", Decimal("100000.00")),
            ("procurement_director", None),
            ("procurement_exception_reviewer", None),
            ("receiver", None),
            ("inspector", None),
            ("admin", None),
        ]
        roles = {}
        for role_code, limit in specs:
            role, _ = Role.objects.get_or_create(
                role=role_code, defaults={"approval_amount_limit": limit}
            )
            roles[role_code] = role
        return roles

    def _seed_users(self, roles):
        specs = [
            ("Alice Chen", "alice@groundtruth.demo", "employee"),
            ("Bob Lin", "bob@groundtruth.demo", "employee"),
            ("Carol Wu", "carol@groundtruth.demo", "approver_10k"),
            ("David Huang", "david@groundtruth.demo", "approver_100k"),
            ("Eva Kao", "eva@groundtruth.demo", "admin"),
            ("Frank Tsai", "frank@groundtruth.demo", "receiver"),
            ("Grace Liu", "grace@groundtruth.demo", "inspector"),
        ]
        users = {}
        for name, email, role_code in specs:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "password": make_password("demo-password-123"),
                    "role": roles[role_code],
                },
            )
            users[email] = user
        return users

    def _seed_rbac(self, roles, users):
        permission_specs = {
            "employee": [
                ("purchase_request.create", "建立採購需求"),
                ("purchase_request.read_own", "讀取自己的採購需求"),
                ("purchase_request.edit_draft", "編輯自己的需求草稿"),
                ("purchase_request.submit", "提交自己的採購需求"),
                ("purchase_request.withdraw", "撤回自己的採購需求"),
                ("master_data.read", "讀取主檔"),
                ("inventory.read", "讀取庫存"),
                ("purchase_suggestion.read", "讀取採購建議"),
            ],
            "approver_10k": [
                ("approval.claim", "認領簽核案件"),
                ("approval.decide", "決議簽核案件"),
                ("approval.read_all", "讀取可簽核案件"),
                ("master_data.read", "讀取主檔"),
                ("requirement.waive", "核准必要條件例外"),
            ],
            "approver_100k": [
                ("approval.claim", "認領簽核案件"),
                ("approval.decide", "決議簽核案件"),
                ("approval.read_all", "讀取可簽核案件"),
                ("master_data.read", "讀取主檔"),
                ("requirement.waive", "核准必要條件例外"),
            ],
            "procurement_director": [
                ("approval.claim", "認領簽核案件"),
                ("approval.decide", "決議簽核案件"),
                ("approval.read_all", "讀取可簽核案件"),
                ("master_data.read", "讀取主檔"),
                ("rfq.manage", "管理 RFQ"),
                ("award.recommend", "建立與提交得標方案"),
                ("purchase_order.manage", "管理與發出採購單"),
                ("supplier_quote.manage", "管理供應商報價"),
                ("requirement.waive", "核准必要條件例外"),
            ],
            "procurement_exception_reviewer": [
                ("approval.claim", "認領簽核案件"),
                ("approval.decide", "決議簽核案件"),
                ("approval.read_all", "讀取可簽核案件"),
                ("requirement.waive", "核准必要條件例外"),
            ],
            "receiver": [
                ("receipt.record", "建立與送出收貨單"),
                ("master_data.read", "讀取主檔"),
                ("inventory.read", "讀取庫存"),
            ],
            "inspector": [
                ("inspection.decide", "執行品質驗收"),
                ("master_data.read", "讀取主檔"),
                ("inventory.read", "讀取庫存"),
            ],
            "admin": [
                ("identity.manage", "管理帳號與角色"),
                ("master_data.read", "讀取主檔"),
                ("master_data.manage", "管理供應商與品項主檔"),
                ("inventory.read", "讀取庫存"),
                ("manual_review.claim", "認領人工複核案件"),
                ("manual_review.decide", "決議人工複核案件"),
                ("audit.read", "讀取稽核紀錄"),
                ("purchase_suggestion.read", "讀取採購建議"),
            ],
        }
        for user in users.values():
            UserRole.objects.get_or_create(user=user, role=user.role)
        UserRole.objects.get_or_create(
            user=users["david@groundtruth.demo"],
            role=roles["procurement_director"],
        )
        for email in ("carol@groundtruth.demo", "david@groundtruth.demo"):
            UserRole.objects.get_or_create(
                user=users[email],
                role=roles["procurement_exception_reviewer"],
            )
        for role_code, specs in permission_specs.items():
            for code, name in specs:
                permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name})
                RolePermission.objects.get_or_create(role=roles[role_code], permission=permission)

    def _seed_approval_policies(self, roles):
        now = timezone.now()
        specs = [
            ("TWD 小額 Demo", Decimal("0.00"), Decimal("10000.00"), "approver_10k"),
            ("TWD 中額 Demo", Decimal("10000.00"), Decimal("100000.00"), "approver_100k"),
            ("TWD 大額 Demo", Decimal("100000.00"), None, "procurement_director"),
        ]
        for name, minimum, maximum, role_code in specs:
            policy, _ = ApprovalPolicy.objects.get_or_create(
                name=name,
                currency="TWD",
                defaults={
                    "min_amount": minimum,
                    "max_amount": maximum,
                    "active_from": now,
                },
            )
            if policy.waiver_role_id != roles["procurement_exception_reviewer"].id:
                policy.waiver_role = roles["procurement_exception_reviewer"]
                policy.save(update_fields=["waiver_role", "updated_at"])
            ApprovalPolicyStep.objects.get_or_create(
                policy=policy,
                sequence=1,
                defaults={"role": roles[role_code]},
            )

    def _seed_suppliers(self):
        specs = [
            ("優品科技", Supplier.Tier.PRIORITY),
            ("誠信貿易", Supplier.Tier.PRIORITY),
            ("大和物產", Supplier.Tier.NORMAL),
            ("新星工業", Supplier.Tier.NORMAL),
            ("暫緩供應", Supplier.Tier.WATCH),
        ]
        suppliers = {}
        for name, tier in specs:
            supplier, _ = Supplier.objects.get_or_create(name=name, defaults={"tier": tier})
            suppliers[name] = supplier
        return suppliers

    def _seed_products(self):
        specs = [
            ("A產品-辦公椅", Decimal("1500.00"), "TWD"),
            ("B產品-筆記型電腦", Decimal("32000.00"), "TWD"),
            ("C產品-印表機碳粉", Decimal("850.00"), "TWD"),
            ("D產品-白板", Decimal("2200.00"), "TWD"),
            ("E產品-伺服器機櫃", Decimal("48000.00"), "TWD"),
            ("F產品-辦公桌", Decimal("3600.00"), "TWD"),
        ]
        products = {}
        for name, price, currency in specs:
            product, _ = Product.objects.get_or_create(
                name=name, defaults={"price": price, "currency": currency}
            )
            products[name] = product
        return products

    def _seed_inventory(self, products):
        # 部分產品故意設在 threshold 之下，供之後 FR-10a 自動採購建議測試使用。
        specs = [
            ("A產品-辦公椅", 40, 10),
            ("B產品-筆記型電腦", 5, 8),  # 低於門檻
            ("C產品-印表機碳粉", 3, 15),  # 低於門檻
            ("D產品-白板", 20, 5),
            ("E產品-伺服器機櫃", 2, 2),
            ("F產品-辦公桌", 12, 6),
        ]
        for name, stock_qty, threshold in specs:
            Inventory.objects.get_or_create(
                product=products[name],
                defaults={"stock_qty": stock_qty, "threshold": threshold},
            )

    def _seed_quotes(self, users, suppliers, products):
        # 少量「已核准」歷史紀錄，供 FR-4a 歷史均價比對測試使用。
        specs = [
            ("alice@groundtruth.demo", "優品科技", "A產品-辦公椅", 20, Decimal("1450.00")),
            ("alice@groundtruth.demo", "優品科技", "A產品-辦公椅", 30, Decimal("1480.00")),
            ("bob@groundtruth.demo", "大和物產", "F產品-辦公桌", 10, Decimal("3550.00")),
        ]
        for email, supplier_name, product_name, qty, price in specs:
            total = price * qty
            Quote.objects.get_or_create(
                user=users[email],
                supplier=suppliers[supplier_name],
                product=products[product_name],
                quantity=qty,
                price=price,
                defaults={
                    "total_amount": total,
                    "currency": "TWD",
                    "status": Quote.Status.APPROVED,
                },
            )

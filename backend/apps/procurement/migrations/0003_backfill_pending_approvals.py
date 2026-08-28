from decimal import Decimal

from django.db import migrations

SMALL_MAX = Decimal(10000)
MEDIUM_MAX = Decimal(100000)


def backfill_pending_approvals(apps, schema_editor):
    Approval = apps.get_model("procurement", "Approval")
    Quote = apps.get_model("procurement", "Quote")
    Role = apps.get_model("core", "Role")

    orphan_quotes = Quote.objects.filter(status="pending_approval", approvals__isnull=True).iterator()
    for quote in orphan_quotes:
        role = (
            Role.objects.filter(approval_amount_limit__gte=quote.total_amount)
            .exclude(role__in=["employee", "admin"])
            .order_by("approval_amount_limit", "id")
            .first()
        )
        if role is None:
            role = Role.objects.filter(role="admin").first()
        if role is None:
            raise RuntimeError("缺少可用簽核角色，無法回填待簽核案件")

        if quote.total_amount <= SMALL_MAX:
            level = "small"
        elif quote.total_amount <= MEDIUM_MAX:
            level = "medium"
        else:
            level = "large"

        Approval.objects.create(
            quote=quote,
            role=role,
            approval_level=level,
            status="pending",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0002_approval_cancelled_unique"),
    ]

    operations = [
        migrations.RunPython(backfill_pending_approvals, migrations.RunPython.noop),
    ]

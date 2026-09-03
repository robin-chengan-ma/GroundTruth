# Generated manually to match Django 5.2.17 migration format (Robin 2026-09-03：人工複核駁回原因)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0004_manualreviewqueue_created_purchase_request_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="manualreviewqueue",
            name="rejection_reason",
            field=models.TextField(
                blank=True,
                help_text="決議為 rejected 時管理員填寫的駁回原因；決議當下必填，用於通知申請人與畫面顯示",
                null=True,
            ),
        ),
    ]

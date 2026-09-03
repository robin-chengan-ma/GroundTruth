# Generated manually to match Django 5.2.17 migration format
# (Robin 2026-09-03：已駁回需求「複製並重新編輯」來源追蹤欄位)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0011_purchase_request_rejected_status"),
        ("audit", "0005_manualreviewqueue_rejection_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="copied_from_review",
            field=models.ForeignKey(
                blank=True,
                db_column="copied_from_review_id",
                db_comment="若此需求是複製自已駁回的人工複核案件重新編輯而成，記錄來源案件；用字串參照 audit app 避免與該 app 的 models.py 互相 import 造成循環依賴",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="copies",
                to="audit.manualreviewqueue",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="copied_from_request",
            field=models.ForeignKey(
                blank=True,
                db_column="copied_from_request_id",
                db_comment="若此需求是複製自已駁回的採購需求重新編輯而成，記錄來源需求；同一來源只允許被複製一次，由 service 層檢查 copies 是否已存在",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="copies",
                to="procurement.purchaserequest",
            ),
        ),
    ]

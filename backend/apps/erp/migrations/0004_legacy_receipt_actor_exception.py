import django.db.models.deletion
from django.db import migrations, models

FORWARD_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION enforce_quality_inspection_quantities()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    received_qty numeric(14,3);
    receipt_legacy_quote_id bigint;
BEGIN
    SELECT gri.received_quantity, gr.legacy_quote_id
    INTO received_qty, receipt_legacy_quote_id
    FROM goods_receipt_items gri
    JOIN goods_receipts gr ON gr.id = gri.receipt_id
    WHERE gri.id = NEW.receipt_item_id;
    IF received_qty IS NULL OR
       NEW.accepted_quantity + NEW.defective_quantity + NEW.rejected_quantity <> received_qty THEN
        RAISE EXCEPTION 'inspection quantities must equal received quantity'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.inspected_by_id IS NULL AND receipt_legacy_quote_id IS NULL THEN
        RAISE EXCEPTION 'inspection actor is required unless receipt is legacy migration'
            USING ERRCODE = 'not_null_violation';
    END IF;
    IF (NEW.status = 'accepted' AND
            (NEW.accepted_quantity <> received_qty OR
             NEW.defective_quantity <> 0 OR NEW.rejected_quantity <> 0))
       OR (NEW.status = 'partially_accepted' AND
            (NEW.accepted_quantity <= 0 OR
             NEW.defective_quantity + NEW.rejected_quantity <= 0))
       OR (NEW.status = 'rejected' AND NEW.accepted_quantity <> 0) THEN
        RAISE EXCEPTION 'inspection status is inconsistent with quantity allocation'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""


REVERSE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION enforce_quality_inspection_quantities()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    received_qty numeric(14,3);
BEGIN
    SELECT received_quantity INTO received_qty
    FROM goods_receipt_items WHERE id = NEW.receipt_item_id;
    IF received_qty IS NULL OR
       NEW.accepted_quantity + NEW.defective_quantity + NEW.rejected_quantity <> received_qty THEN
        RAISE EXCEPTION 'inspection quantities must equal received quantity'
            USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.status = 'accepted' AND
            (NEW.accepted_quantity <> received_qty OR
             NEW.defective_quantity <> 0 OR NEW.rejected_quantity <> 0))
       OR (NEW.status = 'partially_accepted' AND
            (NEW.accepted_quantity <= 0 OR
             NEW.defective_quantity + NEW.rejected_quantity <= 0))
       OR (NEW.status = 'rejected' AND NEW.accepted_quantity <> 0) THEN
        RAISE EXCEPTION 'inspection status is inconsistent with quantity allocation'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("erp", "0003_receiving_inventory_ledger"),
    ]

    operations = [
        migrations.AlterField(
            model_name="goodsreceipt",
            name="received_by",
            field=models.ForeignKey(
                blank=True,
                db_column="received_by_id",
                db_comment="實際記錄收貨的 users.id；僅 legacy migration 可為 NULL",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="recorded_goods_receipts",
                to="core.user",
            ),
        ),
        migrations.AddConstraint(
            model_name="goodsreceipt",
            constraint=models.CheckConstraint(
                condition=models.Q(legacy_quote__isnull=False) | models.Q(received_by__isnull=False),
                name="goods_receipts_actor_required_unless_legacy",
            ),
        ),
        migrations.AlterField(
            model_name="qualityinspection",
            name="inspected_by",
            field=models.ForeignKey(
                blank=True,
                db_column="inspected_by_id",
                db_comment="執行品質驗收的 users.id；僅 legacy migration 可為 NULL",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="quality_inspections",
                to="core.user",
            ),
        ),
        migrations.RunSQL(FORWARD_TRIGGER_SQL, reverse_sql=REVERSE_TRIGGER_SQL),
    ]

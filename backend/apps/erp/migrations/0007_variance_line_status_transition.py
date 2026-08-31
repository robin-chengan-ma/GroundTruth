from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION protect_submitted_variance_lines()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    case_status varchar;
BEGIN
    SELECT status INTO case_status FROM inspection_variance_cases
    WHERE id = COALESCE(NEW.variance_case_id, OLD.variance_case_id);

    IF case_status = 'draft' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'submitted variance lines are immutable'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    IF OLD.status = 'pending'
       AND NEW.status = 'completed'
       AND OLD.completed_by_id IS NULL
       AND OLD.completed_at IS NULL
       AND NEW.completed_by_id IS NOT NULL
       AND NEW.completed_at IS NOT NULL
       AND NEW.variance_case_id = OLD.variance_case_id
       AND NEW.action_type = OLD.action_type
       AND NEW.quantity = OLD.quantity
       AND NEW.reason = OLD.reason
       AND NEW.created_at = OLD.created_at THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'submitted variance lines allow only pending to completed transition'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE OR REPLACE FUNCTION enforce_goods_receipt_item_quantity()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    receipt_po_id bigint;
    item_po_id bigint;
    ordered_qty numeric(14,3);
    already_received numeric(14,3);
    replacement_qty numeric(14,3);
    replacement_po_item_id bigint;
    replacement_action varchar;
    replacement_line_status varchar;
    replacement_case_status varchar;
BEGIN
    SELECT purchase_order_id INTO receipt_po_id FROM goods_receipts WHERE id = NEW.receipt_id;
    SELECT purchase_order_id, ordered_quantity INTO item_po_id, ordered_qty
    FROM purchase_order_items WHERE id = NEW.purchase_order_item_id FOR UPDATE;
    IF receipt_po_id IS NULL OR item_po_id IS NULL OR receipt_po_id <> item_po_id THEN
        RAISE EXCEPTION 'receipt item must belong to the receipt purchase order'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF NEW.replacement_variance_line_id IS NULL THEN
        SELECT COALESCE(SUM(received_quantity), 0) INTO already_received
        FROM goods_receipt_items
        WHERE purchase_order_item_id = NEW.purchase_order_item_id
          AND replacement_variance_line_id IS NULL
          AND id <> COALESCE(NEW.id, -1);
        IF already_received + NEW.received_quantity > ordered_qty THEN
            RAISE EXCEPTION 'cumulative original received quantity exceeds ordered quantity'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        SELECT ivl.quantity, gri.purchase_order_item_id, ivl.action_type, ivl.status, ivc.status
        INTO replacement_qty, replacement_po_item_id, replacement_action,
             replacement_line_status, replacement_case_status
        FROM inspection_variance_lines ivl
        JOIN inspection_variance_cases ivc ON ivc.id = ivl.variance_case_id
        JOIN quality_inspections qi ON qi.id = ivc.quality_inspection_id
        JOIN goods_receipt_items gri ON gri.id = qi.receipt_item_id
        WHERE ivl.id = NEW.replacement_variance_line_id;
        IF replacement_action <> 'replacement'
           OR replacement_line_status <> 'pending'
           OR replacement_case_status <> 'open'
           OR replacement_po_item_id <> NEW.purchase_order_item_id THEN
            RAISE EXCEPTION 'replacement receipt requires an open matching pending replacement line'
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT COALESCE(SUM(received_quantity), 0) INTO already_received
        FROM goods_receipt_items
        WHERE replacement_variance_line_id = NEW.replacement_variance_line_id
          AND id <> COALESCE(NEW.id, -1);
        IF already_received + NEW.received_quantity > replacement_qty THEN
            RAISE EXCEPTION 'cumulative replacement received quantity exceeds authorized quantity'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION protect_submitted_variance_lines()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    case_status varchar;
BEGIN
    SELECT status INTO case_status FROM inspection_variance_cases
    WHERE id = COALESCE(NEW.variance_case_id, OLD.variance_case_id);
    IF case_status <> 'draft' THEN
        RAISE EXCEPTION 'submitted variance lines are immutable'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_goods_receipt_item_quantity()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    receipt_po_id bigint;
    item_po_id bigint;
    ordered_qty numeric(14,3);
    already_received numeric(14,3);
    replacement_qty numeric(14,3);
    replacement_po_item_id bigint;
    replacement_action varchar;
    replacement_case_status varchar;
BEGIN
    SELECT purchase_order_id INTO receipt_po_id FROM goods_receipts WHERE id = NEW.receipt_id;
    SELECT purchase_order_id, ordered_quantity INTO item_po_id, ordered_qty
    FROM purchase_order_items WHERE id = NEW.purchase_order_item_id FOR UPDATE;
    IF receipt_po_id IS NULL OR item_po_id IS NULL OR receipt_po_id <> item_po_id THEN
        RAISE EXCEPTION 'receipt item must belong to the receipt purchase order'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF NEW.replacement_variance_line_id IS NULL THEN
        SELECT COALESCE(SUM(received_quantity), 0) INTO already_received
        FROM goods_receipt_items
        WHERE purchase_order_item_id = NEW.purchase_order_item_id
          AND replacement_variance_line_id IS NULL
          AND id <> COALESCE(NEW.id, -1);
        IF already_received + NEW.received_quantity > ordered_qty THEN
            RAISE EXCEPTION 'cumulative original received quantity exceeds ordered quantity'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        SELECT ivl.quantity, gri.purchase_order_item_id, ivl.action_type, ivc.status
        INTO replacement_qty, replacement_po_item_id, replacement_action, replacement_case_status
        FROM inspection_variance_lines ivl
        JOIN inspection_variance_cases ivc ON ivc.id = ivl.variance_case_id
        JOIN quality_inspections qi ON qi.id = ivc.quality_inspection_id
        JOIN goods_receipt_items gri ON gri.id = qi.receipt_item_id
        WHERE ivl.id = NEW.replacement_variance_line_id;
        IF replacement_action <> 'replacement'
           OR replacement_case_status NOT IN ('open', 'closed')
           OR replacement_po_item_id <> NEW.purchase_order_item_id THEN
            RAISE EXCEPTION 'replacement receipt requires an active matching replacement line'
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT COALESCE(SUM(received_quantity), 0) INTO already_received
        FROM goods_receipt_items
        WHERE replacement_variance_line_id = NEW.replacement_variance_line_id
          AND id <> COALESCE(NEW.id, -1);
        IF already_received + NEW.received_quantity > replacement_qty THEN
            RAISE EXCEPTION 'cumulative replacement received quantity exceeds authorized quantity'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("erp", "0006_inspection_variance_comments"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]

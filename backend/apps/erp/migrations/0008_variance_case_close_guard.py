from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION enforce_inspection_variance_case()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    variance_qty numeric(14,3);
    allocated_qty numeric(14,3);
    incomplete_line_count bigint;
BEGIN
    SELECT defective_quantity + rejected_quantity INTO variance_qty
    FROM quality_inspections WHERE id = NEW.quality_inspection_id;
    IF variance_qty IS NULL OR variance_qty <= 0 THEN
        RAISE EXCEPTION 'variance case requires defective or rejected quantity'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IN ('open', 'closed') THEN
        SELECT COALESCE(SUM(quantity), 0) INTO allocated_qty
        FROM inspection_variance_lines
        WHERE variance_case_id = NEW.id AND status <> 'cancelled';
        IF allocated_qty <> variance_qty THEN
            RAISE EXCEPTION 'active variance line quantities must equal inspection variance quantity'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.submitted_by_id IS NULL OR NEW.submitted_at IS NULL THEN
            RAISE EXCEPTION 'submitted actor and time are required for open variance case'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF NEW.status = 'closed' THEN
        IF TG_OP <> 'UPDATE' OR OLD.status <> 'open' THEN
            RAISE EXCEPTION 'variance case can close only from open status'
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT COUNT(*) INTO incomplete_line_count
        FROM inspection_variance_lines
        WHERE variance_case_id = NEW.id AND status <> 'completed';
        IF incomplete_line_count > 0 THEN
            RAISE EXCEPTION 'all variance lines must be completed before closing'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.closed_by_id IS NULL OR NEW.closed_at IS NULL THEN
            RAISE EXCEPTION 'closed actor and time are required for closed variance case'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION enforce_inspection_variance_case()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    variance_qty numeric(14,3);
    allocated_qty numeric(14,3);
BEGIN
    SELECT defective_quantity + rejected_quantity INTO variance_qty
    FROM quality_inspections WHERE id = NEW.quality_inspection_id;
    IF variance_qty IS NULL OR variance_qty <= 0 THEN
        RAISE EXCEPTION 'variance case requires defective or rejected quantity'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IN ('open', 'closed') THEN
        SELECT COALESCE(SUM(quantity), 0) INTO allocated_qty
        FROM inspection_variance_lines
        WHERE variance_case_id = NEW.id AND status <> 'cancelled';
        IF allocated_qty <> variance_qty THEN
            RAISE EXCEPTION 'active variance line quantities must equal inspection variance quantity'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.submitted_by_id IS NULL OR NEW.submitted_at IS NULL THEN
            RAISE EXCEPTION 'submitted actor and time are required for open variance case'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF NEW.status = 'closed' AND (NEW.closed_by_id IS NULL OR NEW.closed_at IS NULL) THEN
        RAISE EXCEPTION 'closed actor and time are required for closed variance case'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [("erp", "0007_variance_line_status_transition")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]

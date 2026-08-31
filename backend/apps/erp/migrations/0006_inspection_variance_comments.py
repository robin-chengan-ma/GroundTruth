from django.db import migrations


COMMENTS_SQL = """
COMMENT ON COLUMN inspection_variance_cases.id IS '驗收差異案件主鍵';
COMMENT ON COLUMN inspection_variance_cases.quality_inspection_id IS '對應 quality_inspections.id';
COMMENT ON COLUMN inspection_variance_cases.created_by_id IS '建立案件的 users.id';
COMMENT ON COLUMN inspection_variance_cases.submitted_by_id IS '正式提出處理方案的 users.id';
COMMENT ON COLUMN inspection_variance_cases.submitted_at IS '正式提出處理方案時間';
COMMENT ON COLUMN inspection_variance_cases.closed_by_id IS '結案者 users.id';
COMMENT ON COLUMN inspection_variance_cases.closed_at IS '正式結案時間';
COMMENT ON COLUMN inspection_variance_cases.created_at IS '建立時間';
COMMENT ON COLUMN inspection_variance_cases.updated_at IS '最後更新時間，由 trigger 維護';
COMMENT ON COLUMN inspection_variance_lines.id IS '驗收差異處理明細主鍵';
COMMENT ON COLUMN inspection_variance_lines.variance_case_id IS '對應 inspection_variance_cases.id';
COMMENT ON COLUMN inspection_variance_lines.completed_by_id IS '完成處理的 users.id';
COMMENT ON COLUMN inspection_variance_lines.completed_at IS '完成處理時間';
COMMENT ON COLUMN inspection_variance_lines.created_at IS '建立時間';
COMMENT ON COLUMN goods_receipt_items.replacement_variance_line_id IS '補交收貨依據的 inspection_variance_lines.id';
COMMENT ON COLUMN purchase_suggestions.source_movement_id IS '觸發建議的 inventory_movements.id';
COMMENT ON COLUMN purchase_suggestions.purchase_request_id IS '由建議轉成的 purchase_requests.id';
"""


class Migration(migrations.Migration):
    dependencies = [("erp", "0005_inspection_variances")]

    operations = [
        migrations.RunSQL(COMMENTS_SQL, reverse_sql=migrations.RunSQL.noop),
    ]

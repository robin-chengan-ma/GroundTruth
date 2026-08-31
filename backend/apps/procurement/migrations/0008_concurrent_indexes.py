from django.db import migrations, models


INDEXES = (
    (
        "CREATE INDEX CONCURRENTLY pr_status_updated_idx "
        "ON purchase_requests (status, updated_at DESC)",
        "DROP INDEX CONCURRENTLY pr_status_updated_idx",
    ),
    (
        "CREATE INDEX CONCURRENTLY rfq_status_due_idx "
        "ON rfqs (status, response_due_at)",
        "DROP INDEX CONCURRENTLY rfq_status_due_idx",
    ),
    (
        "CREATE INDEX CONCURRENTLY rfq_supplier_queue_idx "
        "ON rfq_suppliers (supplier_id, status, invited_at DESC)",
        "DROP INDEX CONCURRENTLY rfq_supplier_queue_idx",
    ),
    (
        "CREATE INDEX CONCURRENTLY sq_status_valid_idx "
        "ON supplier_quotes (status, valid_until)",
        "DROP INDEX CONCURRENTLY sq_status_valid_idx",
    ),
    (
        "CREATE INDEX CONCURRENTLY approval_step_queue_idx "
        "ON approval_steps (role_id, status, sequence)",
        "DROP INDEX CONCURRENTLY approval_step_queue_idx",
    ),
    (
        "CREATE INDEX CONCURRENTLY po_supplier_status_idx "
        "ON purchase_orders (supplier_id, status)",
        "DROP INDEX CONCURRENTLY po_supplier_status_idx",
    ),
)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("procurement", "0007_awarddecision_approvalcase_awardline_purchaseorder_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=sql, reverse_sql=reverse_sql)
                for sql, reverse_sql in INDEXES
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="purchaserequest",
                    index=models.Index(fields=["status", "-updated_at"], name="pr_status_updated_idx"),
                ),
                migrations.AddIndex(
                    model_name="rfq",
                    index=models.Index(fields=["status", "response_due_at"], name="rfq_status_due_idx"),
                ),
                migrations.AddIndex(
                    model_name="rfqsupplier",
                    index=models.Index(
                        fields=["supplier", "status", "-invited_at"],
                        name="rfq_supplier_queue_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="supplierquote",
                    index=models.Index(
                        fields=["status", "valid_until"],
                        name="sq_status_valid_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="approvalstep",
                    index=models.Index(
                        fields=["role", "status", "sequence"],
                        name="approval_step_queue_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="purchaseorder",
                    index=models.Index(fields=["supplier", "status"], name="po_supplier_status_idx"),
                ),
            ],
        ),
    ]

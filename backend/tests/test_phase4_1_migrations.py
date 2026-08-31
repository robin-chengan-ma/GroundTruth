import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ROLLBACK_TARGETS = [
    ("procurement", "0003_backfill_pending_approvals"),
    ("erp", "0001_initial"),
    ("crm", "0001_initial"),
    ("core", "0002_refresh_session"),
]

FORWARD_TARGETS = [
    ("core", "0003_permission_rolepermission_userrole"),
    ("crm", "0002_supplier_code_supplier_contact_supplier_is_active_and_more"),
    ("erp", "0002_productcategory_product_description_and_more"),
    ("procurement", "0004_approvalpolicy_supplierproduct_supplierpriceversion_and_more"),
]


@pytest.mark.django_db(transaction=True)
def test_phase4_1_foundation_migrations_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate(ROLLBACK_TARGETS)

    tables_after_reverse = set(connection.introspection.table_names())
    assert "permissions" not in tables_after_reverse
    assert "product_categories" not in tables_after_reverse
    assert "approval_policies" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate(FORWARD_TARGETS)

    tables_after_forward = set(connection.introspection.table_names())
    assert {"permissions", "product_categories", "approval_policies"} <= tables_after_forward


@pytest.mark.django_db(transaction=True)
def test_purchase_request_rfq_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0004_approvalpolicy_supplierproduct_supplierpriceversion_and_more")])

    tables_after_reverse = set(connection.introspection.table_names())
    assert "purchase_requests" not in tables_after_reverse
    assert "rfqs" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0005_purchaserequest_purchaserequestitem_and_more")])

    tables_after_forward = set(connection.introspection.table_names())
    assert {
        "purchase_requests",
        "purchase_request_items",
        "request_item_requirements",
        "rfqs",
        "rfq_suppliers",
    } <= tables_after_forward


@pytest.mark.django_db(transaction=True)
def test_supplier_quote_scoring_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0005_purchaserequest_purchaserequestitem_and_more")])

    tables_after_reverse = set(connection.introspection.table_names())
    assert "supplier_quotes" not in tables_after_reverse
    assert "supplier_quote_scores" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0006_supplierquote_rfqscoringcriterion_and_more")])

    tables_after_forward = set(connection.introspection.table_names())
    assert {
        "supplier_quotes",
        "supplier_quote_items",
        "quote_requirement_results",
        "rfq_scoring_criteria",
        "supplier_quote_scores",
    } <= tables_after_forward


@pytest.mark.django_db(transaction=True)
def test_award_approval_po_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0006_supplierquote_rfqscoringcriterion_and_more")])

    tables_after_reverse = set(connection.introspection.table_names())
    assert "award_decisions" not in tables_after_reverse
    assert "purchase_orders" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0007_awarddecision_approvalcase_awardline_purchaseorder_and_more")])

    tables_after_forward = set(connection.introspection.table_names())
    assert {
        "award_decisions",
        "award_lines",
        "approval_cases",
        "approval_steps",
        "purchase_orders",
        "purchase_order_items",
    } <= tables_after_forward


@pytest.mark.django_db(transaction=True)
def test_receiving_inventory_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0002_productcategory_product_description_and_more")])

    tables_after_reverse = set(connection.introspection.table_names())
    assert "goods_receipts" not in tables_after_reverse
    assert "inventory_movements" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0003_receiving_inventory_ledger")])

    tables_after_forward = set(connection.introspection.table_names())
    assert {
        "goods_receipts",
        "goods_receipt_items",
        "quality_inspections",
        "inventory_movements",
        "inventory_balances",
    } <= tables_after_forward


@pytest.mark.django_db(transaction=True)
def test_inspection_variance_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0004_legacy_receipt_actor_exception")])

    tables_after_reverse = set(connection.introspection.table_names())
    assert "inspection_variance_cases" not in tables_after_reverse
    assert "inspection_variance_lines" not in tables_after_reverse

    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0005_inspection_variances")])

    tables_after_forward = set(connection.introspection.table_names())
    assert {"inspection_variance_cases", "inspection_variance_lines"} <= tables_after_forward
    with connection.cursor() as cursor:
        receipt_item_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "goods_receipt_items"
            )
        }
        suggestion_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "purchase_suggestions"
            )
        }
    assert "replacement_variance_line_id" in receipt_item_columns
    assert {"source_movement_id", "purchase_request_id"} <= suggestion_columns


@pytest.mark.django_db(transaction=True)
def test_variance_status_transition_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0006_inspection_variance_comments")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('protect_submitted_variance_lines()'::regprocedure)"
        )
        reverse_definition = cursor.fetchone()[0]
    assert "allow only pending to completed transition" not in reverse_definition

    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0007_variance_line_status_transition")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('protect_submitted_variance_lines()'::regprocedure)"
        )
        forward_definition = cursor.fetchone()[0]
    assert "allow only pending to completed transition" in forward_definition


@pytest.mark.django_db(transaction=True)
def test_variance_close_guard_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0007_variance_line_status_transition")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('enforce_inspection_variance_case()'::regprocedure)"
        )
        reverse_definition = cursor.fetchone()[0]
    assert "all variance lines must be completed before closing" not in reverse_definition

    executor = MigrationExecutor(connection)
    executor.migrate([("erp", "0008_variance_case_close_guard")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('enforce_inspection_variance_case()'::regprocedure)"
        )
        forward_definition = cursor.fetchone()[0]
    assert "all variance lines must be completed before closing" in forward_definition


@pytest.mark.django_db(transaction=True)
def test_high_traffic_indexes_can_reverse_and_reapply_concurrently():
    index_names = {
        "pr_status_updated_idx",
        "rfq_status_due_idx",
        "rfq_supplier_queue_idx",
        "sq_status_valid_idx",
        "approval_step_queue_idx",
        "po_supplier_status_idx",
    }

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0007_awarddecision_approvalcase_awardline_purchaseorder_and_more")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND indexname = ANY(%s)",
            [list(index_names)],
        )
        assert {row[0] for row in cursor.fetchall()} == set()

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0008_concurrent_indexes")])

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() AND indexname = ANY(%s)",
            [list(index_names)],
        )
        assert {row[0] for row in cursor.fetchall()} == index_names


@pytest.mark.django_db(transaction=True)
def test_legacy_quote_backfill_is_reversible_and_does_not_double_inventory():
    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0008_concurrent_indexes")])
    old_apps = executor.loader.project_state(
        [("procurement", "0008_concurrent_indexes")]
    ).apps

    Role = old_apps.get_model("core", "Role")
    User = old_apps.get_model("core", "User")
    Supplier = old_apps.get_model("crm", "Supplier")
    Product = old_apps.get_model("erp", "Product")
    Quote = old_apps.get_model("procurement", "Quote")
    Approval = old_apps.get_model("procurement", "Approval")
    ApprovalPolicy = old_apps.get_model("procurement", "ApprovalPolicy")
    ApprovalPolicyStep = old_apps.get_model("procurement", "ApprovalPolicyStep")

    employee_role = Role.objects.create(role="migration_employee")
    approver_role = Role.objects.create(role="migration_approver")
    requester = User.objects.create(
        name="Migration Requester",
        email="migration-requester@example.invalid",
        password="not-a-real-password-hash",
        role=employee_role,
    )
    approver = User.objects.create(
        name="Migration Approver",
        email="migration-approver@example.invalid",
        password="not-a-real-password-hash",
        role=approver_role,
    )
    supplier = Supplier.objects.create(name="Migration Supplier")
    product = Product.objects.create(
        name="Migration Product", price="100.00", currency="TWD"
    )
    policy = ApprovalPolicy.objects.create(
        name="Migration Policy",
        currency="TWD",
        min_amount="0.00",
        max_amount=None,
        active_from="2020-01-01T00:00:00Z",
    )
    ApprovalPolicyStep.objects.create(
        policy=policy, sequence=1, role=approver_role, decision_mode="any_one"
    )
    approved = Quote.objects.create(
        user=requester,
        supplier=supplier,
        product=product,
        quantity=2,
        price="100.00",
        total_amount="200.00",
        currency="TWD",
        status="approved",
    )
    pending = Quote.objects.create(
        user=requester,
        supplier=supplier,
        product=product,
        quantity=3,
        price="100.00",
        total_amount="300.00",
        currency="TWD",
        status="pending_approval",
    )
    pending_verification = Quote.objects.create(
        user=requester, supplier=supplier, product=product, quantity=1,
        price="100.00", total_amount="100.00", currency="TWD",
        status="pending_verification",
    )
    pending_review = Quote.objects.create(
        user=requester, supplier=supplier, product=product, quantity=1,
        price="100.00", total_amount="100.00", currency="TWD",
        status="pending_review",
    )
    rejected = Quote.objects.create(
        user=requester, supplier=supplier, product=product, quantity=1,
        price="100.00", total_amount="100.00", currency="TWD",
        status="rejected",
    )
    cancelled = Quote.objects.create(
        user=requester, supplier=supplier, product=product, quantity=1,
        price="100.00", total_amount="100.00", currency="TWD",
        status="cancelled",
    )
    Approval.objects.create(
        quote=pending,
        role=approver_role,
        approval_level="small",
        status="pending",
    )
    Approval.objects.create(
        quote=rejected,
        role=approver_role,
        approver=approver,
        approval_level="small",
        status="rejected",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0009_backfill_legacy_quotes")])
    new_apps = executor.loader.project_state(
        [("procurement", "0009_backfill_legacy_quotes")]
    ).apps

    PurchaseRequest = new_apps.get_model("procurement", "PurchaseRequest")
    ApprovalCase = new_apps.get_model("procurement", "ApprovalCase")
    ApprovalStep = new_apps.get_model("procurement", "ApprovalStep")
    GoodsReceipt = new_apps.get_model("erp", "GoodsReceipt")
    InventoryMovement = new_apps.get_model("erp", "InventoryMovement")
    InventoryBalance = new_apps.get_model("erp", "InventoryBalance")

    assert PurchaseRequest.objects.filter(legacy_quote_id__isnull=False).count() == 6
    assert PurchaseRequest.objects.get(legacy_quote_id=pending_verification.id).status == "sourcing"
    assert PurchaseRequest.objects.get(legacy_quote_id=pending_review.id).status == "sourcing"
    assert PurchaseRequest.objects.get(legacy_quote_id=pending.id).status == "approval"
    assert PurchaseRequest.objects.get(legacy_quote_id=approved.id).status == "completed"
    assert PurchaseRequest.objects.get(legacy_quote_id=rejected.id).status == "cancelled"
    assert PurchaseRequest.objects.get(legacy_quote_id=cancelled.id).status == "cancelled"
    approved_case = ApprovalCase.objects.get(award__rfq__request__legacy_quote_id=approved.id)
    assert approved_case.status == "approved"
    assert approved_case.policy_snapshot["legacy_approval_record_missing"] is True
    assert not ApprovalStep.objects.filter(approval_case=approved_case).exists()
    assert ApprovalStep.objects.get(
        approval_case__award__rfq__request__legacy_quote_id=pending.id
    ).status == "pending"
    assert GoodsReceipt.objects.get(legacy_quote_id=approved.id).received_by_id is None
    movement = InventoryMovement.objects.get(movement_type="migration_assumed_receipt")
    assert movement.affects_balance is False
    assert not InventoryBalance.objects.filter(product_id=product.id).exists()

    migration_module = importlib.import_module(
        "apps.procurement.migrations.0009_backfill_legacy_quotes"
    )
    with connection.schema_editor() as schema_editor:
        migration_module.forwards(new_apps, schema_editor)
    assert PurchaseRequest.objects.filter(legacy_quote_id__isnull=False).count() == 6

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0008_concurrent_indexes")])
    reversed_apps = executor.loader.project_state(
        [("procurement", "0008_concurrent_indexes")]
    ).apps
    assert reversed_apps.get_model("procurement", "Quote").objects.count() == 6
    assert reversed_apps.get_model("procurement", "PurchaseRequest").objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_approval_waiver_steps_migration_can_reverse_and_reapply():
    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0009_backfill_legacy_quotes")])

    with connection.cursor() as cursor:
        approval_policy_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "approval_policies")
        }
        approval_step_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "approval_steps")
        }
    assert "waiver_role_id" not in approval_policy_columns
    assert "step_type" not in approval_step_columns
    assert "approval_step_waivers" not in connection.introspection.table_names()

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0010_approval_waiver_steps")])

    with connection.cursor() as cursor:
        approval_policy_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "approval_policies")
        }
        approval_step_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "approval_steps")
        }
    assert "waiver_role_id" in approval_policy_columns
    assert "step_type" in approval_step_columns
    assert "approval_step_waivers" in connection.introspection.table_names()


@pytest.mark.django_db(transaction=True)
def test_purchase_request_rejected_status_migration_can_reverse_and_reapply():
    def status_constraint():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'purchase_requests_status_check'
                """
            )
            return cursor.fetchone()[0]

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0010_approval_waiver_steps")])
    assert "rejected" not in status_constraint()

    executor = MigrationExecutor(connection)
    executor.migrate([("procurement", "0011_purchase_request_rejected_status")])
    assert "rejected" in status_constraint()

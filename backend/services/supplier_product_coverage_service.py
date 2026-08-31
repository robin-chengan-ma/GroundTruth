"""建立採購草稿前的供應商 × 品項供應能力唯讀矩陣。"""
from decimal import Decimal, InvalidOperation

from repositories.procurement import PurchaseRequestRepository


class SupplierProductCoverageError(Exception):
    code = "invalid_coverage_request"


def _positive_quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SupplierProductCoverageError("品項數量必須大於 0") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise SupplierProductCoverageError("品項數量必須大於 0")
    return quantity


def build_supplier_product_coverage(payload):
    supplier_ids = payload.get("supplier_ids")
    item_rows = payload.get("items")
    if not isinstance(supplier_ids, list) or not isinstance(item_rows, list):
        raise SupplierProductCoverageError("供應商與品項格式不正確")

    currency = str(payload.get("currency") or "TWD").strip().upper()
    suppliers = {
        supplier.id: supplier
        for supplier in PurchaseRequestRepository.active_suppliers(supplier_ids)
    }
    requested_items = []
    for row in item_rows:
        if not isinstance(row, dict):
            raise SupplierProductCoverageError("品項格式不正確")
        product_id = row.get("product_id")
        if product_id in (None, ""):
            continue
        requested_items.append((int(product_id), _positive_quantity(row.get("quantity"))))
    products = {
        product.id: product
        for product in PurchaseRequestRepository.active_products(
            [product_id for product_id, _ in requested_items],
        )
    }

    rows = []
    for product_id, quantity in requested_items:
        product = products.get(product_id)
        if product is None:
            continue
        for supplier_id in supplier_ids:
            supplier = suppliers.get(supplier_id)
            if supplier is None:
                continue
            relation = PurchaseRequestRepository.supplier_product(
                supplier_id=supplier_id, product_id=product_id,
            )
            price = None
            if relation and relation.is_active and relation.quality_status != "blocked":
                price = PurchaseRequestRepository.active_price(
                    supplier_id=supplier_id,
                    product_id=product_id,
                    quantity=quantity,
                    currency=currency,
                )

            if relation is None:
                coverage_status, label = "not_configured", "未建立供應關係"
            elif not relation.is_active:
                coverage_status, label = "inactive", "供應關係已停用"
            elif relation.quality_status == "blocked":
                coverage_status, label = "blocked", "品質資格禁止採購"
            elif relation.quality_status == "conditional":
                coverage_status = "conditional"
                label = "條件式合格，有有效價格" if price else "條件式合格，尚無有效價格"
            elif price is None:
                coverage_status, label = "unpriced", "有供應關係，但尚無有效價格"
            else:
                coverage_status, label = "priced", "可供應，且有有效價格"

            rows.append({
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "product_id": product.id,
                "product_name": product.name,
                "status": coverage_status,
                "label": label,
                "unit_price": format(price.unit_price, ".2f") if price else None,
                "currency": price.currency if price else currency,
            })
    return {"rows": rows}

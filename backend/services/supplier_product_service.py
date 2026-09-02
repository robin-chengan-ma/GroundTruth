"""Phase 5／FR-2／FR-16：供應商可供應品項與版本化價格主檔維護。

主檔只能啟用／停用（`is_active`），不得實體刪除；價格採版本控制，新版本一律用
新增，不得覆寫既有版本的價格內容，符合 FR-17「正式提交後不得原地修改」的精神
延伸到主檔價格版本。
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.crm.models import Supplier
from apps.erp.models import Product
from apps.procurement.models import SupplierPriceVersion, SupplierProduct
from repositories.procurement import SupplierProductRepository
from services.rbac_service import user_has_permission


class SupplierProductError(Exception):
    code = "invalid_supplier_product"


class SupplierProductPermissionDenied(SupplierProductError):
    code = "permission_denied"


class SupplierProductNotFound(SupplierProductError):
    code = "not_found"


class SupplierProductConflict(SupplierProductError):
    code = "conflict"


def _require_read_permission(user):
    if not user_has_permission(user, "master_data.read"):
        raise SupplierProductPermissionDenied("沒有讀取供應商品項主檔的權限")


def _require_manage_permission(user):
    if not user_has_permission(user, "master_data.manage"):
        raise SupplierProductPermissionDenied("沒有維護供應商品項主檔的權限")


def list_supplier_products(user):
    _require_read_permission(user)
    return SupplierProductRepository.all()


def get_supplier_product(user, pk):
    _require_read_permission(user)
    try:
        return SupplierProductRepository.get(pk)
    except ObjectDoesNotExist as exc:
        raise SupplierProductNotFound("找不到指定的供應商品項關係") from exc


def _decimal(value, field_name, *, positive=False, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise SupplierProductError(f"{field_name} 為必填")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SupplierProductError(f"{field_name} 必須是有效數字") from exc
    if not parsed.is_finite() or (positive and parsed <= 0) or (not positive and parsed < 0):
        raise SupplierProductError(f"{field_name} 數值不正確")
    return parsed


@transaction.atomic
def create_supplier_product(user, payload):
    _require_manage_permission(user)
    supplier_id = payload.get("supplier")
    product_id = payload.get("product")
    try:
        supplier = Supplier.objects.get(pk=supplier_id, is_active=True)
    except (Supplier.DoesNotExist, TypeError, ValueError) as exc:
        raise SupplierProductError("supplier 不存在或已停用") from exc
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except (Product.DoesNotExist, TypeError, ValueError) as exc:
        raise SupplierProductError("product 不存在或已停用") from exc
    lead_time_days = payload.get("lead_time_days", 0)
    try:
        lead_time_days = int(lead_time_days)
    except (TypeError, ValueError) as exc:
        raise SupplierProductError("lead_time_days 必須是整數") from exc
    if lead_time_days < 0:
        raise SupplierProductError("lead_time_days 不得為負數")
    moq = _decimal(payload.get("minimum_order_quantity", "1"), "minimum_order_quantity", positive=True)
    quality_status = str(payload.get("quality_status") or "qualified")
    if quality_status not in {"qualified", "conditional", "blocked"}:
        raise SupplierProductError("quality_status 不是有效值")
    try:
        supplier_product = SupplierProduct.objects.create(
            supplier=supplier,
            product=product,
            supplier_sku=str(payload.get("supplier_sku") or ""),
            lead_time_days=lead_time_days,
            minimum_order_quantity=moq,
            quality_status=quality_status,
        )
    except IntegrityError as exc:
        raise SupplierProductConflict("此供應商與品項的關係已存在") from exc
    return SupplierProductRepository.get(supplier_product.pk)


@transaction.atomic
def update_supplier_product(user, pk, payload):
    _require_manage_permission(user)
    try:
        supplier_product = SupplierProduct.objects.select_for_update().get(pk=pk)
    except ObjectDoesNotExist as exc:
        raise SupplierProductNotFound("找不到指定的供應商品項關係") from exc
    update_fields = []
    if "supplier_sku" in payload:
        supplier_product.supplier_sku = str(payload.get("supplier_sku") or "")
        update_fields.append("supplier_sku")
    if "lead_time_days" in payload:
        try:
            lead_time_days = int(payload.get("lead_time_days"))
        except (TypeError, ValueError) as exc:
            raise SupplierProductError("lead_time_days 必須是整數") from exc
        if lead_time_days < 0:
            raise SupplierProductError("lead_time_days 不得為負數")
        supplier_product.lead_time_days = lead_time_days
        update_fields.append("lead_time_days")
    if "minimum_order_quantity" in payload:
        supplier_product.minimum_order_quantity = _decimal(
            payload.get("minimum_order_quantity"), "minimum_order_quantity", positive=True,
        )
        update_fields.append("minimum_order_quantity")
    if "quality_status" in payload:
        quality_status = str(payload.get("quality_status") or "")
        if quality_status not in {"qualified", "conditional", "blocked"}:
            raise SupplierProductError("quality_status 不是有效值")
        supplier_product.quality_status = quality_status
        update_fields.append("quality_status")
    if "is_active" in payload:
        supplier_product.is_active = bool(payload.get("is_active"))
        update_fields.append("is_active")
    if not update_fields:
        raise SupplierProductError("沒有可更新的欄位")
    supplier_product.save(update_fields=update_fields)
    return SupplierProductRepository.get(pk)


@transaction.atomic
def add_price_version(user, supplier_product_id, payload):
    _require_manage_permission(user)
    try:
        supplier_product = SupplierProduct.objects.select_for_update().get(pk=supplier_product_id)
    except ObjectDoesNotExist as exc:
        raise SupplierProductNotFound("找不到指定的供應商品項關係") from exc
    unit_price = _decimal(payload.get("unit_price"), "unit_price")
    currency = str(payload.get("currency") or "TWD").upper()
    minimum_quantity = _decimal(
        payload.get("minimum_quantity", "1"), "minimum_quantity", positive=True,
    )
    valid_from_raw = payload.get("valid_from")
    valid_from = parse_datetime(str(valid_from_raw)) if valid_from_raw else timezone.now()
    if valid_from is None:
        raise SupplierProductError("valid_from 必須是有效日期時間")
    valid_until = None
    if payload.get("valid_until"):
        valid_until = parse_datetime(str(payload.get("valid_until")))
        if valid_until is None:
            raise SupplierProductError("valid_until 必須是有效日期時間")
        if valid_until <= valid_from:
            raise SupplierProductError("valid_until 必須晚於 valid_from")
    overlapping = SupplierProductRepository.overlapping_price_versions(
        supplier_product_id=supplier_product.pk,
        currency=currency,
        minimum_quantity=minimum_quantity,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    if overlapping.exists():
        raise SupplierProductConflict("此幣別與數量級距已有時間重疊的有效價格版本")
    try:
        SupplierPriceVersion.objects.create(
            supplier_product=supplier_product,
            unit_price=unit_price,
            currency=currency,
            minimum_quantity=minimum_quantity,
            valid_from=valid_from,
            valid_until=valid_until,
            created_by=user,
        )
    except IntegrityError as exc:
        raise SupplierProductError(str(exc)) from exc
    return SupplierProductRepository.get(supplier_product.pk)

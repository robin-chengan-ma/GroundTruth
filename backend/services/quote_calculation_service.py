"""FR-4／FR-4a：報價試算與歷史均價比對。

固定程式邏輯，LLM 不參與任何數字運算（NFR 可信度要求）。
`calculate_quote()` 只回傳計算結果（dict），不落地寫入 DB，供只想試算不建單的情境使用。
`create_quote()`（Phase 3 新增）在試算後正式建立 `Quote` 資料列——Phase 3 的幻覺驗證
（`quotes/verify-hallucination/`）需要一個真實存在的 `quote_id` 才能運作，Phase 2 當時
先只做試算，正式建單留到這裡補上（見 `docs/specs/PROGRESS.md` 已知待補）。
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist

from apps.procurement.models import Quote
from repositories.core import UserRepository
from repositories.erp import ProductRepository
from repositories.procurement import QuoteRepository

PRICE_DEVIATION_THRESHOLD_PCT = Decimal("20.00")  # 偏離超過此門檻標記價格異常（FR-4a，寫死於設定）


class QuoteCalculationError(Exception):
    """試算輸入有誤時拋出（例如產品不存在、數量非正整數）。"""


def calculate_quote(product_id, quantity, supplier_id=None):
    """依真實資料試算報價金額，並比對歷史均價。

    回傳：
        {
            "product_id": int,
            "supplier_id": int | None,
            "quantity": int,
            "unit_price": Decimal,
            "total_amount": Decimal,
            "currency": str,
            "price_deviation_pct": Decimal | None,
            "price_deviation_flag": bool,
        }
    """
    if not isinstance(quantity, int) or quantity <= 0:
        raise QuoteCalculationError("quantity 必須是正整數")

    try:
        product = ProductRepository.get(product_id)
    except ObjectDoesNotExist as exc:
        raise QuoteCalculationError("找不到指定的產品") from exc

    unit_price = product.price
    total_amount = (unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    price_deviation_pct = None
    price_deviation_flag = False
    if supplier_id is not None:
        price_deviation_pct = _calculate_price_deviation(supplier_id, product_id, unit_price)
        if price_deviation_pct is not None:
            price_deviation_flag = abs(price_deviation_pct) > PRICE_DEVIATION_THRESHOLD_PCT

    return {
        "product_id": product.id,
        "supplier_id": supplier_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_amount": total_amount,
        "currency": product.currency,
        "price_deviation_pct": price_deviation_pct,
        "price_deviation_flag": price_deviation_flag,
    }


def create_quote(*, user_id, product_id, quantity, supplier_id):
    """試算並正式建立 Quote 資料列（Phase 3：詢價主流程用這支，不是 calculate_quote()）。

    supplier_id 在這裡是必填——建立 Quote 一定要有供應商，跟 calculate_quote() 允許省略
    supplier_id（只是為了不比對歷史均價）語意不同。

    回傳：calculate_quote() 的原始欄位 + "quote_id"（新建立的 Quote 主鍵）。
    """
    if supplier_id is None:
        raise QuoteCalculationError("supplier_id 為必填（建立 Quote 需要指定供應商）")

    try:
        user = UserRepository.get(user_id)
    except ObjectDoesNotExist as exc:
        raise QuoteCalculationError("找不到指定的使用者") from exc

    result = calculate_quote(product_id=product_id, quantity=quantity, supplier_id=supplier_id)

    quote = Quote.objects.create(
        user=user,
        supplier_id=result["supplier_id"],
        product_id=result["product_id"],
        quantity=result["quantity"],
        price=result["unit_price"],
        total_amount=result["total_amount"],
        currency=result["currency"],
        status=Quote.Status.PENDING_VERIFICATION,
        price_deviation_pct=result["price_deviation_pct"],
    )

    result["quote_id"] = quote.id
    return result


def _calculate_price_deviation(supplier_id, product_id, current_unit_price):
    """該供應商＋該產品過去已核准採購單的平均單價，計算本次偏離百分比。
    無歷史紀錄則回傳 None（不視為異常，FR-4a）。
    """
    history = QuoteRepository.approved_history(supplier_id, product_id)
    prices = [q.price for q in history]
    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    if avg_price == 0:
        return None

    deviation = (current_unit_price - avg_price) / avg_price * Decimal("100")
    return deviation.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

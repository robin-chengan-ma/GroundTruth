"""FR-4／FR-4a：報價試算與歷史均價比對。

固定程式邏輯，LLM 不參與任何數字運算（NFR 可信度要求）。
這裡只回傳計算結果（dict），是否要寫入 DB 由呼叫端（api 層）決定，
Phase 2 範圍內先只回傳試算結果，不落地建立 Quote 紀錄（幻覺驗證與正式建單留待 Phase 3）。
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist

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

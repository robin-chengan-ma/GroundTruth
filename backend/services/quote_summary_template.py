"""FR-6a：幻覺驗證失敗案件經人工核准後，丟棄 LLM 生成的摘要文字，
改用固定樣板依真實數字組出文字（不再信任 LLM 這段敘述）。
"""


def render_summary(*, supplier_name, product_name, quantity, unit_price, total_amount, currency) -> str:
    return (
        f"【系統核定摘要，非 AI 原始生成內容】"
        f"供應商：{supplier_name}／產品：{product_name}／數量：{quantity}／"
        f"單價：{unit_price}／總金額：{total_amount} {currency}"
    )

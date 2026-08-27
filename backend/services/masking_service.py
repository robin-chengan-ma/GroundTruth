"""FR-2／NFR-1：資安遮罩層。

把使用者原始輸入中的「供應商名稱」「金額」換成 Token，送外部 LLM（Gemini）前先脫敏，
LLM 回應後再用 unmask_text 換回真實值。對應/遮罩表只存在記憶體（呼叫端變數）中，
依 NFR-1 絕不落地寫入 DB。

比對策略（已與使用者確認的 demo 合理標準，2026-08-27）：
1. 供應商名稱：
   - 先在全部供應商名稱中找「精確子字串」比對。
     - 剛好 1 筆命中 → 直接遮罩（outcome: "masked"）。
     - 0 筆命中 → 用 difflib.SequenceMatcher 做模糊比對（threshold 0.6，demo 合理標準）：
       - 有候選 → outcome: "supplier_fuzzy_match"，寫入 manual_review_queue
         （quote_id 為 null，此階段尚無 Quote；raw_input_text 保留原始輸入）。
         只有「剛好 1 筆候選，且比對到的片段長度沒有比供應商全名短太多（見下方長度保
         險）」時，才預填 `supplier`（系統建議值，仍須人工複核決議，不是最終答案）；
         其餘情況（多筆候選、或唯一候選但片段太短）一律讓 `supplier` 留空，交由人工從
         `candidates` 清單挑選。
       - 無候選 → outcome: "supplier_not_found"，不寫入 DB，直接回覆使用者。
   - 多筆精確命中視為歧義（無法判斷是哪一間），比照模糊比對流程走複核佇列，不猜測。
   - 長度保險（2026-08-27 補強，使用者提出）：像「生技」對到「保生技術」這種輸入片段
     很短、可能只是巧合命中的情況，即使相似度過門檻也不該直接當作高可信度的單一候選。
     用「最長連續相符子字串長度」（而非整個滑動視窗寬度，視窗寬度天生就貼近供應商全名
     長度，無法反映真正巧合命中的情況）去對照供應商全名長度，要求達
     LENGTH_SAFETY_RATIO（60%）以上才算「長度安全」；沒過這關的候選依然會出現在
     `candidates` 清單供人工參考，只是不會自動預填。
2. 金額：只遮罩「有金額語境」的數字（前後有 元／NT$／USD／TWD／$ 等關鍵字），
   刻意排除「20 個」這種數量詞，避免誤傷。
"""
import difflib
import re

from apps.audit.models import ManualReviewQueue
from repositories.crm import SupplierRepository

FUZZY_MATCH_THRESHOLD = 0.6  # demo 合理標準，非嚴謹統計門檻
LENGTH_SAFETY_RATIO = 0.6  # 命中片段長度須達供應商全名長度的此比例，才允許預填 supplier

# 有金額語境的數字：前綴貨幣符號/代碼，或後綴「元／塊」。
# 刻意不比對純數字＋「個／件／份／箱／組／台／次」等數量詞，避免誤把數量當金額遮罩。
_AMOUNT_PATTERN = re.compile(
    r"(?:NT\$|US\$|\$|TWD|USD)\s?\d[\d,]*(?:\.\d+)?"
    r"|\d[\d,]*(?:\.\d+)?\s?(?:元|塊錢|塊)"
)


class MaskingError(Exception):
    """遮罩流程輸入有誤時拋出（例如 raw_text 為空）。"""


def mask_text(raw_text: str, requester_id=None) -> dict:
    """遮罩使用者原始輸入。

    requester_id：詢價發起人。模糊比對案件會把它存進 `manual_review_queue.requester`，
    核准後才知道要用誰的身分重新建立 Quote（見 `services/inquiry_resume_service.py`）。

    回傳其中一種：
    - {"outcome": "masked", "masked_text": str, "mapping": {token: real_value}}
    - {"outcome": "supplier_fuzzy_match", "review_id": int, "candidates": [str, ...]}
    - {"outcome": "supplier_not_found", "masked_text": None, "mapping": {}}
    """
    if not raw_text or not raw_text.strip():
        raise MaskingError("raw_text 不可為空")

    suppliers = list(SupplierRepository.all())
    exact_matches = [s for s in suppliers if s.name and s.name in raw_text]

    if len(exact_matches) == 1:
        masked_text, mapping = _apply_masks(raw_text, exact_matches[0])
        return {"outcome": "masked", "masked_text": masked_text, "mapping": mapping}

    if len(exact_matches) > 1:
        # 多筆精確命中＝歧義，不猜測是哪一間，比照模糊比對流程走複核佇列。
        review = ManualReviewQueue.objects.create(
            quote=None,
            review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
            raw_input_text=raw_text,
            supplier=None,
            requester_id=requester_id,
        )
        return {
            "outcome": "supplier_fuzzy_match",
            "review_id": review.id,
            "candidates": [s.name for s in exact_matches],
        }

    # 0 筆精確命中 → 模糊比對
    candidates = _find_fuzzy_supplier_candidates(raw_text, suppliers)
    if not candidates:
        return {"outcome": "supplier_not_found", "masked_text": None, "mapping": {}}

    # 只有「剛好 1 筆候選」且該候選「長度安全」時才預填，其餘一律留空給人工判斷。
    best_supplier = None
    if len(candidates) == 1 and candidates[0][2]:
        best_supplier = candidates[0][0]

    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text=raw_text,
        supplier=best_supplier,
        requester_id=requester_id,
    )
    return {
        "outcome": "supplier_fuzzy_match",
        "review_id": review.id,
        "candidates": [s.name for s, _, _ in candidates],
    }


def mask_amounts_only(raw_text: str) -> dict:
    """FR-6a 模糊比對案件核准後續傳流程專用：供應商已由人工確認（走 supplier_id 直接
    帶給下游，不需要再靠文字比對／Token 化），這裡只需要照常規則遮罩金額，不處理供應商。

    回傳：{"masked_text": str, "mapping": {token: real_value}}
    """
    if not raw_text or not raw_text.strip():
        raise MaskingError("raw_text 不可為空")

    masked, mapping = _mask_amounts(raw_text)
    return {"masked_text": masked, "mapping": mapping}


def unmask_text(masked_text: str, mapping: dict) -> str:
    """把遮罩文字中的 Token 換回真實值（供 Gemini 回應後還原用）。"""
    if not masked_text:
        return masked_text
    result = masked_text
    # Token 名稱不會互為子字串（SUP_/AMOUNT_ 前綴不同），直接逐一取代即可。
    for token, real_value in mapping.items():
        result = result.replace(token, real_value)
    return result


def _find_fuzzy_supplier_candidates(raw_text: str, suppliers) -> list:
    """對每個供應商名稱，在 raw_text 上滑動視窗找最相似片段，
    回傳 [(supplier, ratio, length_safe), ...]（只含 ratio >= FUZZY_MATCH_THRESHOLD 的候選，
    依相似度由高到低排序）。

    length_safe：最佳命中位置的「最長連續相符子字串長度」是否達供應商全名長度的
    LENGTH_SAFETY_RATIO 以上——片段太短、只是巧合命中（例如「生技」對到「保生技術」，
    最長連續相符只有 2 字，佔全名 4 字的 50%），即使相似度過門檻，也不夠可信到能自動預填。
    """
    candidates = []
    for supplier in suppliers:
        name = supplier.name
        if not name:
            continue
        best_ratio, best_match_len = _best_match(raw_text, name)
        if best_ratio >= FUZZY_MATCH_THRESHOLD:
            length_safe = best_match_len >= LENGTH_SAFETY_RATIO * len(name)
            candidates.append((supplier, best_ratio, length_safe))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def _best_match(raw_text: str, name: str) -> tuple:
    """回傳 (best_ratio, best_match_len)：最相似片段的相似度，
    以及該片段與供應商全名之間「最長連續相符子字串」的長度。
    """
    name_len = len(name)
    best_ratio = 0.0
    best_match_len = 0
    # 視窗寬度：供應商名稱長度 -1 ~ +2，容忍使用者輸入略有增減字。
    for width in range(max(1, name_len - 1), name_len + 3):
        if width > len(raw_text):
            continue
        for start in range(0, len(raw_text) - width + 1):
            segment = raw_text[start:start + width]
            matcher = difflib.SequenceMatcher(None, segment, name)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                longest = matcher.find_longest_match(0, len(segment), 0, name_len)
                best_match_len = longest.size
    return best_ratio, best_match_len


def _apply_masks(raw_text: str, supplier) -> tuple:
    masked = raw_text.replace(supplier.name, "SUP_001")
    masked, mapping = _mask_amounts(masked)
    mapping["SUP_001"] = supplier.name
    return masked, mapping


def _mask_amounts(text: str) -> tuple:
    """把有金額語境的數字換成 AMOUNT_NNN token，回傳 (masked_text, mapping)。"""
    mapping = {}
    masked = text

    seen_amounts = []
    for match in _AMOUNT_PATTERN.finditer(masked):
        amount_text = match.group(0)
        if amount_text not in seen_amounts:
            seen_amounts.append(amount_text)

    for idx, amount_text in enumerate(seen_amounts, start=1):
        token = f"AMOUNT_{idx:03d}"
        masked = masked.replace(amount_text, token)
        mapping[token] = amount_text

    return masked, mapping

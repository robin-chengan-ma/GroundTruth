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
_SUPPLIER_CLAUSE_PATTERN = re.compile(
    r"(?:跟|向|找|由)\s*(?P<names>[^，。；\n]+?)\s*(?:詢價|採購|購買|買|訂購|拿貨)"
)
_SUPPLIER_SEPARATOR_PATTERN = re.compile(r"[\s、,，和與及/&]+")


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


def mask_confirmed_supplier_text(raw_text: str, supplier) -> dict:
    """FR-6a 人工複核核准 supplier_fuzzy_match 案件後續傳流程專用（2026-09-02 改版，
    見 docs/ADR/debug/phase5-security.md）：供應商已由人工確認，不需要也不應該再重新跑
    模糊比對（會又繞回複核佇列造成無限迴圈）。

    優先找 raw_text 中與供應商全名「精確子字串」相符的片段直接遮罩；找不到精確命中
    （例如使用者原始輸入本來就是打錯字、才會落入模糊比對複核）時，改用 `_best_match`
    找出的最相似片段位置做替換——這裡不再用 FUZZY_MATCH_THRESHOLD／LENGTH_SAFETY_RATIO
    篩選是否要「自動預填」，因為供應商身分已經是人工確認過的事實，不是待判斷的候選。

    找不到任何足以定位的相似片段時（極端情況，例如 raw_text 遠短於供應商全名）直接
    拋出 `MaskingError`，中止這次續傳，而不是把真實供應商名稱原封不動送給外部 LLM
    ——NFR-1「送往 LLM 的內容必須先脫敏」沒有例外，fail-closed 優於 fail-open
    （2026-09-02 修正：Codex 審查發現原本會 fail-open，見
    `docs/ADR/debug/phase5-security.md`）。呼叫端（`inquiry_service.resolve_candidate_after_manual_review`）
    會把這個例外轉換成專屬子類別 `InquiryUnmaskableSupplierError`，`inquiry_resume_service.trigger_resume`
    再把它對應到獨立的 `RESUME_ERROR_UNMASKABLE_SUPPLIER` 錯誤代碼並落地保存，交管理員人工確認或重試，
    不影響已提交的複核決議。

    回傳：{"masked_text": str, "mapping": {token: real_value}}（結構比照 mask_amounts_only，
    供呼叫端後續送進既有候選解析 n8n webhook）。
    """
    if not raw_text or not raw_text.strip():
        raise MaskingError("raw_text 不可為空")
    if supplier is None or not supplier.name:
        raise MaskingError("supplier 不可為空")

    name = supplier.name
    if name in raw_text:
        start = raw_text.index(name)
        end = start + len(name)
    else:
        _ratio, _match_len, span = _best_match(raw_text, name)
        start, end = span or (None, None)

    if start is None:
        raise MaskingError("找不到可定位的供應商片段，無法安全遮罩後續傳送 AI 解析")

    masked = raw_text[:start] + "SUP_001" + raw_text[end:]
    masked, mapping = _mask_amounts(masked)
    mapping["SUP_001"] = name
    return {"masked_text": masked, "mapping": mapping}


def mask_amounts_only(raw_text: str) -> dict:
    """FR-6a 模糊比對案件核准後續傳流程專用：供應商已由人工確認（走 supplier_id 直接
    帶給下游，不需要再靠文字比對／Token 化），這裡只需要照常規則遮罩金額，不處理供應商。

    回傳：{"masked_text": str, "mapping": {token: real_value}}
    """
    if not raw_text or not raw_text.strip():
        raise MaskingError("raw_text 不可為空")

    masked, mapping = _mask_amounts(raw_text)
    return {"masked_text": masked, "mapping": mapping}


def mask_candidate_text(raw_text: str, requester_id=None) -> dict:
    """遮罩新版採購需求候選解析文字，支援同時指定多間已知供應商。

    legacy `mask_text` 的多筆精確命中代表單一供應商流程存在歧義；新版需求本來就允許
    多候選供應商，因此會將文字中所有完整命中的供應商分別 Token 化。完全沒有精確命中時，
    才沿用既有模糊比對／查無供應商分流，避免把無法確認的名稱送往外部 LLM。
    """
    if not raw_text or not raw_text.strip():
        raise MaskingError("raw_text 不可為空")

    suppliers = [supplier for supplier in SupplierRepository.all() if supplier.name]
    exact_matches = [supplier for supplier in suppliers if supplier.name in raw_text]
    if not exact_matches:
        return mask_text(raw_text, requester_id=requester_id)
    if _has_unmatched_supplier_clause(raw_text, exact_matches):
        return {"outcome": "supplier_not_found", "masked_text": None, "mapping": {}}

    # 先處理較長名稱，避免供應商名稱互為子字串時短名稱先取代而洩漏剩餘文字。
    exact_matches.sort(key=lambda supplier: (-len(supplier.name), supplier.id))
    masked_text = raw_text
    mapping = {}
    for index, supplier in enumerate(exact_matches, start=1):
        token = f"SUP_{index:03d}"
        masked_text = masked_text.replace(supplier.name, token)
        mapping[token] = supplier.name

    masked_text, amount_mapping = _mask_amounts(masked_text)
    mapping.update(amount_mapping)
    return {"outcome": "masked", "masked_text": masked_text, "mapping": mapping}


def _has_unmatched_supplier_clause(raw_text: str, exact_matches) -> bool:
    """保守檢查顯式供應商片段，避免已知與未知供應商混寫時讓未知名稱外洩。"""
    for clause_match in _SUPPLIER_CLAUSE_PATTERN.finditer(raw_text):
        remaining = clause_match.group("names")
        for supplier in exact_matches:
            remaining = remaining.replace(supplier.name, "")
        if _SUPPLIER_SEPARATOR_PATTERN.sub("", remaining):
            return True
    return False


def unmask_text(masked_text: str, mapping: dict) -> str:
    """把遮罩文字中的 Token 換回真實值（供 Gemini 回應後還原用）。"""
    if not masked_text:
        return masked_text
    result = masked_text
    # Token 名稱不會互為子字串（SUP_/AMOUNT_ 前綴不同），直接逐一取代即可。
    for token, real_value in mapping.items():
        result = result.replace(token, real_value)
    return result


def unmask_payload(value, mapping: dict):
    """遞迴還原 n8n 候選 payload 內所有字串，不修改數字、布林或空值。"""
    if isinstance(value, str):
        return unmask_text(value, mapping)
    if isinstance(value, list):
        return [unmask_payload(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: unmask_payload(item, mapping) for key, item in value.items()}
    return value


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
        best_ratio, best_match_len, _span = _best_match(raw_text, name)
        if best_ratio >= FUZZY_MATCH_THRESHOLD:
            length_safe = best_match_len >= LENGTH_SAFETY_RATIO * len(name)
            candidates.append((supplier, best_ratio, length_safe))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def _best_match(raw_text: str, name: str) -> tuple:
    """回傳 (best_ratio, best_match_len, best_span)：最相似片段的相似度、
    該片段與供應商全名之間「最長連續相符子字串」的長度，以及該片段在 raw_text 中的
    位置 `(start, end)`（找不到任何候選視窗時為 None——目前只有 raw_text 短到所有
    視窗寬度都超過其長度時才會發生，見 raw_text 短於供應商名稱長度的邊界情況）。

    best_span 是給 `mask_confirmed_supplier_text` 用來精確替換原文片段；
    `_find_fuzzy_supplier_candidates` 沿用既有邏輯，不需要用到位置。
    """
    name_len = len(name)
    best_ratio = 0.0
    best_match_len = 0
    best_span = None
    # 視窗寬度：供應商名稱長度 -1 ~ +2，容忍使用者輸入略有增減字。
    for width in range(max(1, name_len - 1), name_len + 3):
        if width > len(raw_text):
            continue
        for start in range(len(raw_text) - width + 1):
            segment = raw_text[start:start + width]
            matcher = difflib.SequenceMatcher(None, segment, name)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                longest = matcher.find_longest_match(0, len(segment), 0, name_len)
                best_match_len = longest.size
                best_span = (start, start + width)
    return best_ratio, best_match_len, best_span


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

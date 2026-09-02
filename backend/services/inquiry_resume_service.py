"""FR-6a：供應商模糊比對案件核准後，重新解析原始需求並嘗試自動建立採購需求草稿。

2026-09-02 改版（見 docs/ADR/debug/phase5-security.md「Codex 程式碼審查發現 Phase 5
『正式完成』有 3 個實質破口」條目，破口①）：原本核准後會呼叫 n8n 續傳 webhook
（`N8N_RESUME_WEBHOOK_URL`），但該 webhook 內部節點呼叫的是已於 Phase 5 退場的 legacy
`/quotes/calculate/`／`/quotes/verify-hallucination/` 端點（現在一律回 410），核准後其實
無法真的把候選解析出來、也不會建立任何單據——這條路徑實質上是壞的。

改為 Django 直接呼叫，略過 n8n 續傳 webhook（Robin 2026-09-02 決策）：
- 供應商已由人工確認，直接在 Django 內用 `mask_confirmed_supplier_text` 重新遮罩
  （不再重新跑模糊比對，避免又繞回複核佇列造成無限迴圈），呼叫既有的候選解析
  n8n webhook（與 `InquiryCandidateParseView` 共用同一個 v2 pure-parse 端點）解析品項。
- 解析成功且無缺漏欄位（`ready_for_draft=True`）時，自動建立 `PurchaseRequest` 草稿
  （比照 `purchase_suggestion_service.convert_to_draft` 的做法，`source` 標記為
  `manual_review_resume`），發起人可在「我的採購需求」看到並自行編輯提交。
- 解析失敗（格式錯誤、AI 需求解析服務連線失敗等）或仍有缺漏欄位時，不建立草稿，
  回傳 `None`，交由管理員人工確認（呼叫端 `manual_review_service.decide_review()`
  會據此把 `resume_triggered` 設為 `False`）。

呼叫時機：`services/manual_review_service.decide_review()` 核准 supplier_fuzzy_match
案件、DB 交易成功提交「之後」才呼叫（維持原本設計：外部/耗時呼叫不包在 DB transaction
裡；決議結果本身已經落地 DB，不因為這裡失敗而回滾）。`retry_resume()` 重試同一案件時
也是呼叫同一支函式。

2026-09-02 二次改版（見 docs/ADR/discuss/main-flow.md「持久化續傳狀態與重試」條目、
docs/ADR/debug/phase5-security.md）：回傳值從單純的 `PurchaseRequest | None` 改成
`(draft, error_code)` tuple，讓呼叫端能把失敗原因（非敏感錯誤代碼，不含原始例外訊息或
供應商名稱）落地寫進 `manual_review_queue.resume_error_code`，管理員事後才看得出「到底
是哪一種失敗」並決定要不要重試。成功時 `error_code` 固定為 `None`；失敗時 `draft` 固定
為 `None`。
"""
from apps.core.models import User
from apps.crm.models import Supplier
from repositories.core import UserRepository
from repositories.crm import SupplierRepository
from services.inquiry_service import (
    InquiryTriggerError,
    InquiryUnmaskableSupplierError,
    InquiryValidationError,
    resolve_candidate_after_manual_review,
)
from services.purchase_request_draft_service import DraftError, DraftPermissionDenied, create_draft

# resume_error_code 合法值：只給管理員判斷失敗類型與是否可重試用，不得含原始例外訊息、
# 供應商名稱或其他敏感內容。
RESUME_ERROR_INVALID_INPUT = "invalid_input"
RESUME_ERROR_UNMASKABLE_SUPPLIER = "unmaskable_supplier"
RESUME_ERROR_PARSE_FAILED = "parse_failed"
RESUME_ERROR_MISSING_FIELDS = "missing_fields"
RESUME_ERROR_PERMISSION_DENIED = "permission_denied"
RESUME_ERROR_DRAFT_CREATION_FAILED = "draft_creation_failed"
RESUME_ERROR_DATA_INTEGRITY = "resume_data_error"


class InquiryResumeError(Exception):
    """找不到已確認的供應商／原始發起人等資料整合性問題時拋出。呼叫端不應讓此中斷
    已提交的決議——AI 解析失敗或缺漏欄位是正常的預期結果，不會走這個例外（見
    `trigger_resume` 回傳 `(None, error_code)` 的情況），這裡只保留給資料本身有問題、
    理論上不該發生的情況（呼叫端會對應到 `RESUME_ERROR_DATA_INTEGRITY`）。"""


def trigger_resume(*, review_id, raw_input_text, requester_id, supplier_id):
    """供應商已由人工確認，直接在 Django 內重新解析原始需求；解析成功且無缺漏欄位時
    自動建立採購需求草稿並回傳 `(draft, None)`，否則回傳 `(None, error_code)`。

    `review_id` 目前只用於保留呼叫介面與既有呼叫端一致（供未來稽核紀錄關聯用），
    尚未寫入草稿本身。
    """
    try:
        supplier = SupplierRepository.get(supplier_id)
    except Supplier.DoesNotExist as exc:
        raise InquiryResumeError("找不到已確認的供應商") from exc
    try:
        requester = UserRepository.get(requester_id)
    except User.DoesNotExist as exc:
        raise InquiryResumeError("找不到原始詢價發起人") from exc

    try:
        candidate = resolve_candidate_after_manual_review(
            raw_input_text, supplier=supplier, requester_id=requester_id,
        )
    except InquiryUnmaskableSupplierError:
        # 找不到可定位的供應商片段：fail-closed，不阻斷決議，回傳非敏感錯誤代碼讓
        # 管理員人工確認（不含原始例外訊息或供應商名稱）。
        return None, RESUME_ERROR_UNMASKABLE_SUPPLIER
    except InquiryValidationError:
        # 原始輸入本身有問題（例如空白）：不阻斷決議，回傳 None 讓管理員人工確認。
        return None, RESUME_ERROR_INVALID_INPUT
    except InquiryTriggerError:
        # AI 需求解析服務逾時/連線失敗/回傳格式錯誤：屬於暫時性問題，可重試。
        return None, RESUME_ERROR_PARSE_FAILED

    if not candidate["ready_for_draft"]:
        return None, RESUME_ERROR_MISSING_FIELDS

    try:
        draft = create_draft(requester, {
            "items": [
                {
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "specifications": item["specifications"],
                    "unit_of_measure": item["unit_of_measure"],
                }
                for item in candidate["items"]
            ],
            "supplier_ids": [supplier.id],
            "purpose": candidate["purpose"],
            "needed_by": candidate["needed_by"],
            "currency": candidate["currency"],
        })
    except DraftPermissionDenied:
        # 發起人沒有（或已被收回）purchase_request.create 權限：不阻斷決議，回傳
        # 非敏感錯誤代碼讓管理員人工確認。
        return None, RESUME_ERROR_PERMISSION_DENIED
    except DraftError:
        # 例如品項/供應商在建立當下剛好被停用：不阻斷決議，回傳 None 讓管理員人工確認。
        return None, RESUME_ERROR_DRAFT_CREATION_FAILED

    draft.source = "manual_review_resume"
    draft.save(update_fields=["source", "updated_at"])
    return draft, None

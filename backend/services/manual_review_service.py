"""FR-6a／FR-6b／FR-6c：待人工複核佇列的認領與決議。

固定程式邏輯（不是 AI 判斷）：
- 認領：防止多位管理員同時處理同一案件，已認領/已結案的案件回報衝突（API 409）。
- 決議：依 review_type 分流（FR-6a 定義的有限選項，不開放自由編輯 AI 生成內容後放行）：
  - hallucination_mismatch：核准＝丟棄 LLM 摘要、改用系統制式模板、Quote 進入待簽核；
    駁回＝詢價作廢（Quote 取消），通知申請人重新送出（Gmail 通知留待 n8n 串接）。
  - supplier_fuzzy_match：核准＝確認供應商身分，交還 n8n 重新走遮罩→LLM 解析流程；
    駁回＝通知申請人確認供應商全名後重新送出。此案件在 Mask 節點階段就中止，尚無 Quote，
    不能跳過解析直接查詢報價（見 docs/ADR/discuss/main-flow.md）。
- 每個決定都寫入稽核 log（FR-6c）。
"""
from django.db import transaction

from apps.audit.models import AuditLog, ManualReviewQueue
from apps.core.models import User
from repositories.core import UserRepository
from services.inquiry_resume_service import InquiryResumeError, trigger_resume
from services.rbac_service import user_has_permission


class ManualReviewError(Exception):
    """複核流程輸入或狀態有誤時拋出（對應 API 400）。"""


class ManualReviewConflictError(ManualReviewError):
    """案件已被認領、已結案，或非本人認領時拋出（對應 API 409）。"""


class LegacyManualReviewRetiredError(ManualReviewError):
    """歷史複核案件僅供查閱，不得再推進 legacy Quote。"""


def claim_review(review_id, user_id) -> ManualReviewQueue:
    review = _get_review(review_id)
    _ensure_active_review(review)
    user = _get_authorized_user(user_id, "manual_review.claim")

    if review.status != ManualReviewQueue.Status.UNCLAIMED:
        raise ManualReviewConflictError("此案件已被認領或已結案")

    review.status = ManualReviewQueue.Status.CLAIMED
    review.user = user
    review.save(update_fields=["status", "user", "updated_at"])
    return review


def decide_review(review_id, user_id, decision, supplier_id=None) -> ManualReviewQueue:
    if decision not in (ManualReviewQueue.Decision.APPROVED, ManualReviewQueue.Decision.REJECTED):
        raise ManualReviewError("decision 必須是 approved 或 rejected")

    review = _get_review(review_id)
    _ensure_active_review(review)
    user = _get_authorized_user(user_id, "manual_review.decide")

    if review.status != ManualReviewQueue.Status.CLAIMED:
        raise ManualReviewConflictError("此案件尚未認領或已結案，無法決議")

    # 用查回來的 user.id（一定是 int）比對，避免呼叫端傳字串型別的 user_id 時誤判。
    if review.user_id != user.id:
        raise ManualReviewConflictError("只有認領此案件的使用者可以決議")

    with transaction.atomic():
        _decide_supplier_fuzzy_match(review, decision, supplier_id)

        review.status = ManualReviewQueue.Status.RESOLVED
        review.decision = decision
        review.save(update_fields=["status", "decision", "updated_at"])

        AuditLog.objects.create(
            user_id=user.id,
            action_type="review_decision",
            quote=review.quote,
            verification_result=decision,
        )

    # 交易確定提交後才對外呼叫 n8n——DB 決議結果是真的，不因為外部呼叫失敗而回滾。
    if (
        review.review_type == ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH
        and decision == ManualReviewQueue.Decision.APPROVED
    ):
        review.resume_triggered = True
        try:
            trigger_resume(
                review_id=review.id,
                raw_input_text=review.raw_input_text,
                requester_id=review.requester_id,
                supplier_id=review.supplier_id,
            )
        except InquiryResumeError:
            # 決議本身已經成功落地，通知 n8n 失敗不推翻決議；記錄下來讓管理員知道要
            # 手動確認流程有沒有真的續傳（demo 範圍的已知限制，見 PROGRESS.md）。
            review.resume_triggered = False

    return review


def _decide_supplier_fuzzy_match(review: ManualReviewQueue, decision: str, supplier_id) -> None:
    if decision != ManualReviewQueue.Decision.APPROVED:
        return  # 駁回：不需要異動供應商欄位，通知申請人重新送出由 n8n／Gmail 串接負責。

    if supplier_id is not None:
        review.supplier_id = supplier_id
    if review.supplier_id is None:
        raise ManualReviewError("核准模糊比對案件時必須指定 supplier_id")
    review.save(update_fields=["supplier"])
    # 核准後交還 n8n（實際的 webhook 呼叫在 decide_review() 的交易提交之後執行，
    # 見 services/inquiry_resume_service.trigger_resume()）：n8n 收到 raw_input_text ＋
    # 已確認的 supplier_id，重新走一次遮罩→LLM 解析流程（此階段品項/數量/幣別仍未解析）。


def _get_review(review_id) -> ManualReviewQueue:
    try:
        return ManualReviewQueue.objects.select_related("quote", "supplier", "user").get(pk=review_id)
    except ManualReviewQueue.DoesNotExist as exc:
        raise ManualReviewError("找不到指定的複核案件") from exc


def _ensure_active_review(review: ManualReviewQueue) -> None:
    if review.review_type == ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH:
        raise LegacyManualReviewRetiredError("舊版幻覺複核案件僅供歷史查閱")


def _get_authorized_user(user_id, permission_code) -> User:
    """FR-6a：依權限能力授權，不以 admin 角色名稱推測業務權限。"""
    try:
        user = UserRepository.get(user_id)
    except User.DoesNotExist as exc:
        raise ManualReviewError("找不到指定的使用者") from exc

    if not user_has_permission(user, permission_code):
        raise ManualReviewError("沒有處理人工複核案件的權限")

    return user

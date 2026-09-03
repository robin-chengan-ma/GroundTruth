"""FR-6b／FR-8：Gmail 通知。

分工原則（AGENTS.md「業務邏輯都寫在 Django，n8n 只做串接與流程控制」）：收件人清單
（哪些使用者目前持有指定角色／權限碼）與信件標題、內文組裝全部在 Django 這裡完成；
n8n 端只收 `{subject, body, recipients, link}` 呼叫 Gmail 節點寄出，不做任何業務判斷。

呼叫失敗（連線問題、逾時、非 2xx）為 best-effort，不拋出例外、不影響呼叫端已提交的
正式決議或案件建立——比照既有 `inquiry_resume_service.trigger_resume` 的原則：外部
系統暫時不可用不該讓已經確認為真的資料庫異動被回滾。呼叫端可用回傳值知道是否成功
送出，若需要可自行記錄或顯示提示，目前呼叫端（masking_service／views）皆未強制要求
成功。

呼叫時機皆刻意放在資料庫交易「已提交」之後才呼叫（避免把耗時的外部 HTTP 呼叫包進
交易），詳見各呼叫點註解：
- `services/masking_service.py`：建立 `ManualReviewQueue` 之後（未包在 transaction 內）
- `api/procurement/views.py`：`submit_award()`／`decide_step()` 皆為
  `@transaction.atomic`，通知放在 view 層、service 呼叫成功返回（交易已提交）之後
"""
import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.models import User

NOTIFY_TIMEOUT_SECONDS = 10


def _active_users_query(**role_filter):
    now = timezone.now()
    return (
        User.objects.filter(**role_filter)
        .filter(user_roles__valid_from__lte=now)
        .filter(Q(user_roles__valid_until__isnull=True) | Q(user_roles__valid_until__gt=now))
        .values_list("email", flat=True)
        .distinct()
    )


def _active_recipients_for_permission(permission_code: str) -> list:
    """回傳目前生效角色具有該權限碼的所有使用者 email（去重）。"""
    return sorted(
        _active_users_query(user_roles__role__role_permissions__permission__code=permission_code)
    )


def _active_recipients_for_role(role_id) -> list:
    """回傳目前持有該角色的所有使用者 email（去重）。"""
    return sorted(_active_users_query(user_roles__role_id=role_id))


def _send_notification(*, subject: str, body: str, recipients: list, link: str = "") -> bool:
    """POST 到 n8n 通知 webhook；best-effort，失敗只回傳 False，不拋例外中斷呼叫端。"""
    if not recipients:
        return False
    try:
        response = requests.post(
            settings.N8N_NOTIFY_WEBHOOK_URL,
            json={"subject": subject, "body": body, "recipients": recipients, "link": link},
            headers={"X-Internal-Api-Key": settings.INTERNAL_API_KEY},
            timeout=NOTIFY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def _frontend_link(path: str) -> str:
    """組出前端頁面完整連結；`FRONTEND_BASE_URL` 未設定時退回空字串（信件仍可寄出，只是不附連結）。"""
    base = getattr(settings, "FRONTEND_BASE_URL", "") or ""
    if not base:
        return ""
    return f"{base.rstrip('/')}{path}"


def notify_manual_review_created(review) -> bool:
    """FR-6b：複核案件建立後，通知所有具 `manual_review.decide` 權限的使用者，並附上複核佇列連結。"""
    recipients = _active_recipients_for_permission("manual_review.decide")
    subject = f"【待複核】供應商比對案件 #{review.id} 待確認"
    body = (
        f"有一筆詢價需要人工複核供應商身分（案件編號 #{review.id}），"
        "請登入系統前往人工複核佇列認領處理。任一管理員皆可認領，"
        "認領後其他管理員會看到處理中狀態，避免重複處理。"
    )
    return _send_notification(
        subject=subject, body=body, recipients=recipients, link=_frontend_link("/reviews")
    )


def notify_manual_review_rejected(review) -> bool:
    """人工複核案件遭駁回時通知原始申請人（Robin 2026-09-03 決策：問題三「駁回不會通知
    申請人」修復）。supplier_fuzzy_match 案件此時尚未建立任何 PurchaseRequest（見
    services/inquiry_resume_service.py 模組說明），收件人取自 `review.requester`；
    hallucination_mismatch 是舊版 Quote 流程，收件人取自 `review.quote.user`。任一種
    找不到收件人 email 時視為沒有收件人，_send_notification 會直接回傳 False，不拋例外。
    """
    recipient_user = review.requester
    if recipient_user is None and review.quote_id is not None:
        recipient_user = review.quote.user
    recipients = [recipient_user.email] if recipient_user and recipient_user.email else []

    subject = f"【詢價已駁回】案件 #{review.id} 需要您重新確認後再送出"
    body = (
        f"您送出的詢價（案件編號 #{review.id}）經管理員複核後遭駁回，尚未建立正式採購需求。\n\n"
        f"駁回原因：{review.rejection_reason or '（未填寫）'}\n\n"
        "請確認供應商全名與品項名稱是否與正式主檔一致後，重新於系統送出詢價。"
    )
    return _send_notification(
        subject=subject, body=body, recipients=recipients, link=_frontend_link("/inquiry")
    )


def notify_approval_step_activated(step) -> bool:
    """FR-8：簽核關卡成為可認領狀態時，通知該角色底下所有使用者（廣播，非單一人），附上簽核頁面連結。"""
    recipients = _active_recipients_for_role(step.role_id)
    subject = f"【待簽核】採購案件 #{step.approval_case_id} 第 {step.sequence} 關待處理"
    body = (
        f"採購簽核案件 #{step.approval_case_id} 已進入第 {step.sequence} 關"
        f"（{step.get_step_type_display()}），請登入系統前往簽核工作區認領處理。"
        "任一符合資格的使用者皆可認領，認領後其他人會看到處理中狀態，避免重複決議。"
    )
    return _send_notification(
        subject=subject, body=body, recipients=recipients, link=_frontend_link("/approvals")
    )


def first_claimable_step(case):
    """回傳 `case` 目前第一個可認領（狀態為 pending 且前面關卡皆已 approved）的關卡；
    沒有則回傳 `None`（案件已結案，或極端情況下前面關卡卡在非 approved 但仍是 pending
    以外的狀態——理論上不會發生，見 `decide_step` 的狀態機保證）。

    刻意設計成純查詢、不觸發任何寫入，讓呼叫端（view 層）可以在 service 的
    `transaction.atomic()` 交易提交之後才呼叫，避免把通知這種耗時外部呼叫包進交易。
    """
    steps = list(case.steps.order_by("sequence"))
    for step in steps:
        if step.status == "pending":
            return step
        if step.status != "approved":
            return None
    return None

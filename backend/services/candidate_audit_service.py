"""AI 採購候選的不可竄改快照與去識別化採用統計。"""

import json
from decimal import Decimal, InvalidOperation

from django.core import signing

from repositories.audit import AuditLogRepository

CANDIDATE_TOKEN_SALT = "groundtruth.purchase-candidate.v1"
CANDIDATE_TOKEN_MAX_AGE_SECONDS = 60 * 60


class CandidateTokenError(ValueError):
    pass


def _quantity(value):
    try:
        return str(Decimal(str(value)).normalize())
    except (InvalidOperation, TypeError, ValueError):
        return str(value or "")


def _candidate_snapshot(candidate):
    return {
        "purpose": str(candidate.get("purpose") or "").strip(),
        "needed_by": candidate.get("needed_by") or None,
        "currency": str(candidate.get("currency") or "TWD").upper(),
        "supplier_ids": sorted(
            row["supplier_id"] for row in candidate.get("supplier_candidates", [])
            if row.get("supplier_id") is not None
        ),
        "items": [
            {
                "product_id": row.get("product_id"),
                "quantity": _quantity(row.get("quantity")),
                "unit_of_measure": str(row.get("unit_of_measure") or "EA"),
                "specifications": row.get("specifications") or {},
            }
            for row in candidate.get("items", [])
        ],
    }


def create_candidate_token(user_id, candidate):
    return signing.dumps(
        {"user_id": user_id, "candidate": _candidate_snapshot(candidate)},
        salt=CANDIDATE_TOKEN_SALT,
        compress=True,
    )


def _confirmed_snapshot(payload):
    return {
        "purpose": str(payload.get("purpose") or "").strip(),
        "needed_by": payload.get("needed_by") or None,
        "currency": str(payload.get("currency") or "TWD").upper(),
        "supplier_ids": sorted(payload.get("supplier_ids") or []),
        "items": [
            {
                "product_id": row.get("product_id"),
                "quantity": _quantity(row.get("quantity")),
                "unit_of_measure": str(row.get("unit_of_measure") or "EA"),
                "specifications": row.get("specifications") or {},
            }
            for row in payload.get("items", [])
        ],
    }


def _changed_fields(original, confirmed):
    changed = []
    for field in ("purpose", "needed_by", "currency", "supplier_ids"):
        if original[field] != confirmed[field]:
            changed.append(field)
    if len(original["items"]) != len(confirmed["items"]):
        changed.append("items.count")
    for before, after in zip(original["items"], confirmed["items"], strict=False):
        for field in ("product_id", "quantity", "unit_of_measure", "specifications"):
            if before[field] != after[field]:
                changed.append(f"items.{field}")
    return sorted(set(changed))


def record_candidate_confirmation(user, token, confirmed_payload):
    if not token:
        return
    try:
        signed = signing.loads(
            token, salt=CANDIDATE_TOKEN_SALT, max_age=CANDIDATE_TOKEN_MAX_AGE_SECONDS,
        )
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise CandidateTokenError("AI 候選憑證無效或已過期，請重新解析需求") from exc
    if signed.get("user_id") != user.id:
        raise CandidateTokenError("AI 候選憑證不屬於目前使用者")
    changed_fields = _changed_fields(signed["candidate"], _confirmed_snapshot(confirmed_payload))
    AuditLogRepository.record(
        user=user,
        action_type="candidate_confirmed",
        verification_result="fail" if changed_fields else "pass",
        masked_payload=json.dumps(
            {"changed_fields": changed_fields, "changed_field_count": len(changed_fields)},
            ensure_ascii=False,
        ),
        real_query_summary="AI 候選確認結果；不保存原始輸入與欄位值",
    )


def record_candidate_parse(user, candidate):
    suppliers = candidate.get("supplier_candidates", [])
    items = candidate.get("items", [])
    summary = {
        "supplier_matched_count": sum(row.get("supplier_id") is not None for row in suppliers),
        "supplier_unmatched_count": sum(row.get("supplier_id") is None for row in suppliers),
        "product_matched_count": sum(row.get("product_id") is not None for row in items),
        "product_unmatched_count": sum(row.get("product_id") is None for row in items),
        "missing_field_count": len(candidate.get("missing_fields", [])),
    }
    AuditLogRepository.record(
        user=user,
        action_type="candidate_parsed",
        verification_result="pass" if candidate.get("ready_for_draft") else "fail",
        masked_payload=json.dumps(summary, ensure_ascii=False),
        real_query_summary="AI 候選解析彙總；不保存原始輸入與主檔名稱",
    )

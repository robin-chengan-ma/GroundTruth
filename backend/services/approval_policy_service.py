from repositories.procurement import ApprovalPolicyRepository


class ApprovalPolicyNotFoundError(Exception):
    """找不到符合幣別、金額與生效時間的核准政策。"""


class ApprovalPolicyConflictError(Exception):
    """同一條件匹配多個政策，必須先修正政策資料。"""


def find_approval_policy(amount, currency, *, at=None):
    """以左含右不含區間找出唯一有效政策。"""
    policies = list(ApprovalPolicyRepository.matching(amount=amount, currency=currency, at=at)[:2])
    if not policies:
        raise ApprovalPolicyNotFoundError("找不到適用的核准政策")
    if len(policies) > 1:
        raise ApprovalPolicyConflictError("同一金額匹配多個核准政策")
    return policies[0]

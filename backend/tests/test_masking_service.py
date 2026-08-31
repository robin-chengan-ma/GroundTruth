import pytest

from apps.audit.models import ManualReviewQueue
from apps.crm.models import Supplier
from services import masking_service


@pytest.fixture
def supplier_a(db):
    return Supplier.objects.create(name="優品科技", tier=Supplier.Tier.PRIORITY)


@pytest.fixture
def supplier_b(db):
    return Supplier.objects.create(name="優品資訊", tier=Supplier.Tier.NORMAL)


def test_mask_text_empty_raises():
    with pytest.raises(masking_service.MaskingError):
        masking_service.mask_text("")

    with pytest.raises(masking_service.MaskingError):
        masking_service.mask_text("   ")


def test_mask_text_exact_match_masks_supplier_and_amount(supplier_a):
    raw = "跟優品科技採購20個A產品，總金額NT$30,000元"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "masked"
    assert "優品科技" not in result["masked_text"]
    assert "SUP_001" in result["masked_text"]
    assert result["mapping"]["SUP_001"] == "優品科技"
    # 數量詞「20個」不應被當金額遮罩
    assert "20個" in result["masked_text"]


def test_mask_text_amount_with_yuan_suffix_is_masked(supplier_a):
    raw = "跟優品科技訂購，單價1500元，總金額30000元"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "masked"
    assert "1500元" not in result["masked_text"]
    assert "30000元" not in result["masked_text"]
    assert set(result["mapping"].values()) >= {"優品科技", "1500元", "30000元"}


def test_mask_text_no_amount_still_masks_supplier(supplier_a):
    raw = "跟優品科技詢價A產品"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "masked"
    assert result["mapping"] == {"SUP_001": "優品科技"}


def test_mask_text_multiple_exact_matches_creates_review(supplier_a, supplier_b):
    # 「優品」同時是兩間供應商名稱的前綴片段，但這裡故意讓兩間全名都精確出現。
    raw = "優品科技跟優品資訊我都有詢價"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "supplier_fuzzy_match"
    assert set(result["candidates"]) == {"優品科技", "優品資訊"}

    review = ManualReviewQueue.objects.get(id=result["review_id"])
    assert review.review_type == ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH
    assert review.quote_id is None
    assert review.supplier_id is None
    assert review.raw_input_text == raw


def test_mask_text_fuzzy_match_single_candidate_creates_review(supplier_a):
    # 少打一個字：優品科 vs 優品科技，ratio 應該 >= 0.6
    raw = "跟優品科採購A產品"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "supplier_fuzzy_match"
    assert result["candidates"] == ["優品科技"]

    review = ManualReviewQueue.objects.get(id=result["review_id"])
    assert review.supplier_id == supplier_a.id
    assert review.quote_id is None
    assert review.raw_input_text == raw


def test_mask_text_no_candidate_returns_supplier_not_found(db):
    Supplier.objects.create(name="優品科技", tier=Supplier.Tier.NORMAL)
    raw = "跟完全不相關的廠商XYZ採購產品"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "supplier_not_found"
    assert result["masked_text"] is None
    assert result["mapping"] == {}
    assert ManualReviewQueue.objects.count() == 0


def test_mask_text_no_suppliers_in_db_returns_not_found(db):
    result = masking_service.mask_text("跟某間公司採購產品")
    assert result["outcome"] == "supplier_not_found"


def test_mask_text_skips_supplier_with_empty_name(db):
    Supplier.objects.create(name="", tier=Supplier.Tier.NORMAL)
    Supplier.objects.create(name="優品科技", tier=Supplier.Tier.NORMAL)
    result = masking_service.mask_text("完全不相關的文字")
    assert result["outcome"] == "supplier_not_found"


def test_mask_text_raw_text_shorter_than_supplier_name(supplier_a):
    # raw_text 長度短於供應商名稱長度，滑動視窗會跳過過寬的視窗（覆蓋邊界分支）。
    result = masking_service.mask_text("優品")
    assert result["outcome"] in {"supplier_fuzzy_match", "supplier_not_found"}


def test_mask_text_short_generic_fragment_does_not_auto_prefill(db):
    # 使用者提出的疑慮案例：即使整體相似度過門檻、且是唯一候選，只要「真正連續相符」的
    # 字數相對全名太短（只是字元湊巧重疊，不是真的打錯一兩個字），就不該自動預填。
    # 「保又生技」對「保生技術」：ratio=0.75（過門檻），但最長連續相符只有 2 字，
    # 佔全名 4 字的 50%（< 60% 長度門檻），視為巧合命中。
    supplier = Supplier.objects.create(name="保生技術", tier=Supplier.Tier.NORMAL)
    raw = "跟保又生技採購一批貨"
    result = masking_service.mask_text(raw)

    assert result["outcome"] == "supplier_fuzzy_match"
    review = ManualReviewQueue.objects.get(id=result["review_id"])
    # 即使只有這一筆候選，長度不安全就不預填，留給人工判斷。
    assert review.supplier_id is None
    assert supplier.name in result["candidates"]


def test_unmask_text_restores_real_values():
    mapping = {"SUP_001": "優品科技", "AMOUNT_001": "30000元"}
    masked = "跟SUP_001採購，總金額AMOUNT_001"
    result = masking_service.unmask_text(masked, mapping)
    assert result == "跟優品科技採購，總金額30000元"


def test_unmask_text_empty_returns_as_is():
    assert masking_service.unmask_text("", {"SUP_001": "x"}) == ""
    assert masking_service.unmask_text(None, {}) is None


def test_mask_candidate_text_masks_multiple_suppliers_and_amount(supplier_a, supplier_b):
    raw = "向優品科技、優品資訊詢價，預算 TWD 30,000"

    result = masking_service.mask_candidate_text(raw)

    assert result["outcome"] == "masked"
    assert "優品科技" not in result["masked_text"]
    assert "優品資訊" not in result["masked_text"]
    assert "TWD 30,000" not in result["masked_text"]
    assert result["mapping"] == {
        "SUP_001": "優品科技",
        "SUP_002": "優品資訊",
        "AMOUNT_001": "TWD 30,000",
    }


def test_mask_candidate_text_empty_raises():
    with pytest.raises(masking_service.MaskingError):
        masking_service.mask_candidate_text("   ")


def test_mask_candidate_text_rejects_mixed_known_and_unknown_supplier(supplier_a):
    result = masking_service.mask_candidate_text(
        "跟優品科技、未建檔公司詢價，採購辦公椅 5 張",
    )

    assert result == {"outcome": "supplier_not_found", "masked_text": None, "mapping": {}}


def test_unmask_payload_restores_nested_strings_without_mutating_non_strings():
    payload = {
        "purpose": "向 SUP_001 採購",
        "suppliers": [{"name": "SUP_001"}],
        "items": [{"quantity": 5, "specifications": {"budget": "AMOUNT_001"}}],
        "needed_by": None,
    }

    result = masking_service.unmask_payload(
        payload, {"SUP_001": "優品科技", "AMOUNT_001": "30000元"},
    )

    assert result["purpose"] == "向 優品科技 採購"
    assert result["suppliers"][0]["name"] == "優品科技"
    assert result["items"][0]["quantity"] == 5
    assert result["items"][0]["specifications"]["budget"] == "30000元"
    assert result["needed_by"] is None


def test_mask_text_stores_requester_on_fuzzy_review(supplier_a, user):
    raw = "跟優品科採購A產品"
    result = masking_service.mask_text(raw, requester_id=user.id)
    review = ManualReviewQueue.objects.get(id=result["review_id"])
    assert review.requester_id == user.id


def test_mask_text_stores_requester_on_ambiguous_exact_matches(supplier_a, supplier_b, user):
    raw = "優品科技跟優品資訊我都有詢價"
    result = masking_service.mask_text(raw, requester_id=user.id)
    review = ManualReviewQueue.objects.get(id=result["review_id"])
    assert review.requester_id == user.id


def test_mask_text_requester_optional():
    with pytest.raises(masking_service.MaskingError):
        masking_service.mask_text("")  # requester_id 預設 None，不影響既有行為


# ---- mask_amounts_only（FR-6a 續傳流程專用） ----

def test_mask_amounts_only_masks_amount_context_numbers():
    raw = "數量20個，單價1500元，總金額NT$30,000"
    result = masking_service.mask_amounts_only(raw)
    assert "1500元" not in result["masked_text"]
    assert "NT$30,000" not in result["masked_text"]
    assert "20個" in result["masked_text"]  # 數量詞不遮罩
    assert set(result["mapping"].values()) == {"1500元", "NT$30,000"}


def test_mask_amounts_only_no_amounts_returns_empty_mapping():
    result = masking_service.mask_amounts_only("跟優品科技詢價A產品")
    assert result["masked_text"] == "跟優品科技詢價A產品"
    assert result["mapping"] == {}


def test_mask_amounts_only_empty_raises():
    with pytest.raises(masking_service.MaskingError):
        masking_service.mask_amounts_only("")

export interface UserProfile {
  id: number
  name: string
  email: string
  role: string
  permissions: string[]
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Quote {
  id: number
  user: number
  user_name: string
  supplier: number
  supplier_name: string
  product: number
  product_name: string
  quantity: number
  price: string
  total_amount: string
  currency: string
  ai_summary_text: string | null
  status: string
  price_deviation_pct: string | null
  created_at: string
}

export interface Approval {
  id: number
  quote: number
  quote_detail: Quote
  role: number
  role_code: string
  approver: number | null
  approver_name: string | null
  approval_level: string
  status: string
  created_at: string
  updated_at: string
}

export interface ApprovalStep {
  id: number
  sequence: number
  step_type: 'waiver_exception' | 'amount_approval'
  role: { id: number; code: string }
  status: 'pending' | 'claimed' | 'approved' | 'rejected'
  claimed_by: { id: number; name: string } | null
  claimed_at: string | null
  decided_by: { id: number; name: string } | null
  decided_at: string | null
  decision_reason: string | null
  can_claim: boolean
  can_decide: boolean
}

export interface ApprovalCase {
  id: number
  award_id: number
  request_id: number
  request_no: string
  purpose: string
  requester: { id: number; name: string }
  policy: { id: number; name: string }
  total_amount: string
  currency: string
  status: 'pending' | 'in_progress' | 'approved' | 'rejected' | 'cancelled'
  submitted_at: string
  decided_at: string | null
  steps: ApprovalStep[]
}

export interface ManualReview {
  id: number
  quote: number | null
  review_type: 'hallucination_mismatch' | 'supplier_fuzzy_match'
  ai_generated_text: string | null
  expected_value: string | null
  supplier: number | null
  supplier_name: string | null
  raw_input_text: string | null
  requester: number | null
  status: string
  user: number | null
  claimant_name: string | null
  decision: string | null
  resume_status: 'not_applicable' | 'pending' | 'succeeded' | 'failed'
  resume_error_code: string | null
  created_purchase_request: number | null
  created_at: string
  updated_at: string
}

export interface SupplierOption { id: number; name: string }
export interface ProductOption { id: number; name: string; price: string; currency: string }
export interface PurchaseCandidateItem {
  product_id: number | null
  product_name: string
  quantity: string | null
  unit_of_measure: string
  specifications: Record<string, string>
}
export interface PurchaseCandidate {
  purpose: string
  needed_by: string | null
  currency: string
  assistant_message: string
  supplier_candidates: Array<{ supplier_id: number | null; supplier_name: string }>
  items: PurchaseCandidateItem[]
  missing_fields: string[]
  ready_for_draft: boolean
  candidate_token: string
  supplier_product_coverage?: SupplierProductCoverageRow[]
}
export type SupplierProductCoverageStatus = 'priced' | 'unpriced' | 'conditional' | 'blocked' | 'inactive' | 'not_configured'
export interface SupplierProductCoverageRow {
  supplier_id: number
  supplier_name: string
  product_id: number
  product_name: string
  status: SupplierProductCoverageStatus
  label: string
  unit_price: string | null
  currency: string
}
export interface PurchaseDraft { id: number; version: number; status: string }
export interface PurchaseRequestSummary {
  id: number
  request_no: string
  purpose: string
  requester_name: string
  status: string
  currency: string
  item_summary: string
  supplier_summary: string
  created_at: string
  updated_at: string
}
export interface PaginatedPurchaseRequests {
  count: number
  page: number
  page_size: 10 | 20 | 50
  total_pages: number
  results: PurchaseRequestSummary[]
}
/** Phase 6 補齊清單頁分頁缺口共用的分頁回應形狀，與 `/purchase-requests/`（PaginatedPurchaseRequests）
 * 一致：`{count, page, page_size, total_pages, results}`，由 `backend/lib/pagination.py` 統一產生。 */
export interface PaginatedList<T> {
  count: number
  page: number
  page_size: 10 | 20 | 50
  total_pages: number
  results: T[]
}
export interface PurchaseRequestDetail {
  id: number
  request_no: string
  purpose: string
  needed_by: string | null
  requester_name: string
  status: string
  currency: string
  source: string
  candidate_suppliers: Array<{ supplier_id: number; supplier_name: string }>
  items: Array<{
    id: number
    line_no: number
    product_id: number | null
    product_name: string | null
    description_snapshot: string
    specifications: Record<string, unknown>
    quantity: string
    unit_of_measure: string
  }>
  created_at: string
  updated_at: string
}
export interface EstimateItem {
  product_id: number
  product_name: string
  quantity: string
  unit_of_measure: string
  available: boolean
  message?: string
  unit_price?: string
  total_amount?: string
  currency?: string
  price_comparison?: { status: 'unavailable' | 'normal' | 'warning'; label: string; deviation_pct: string | null }
}
export interface DraftEstimate {
  request_id: number
  version: number
  status: 'estimate_only'
  message: string
  suppliers: Array<{ supplier_id: number; supplier_name: string; items: EstimateItem[]; estimated_total: string; currency: string }>
}

// ==================== Phase 6 ====================

// ---- 主檔管理：供應商／品項分類／品項／供應商產品與價格 ----
export type SupplierTier = 'priority' | 'normal' | 'watch'
export type SupplierStatus = 'active' | 'on_hold' | 'blocked'
export interface Supplier {
  id: number
  name: string
  tier: SupplierTier
  code: string | null
  status: SupplierStatus
  tax_id: string | null
  contact: Record<string, unknown>
  payment_terms: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ProductCategory {
  id: number
  code: string
  name: string
  spec_schema: Record<string, unknown>
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Product {
  id: number
  name: string
  category: number | null
  category_name: string | null
  sku: string | null
  description: string
  specifications: Record<string, unknown>
  unit_of_measure: string
  is_active: boolean
  price: string
  currency: string
  updated_at: string
}

export interface SupplierPriceVersion {
  id: number
  supplier_product: number
  unit_price: string
  currency: string
  minimum_quantity: string
  valid_from: string
  valid_until: string | null
  created_by: number
  created_by_name: string
  created_at: string
}
export interface SupplierProduct {
  id: number
  supplier: number
  supplier_name: string
  product: number
  product_name: string
  supplier_sku: string | null
  lead_time_days: number
  minimum_order_quantity: string
  quality_status: string
  is_active: boolean
  price_versions: SupplierPriceVersion[]
  created_at: string
  updated_at: string
}

// ---- 詢價與評選：RFQ／供應商報價／得標方案 ----
export type RfqStatus = 'draft' | 'issued' | 'collecting' | 'evaluating' | 'closed' | 'cancelled'
export interface RfqScoringCriterion {
  code: string
  label: string
  weight: string
  calculation_method: string
  sequence: number
}
export type RfqInvitationStatus = 'invited' | 'responded' | 'declined' | 'expired' | 'cancelled'
export interface RfqInvitedSupplier {
  rfq_supplier_id: number
  supplier_id: number
  supplier_name: string
  status: RfqInvitationStatus
  invited_at: string
  responded_at: string | null
}
export interface RfqRequestItem {
  id: number
  line_no: number
  product_id: number | null
  product_name: string | null
  description_snapshot: string
  specifications: Record<string, unknown>
  quantity: string
  unit_of_measure: string
}
export interface Rfq {
  id: number
  rfq_no: string
  request_id: number
  request_no: string
  request_purpose: string
  revision: number
  status: RfqStatus
  response_due_at: string
  rule_snapshot: Record<string, unknown>
  version: number
  supplier_ids: number[]
  invited_suppliers: RfqInvitedSupplier[]
  criteria: RfqScoringCriterion[]
  request_items: RfqRequestItem[]
  created_at: string
  updated_at: string
}

export type SupplierQuoteStatus =
  | 'draft' | 'submitted' | 'accepted_for_evaluation' | 'revised' | 'rejected' | 'expired'
export interface SupplierQuoteItem {
  id: number
  request_item_id: number
  quantity: string
  unit_price: string
  subtotal: string
  lead_time_days: number | null
  warranty_months: number | null
  specifications: Record<string, unknown>
}
export interface SupplierQuote {
  id: number
  quote_no: string
  rfq_id: number
  supplier_id: number
  supplier_name: string
  revision: number
  status: SupplierQuoteStatus
  currency: string
  exchange_rate_to_twd: string
  items_subtotal: string
  tax_amount: string
  shipping_amount: string
  discount_amount: string
  landed_total_twd: string
  payment_terms_snapshot: string
  valid_until: string | null
  submitted_at: string | null
  items: SupplierQuoteItem[]
  created_at: string
}

export type AwardDecisionStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'cancelled'
export interface AwardLine {
  id: number
  request_item_id: number
  supplier_quote_item_id: number
  supplier_id: number
  supplier_name: string
  quantity: string
  unit_cost_twd: string
  amount_twd: string
  reason: string
}
export interface AwardDecision {
  id: number
  rfq_id: number
  revision: number
  status: AwardDecisionStatus
  selection_reason: string
  selected_by: { id: number; name: string }
  submitted_at: string | null
  approval_case_id: number | null
  total_amount_twd: string
  lines: AwardLine[]
}

// ---- 訂單與到貨：採購單／收貨／驗收差異 ----
export type PurchaseOrderStatus =
  | 'draft' | 'issued' | 'partially_received' | 'received' | 'closed' | 'cancelled'
export interface PurchaseOrderItem {
  id: number
  line_no: number
  award_line_id: number
  product_id: number
  product_name: string
  specifications: Record<string, unknown>
  quantity: string
  unit_price: string
  amount: string
}
export interface PurchaseOrder {
  id: number
  po_no: string
  award_id: number
  request_id: number
  request_no: string
  supplier: { id: number; name: string }
  status: PurchaseOrderStatus
  currency: string
  total_amount: string
  issued_at: string | null
  version: number
  items: PurchaseOrderItem[]
}

export type GoodsReceiptStatus =
  | 'draft' | 'inspecting' | 'posted' | 'partially_accepted' | 'rejected' | 'voided'
export type QualityInspectionStatus = 'accepted' | 'partially_accepted' | 'rejected'
export interface GoodsReceiptItemInspection {
  id: number
  status: QualityInspectionStatus
  accepted_quantity: string
  defective_quantity: string
  rejected_quantity: string
  defect_details: string
  notes: string
  inspected_by: { id: number; name: string } | null
  inspected_at: string
}
export interface GoodsReceiptItem {
  id: number
  purchase_order_item_id: number
  product_id: number
  product_name: string
  received_quantity: string
  lot_no: string | null
  replacement_variance_line_id: number | null
  inspection: GoodsReceiptItemInspection | null
}
export interface GoodsReceipt {
  id: number
  receipt_no: string
  purchase_order_id: number
  po_no: string
  request_id: number
  supplier: { id: number; name: string }
  status: GoodsReceiptStatus
  received_by: { id: number; name: string } | null
  received_at: string | null
  version: number
  items: GoodsReceiptItem[]
}

export type InspectionVarianceCaseStatus = 'draft' | 'open' | 'closed' | 'cancelled'
export type InspectionVarianceActionType = 'replacement' | 'return' | 'credit' | 'waive'
export type InspectionVarianceLineStatus = 'pending' | 'completed' | 'cancelled'
export interface InspectionVarianceLine {
  id: number
  action_type: InspectionVarianceActionType
  quantity: string
  status: InspectionVarianceLineStatus
  reason: string
  completed_by: { id: number; name: string } | null
  completed_at: string | null
}
export interface InspectionVarianceCase {
  id: number
  quality_inspection_id: number
  goods_receipt_id: number
  purchase_order_id: number
  product: { id: number; name: string }
  supplier: { id: number; name: string }
  variance_quantity: string
  status: InspectionVarianceCaseStatus
  version: number
  created_by: { id: number; name: string }
  submitted_by: { id: number; name: string } | null
  submitted_at: string | null
  closed_by: { id: number; name: string } | null
  closed_at: string | null
  lines: InspectionVarianceLine[]
}

// ---- 庫存與建議 ----
export interface InventoryBalance {
  product: number
  product_name: string
  on_hand_quantity: string
  reserved_quantity: string
  in_transit_quantity: string
  available_quantity: string
  threshold: number | null
  version: number
  updated_at: string
}
export type InventoryMovementType =
  | 'receipt_accept' | 'return_out' | 'issue_out' | 'adjustment_in' | 'adjustment_out'
  | 'reversal' | 'migration_assumed_receipt'
export interface InventoryMovement {
  id: number
  product: number
  product_name: string
  movement_type: InventoryMovementType
  quantity_delta: string
  reference_type: string
  reference_id: number
  affects_balance: boolean
  reason: string
  posted_at: string
  posted_by: number | null
  posted_by_name: string | null
  created_at: string
}

export type PurchaseSuggestionStatus = 'pending' | 'in_progress' | 'processed' | 'dismissed'
export interface PurchaseSuggestion {
  id: number
  product: number
  suggested_qty: string
  status: PurchaseSuggestionStatus
  source_movement: number | null
  purchase_request: number | null
  created_at: string
}

// ---- 稽核：稽核紀錄／稽核與正確率總覽 ----
export interface AuditLog {
  id: number
  user: number | null
  action_type: string
  masked_payload: Record<string, unknown> | null
  real_query_summary: string | null
  verification_result: string | null
  quote: number | null
  created_at: string
}

export interface DashboardCandidateQualityStats {
  direct_adoption_count: number
  corrected_count: number
  direct_adoption_rate_pct: string | null
  corrections_by_field: Record<string, number>
}
export interface DashboardSupplierMatchStats {
  supplier_matched_count: number
  supplier_unmatched_count: number
  product_matched_count: number
  product_unmatched_count: number
  fuzzy_match_total: number
  fuzzy_match_approved: number
  fuzzy_match_rejected: number
  fuzzy_match_pending: number
}
export interface DashboardManualReviewQueueStats {
  pending_count: number
  processed_count: number
  by_decision: { approved: number; rejected: number }
}
export interface DashboardPriceAnomalyItem {
  supplier_quote_item_id: number
  rfq_no: string
  supplier_id: number
  supplier_name: string
  product_id: number
  product_name: string
  unit_price: string
  historical_average: string
  deviation_pct: string
  currency: string
}
export interface DashboardPriceAnomalyStats {
  threshold_pct: string
  checked_count: number
  anomaly_count: number
  anomaly_rate_pct: string | null
  items: DashboardPriceAnomalyItem[]
}
export interface DashboardQualityStats {
  inspection_count: number
  accepted_quantity: string
  exception_quantity: string
  acceptance_rate_pct: string | null
}
export interface AuditDashboardStats {
  period: { from: string | null; to: string | null }
  candidate_quality: DashboardCandidateQualityStats
  supplier_match: DashboardSupplierMatchStats
  manual_review_queue: DashboardManualReviewQueueStats
  price_anomaly: DashboardPriceAnomalyStats
  quality: DashboardQualityStats
}

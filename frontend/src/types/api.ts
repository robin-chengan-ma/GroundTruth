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

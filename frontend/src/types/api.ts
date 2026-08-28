export interface UserProfile {
  id: number
  name: string
  email: string
  role: string
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

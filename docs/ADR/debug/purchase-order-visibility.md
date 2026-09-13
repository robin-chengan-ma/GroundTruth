---
updated: 2026-09-10
---

# 採購單讀取權限缺漏修復紀錄

## 2026-09-10 收貨人員看不到已發出的採購單

**現象**：以 receiver 角色（Frank Tsai）登入，在「新增收貨單」的採購單下拉選單裡，即使目標採購單已經是 `issued` 狀態，清單仍然是空的；點「重新整理」也一樣看不到。

**排查過程**：追蹤前端 `GoodsReceiptListView.vue` 的 `loadPurchaseOrders()`，發現呼叫 `/purchase-orders/` 失敗時會被 `catch` 吞掉、直接把清單設成空陣列，不會顯示任何錯誤訊息，所以外觀上跟「單純沒有可收貨的採購單」無法分辨。往後端追，`services/purchase_order_service.py` 的 `list_accessible_purchase_orders()` 只允許 `purchase_order.manage`、`audit.read`（可看全部）或 `purchase_request.read_own`（只能看自己需求產生的 PO）三種權限，receiver 角色的實際權限只有 `receipt.record`、`master_data.read`、`inventory.read`，三者都不在允許清單內，因此後端直接回 403。

**根因**：`list_accessible_purchase_orders()` 建立時沒有把「收貨（receipt.record）」與「品質驗收（inspection.decide）」納入可唯讀全部的權限清單，跟同流程的 `goods_receipt_service.list_accessible_goods_receipts()`／`inspection_variance_service._require_read()` 的權限設計不一致（後兩者都有把這兩個角色算進可讀全部）。收貨、驗收人員本來就需要看到已發出的採購單才能建立收貨單／執行驗收，這是被遺漏的權限規則，不是刻意限制。

**修復方式**：在 `backend/services/purchase_order_service.py` 的 `list_accessible_purchase_orders()`，把 `can_read_all` 判斷的權限集合加入 `receipt.record`、`inspection.decide`，比照收貨單／驗收差異案件既有的讀取權限規則。`get_accessible_purchase_order()` 內部呼叫同一個函式，一併修復。同步更新 `docs/reference/api.md` 的 `GET /api/v1/purchase-orders/` 權限說明。

**驗證方式**：`python3 -m py_compile services/purchase_order_service.py` 通過；檢查 `tests/test_phase4_1_purchase_orders.py` 現有測試（`test_po_list_visibility_is_own_request_or_business_permission`）用的 outsider 角色不具任何權限，不受此次修改影響，預期仍通過；待 Robin 用 `docker compose exec backend python -m pytest tests/test_phase4_1_purchase_orders.py tests/test_phase4_1_goods_receipts.py -q` 實際跑過確認，並在畫面上以 Frank 帳號重新整理確認能選到已發出的採購單。

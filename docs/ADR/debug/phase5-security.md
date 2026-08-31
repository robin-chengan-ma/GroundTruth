---
title: Phase 5 安全與應用切換修復紀錄
updated: 2026-08-31
---

# Phase 5 安全與應用切換修復紀錄

## 2026-08-31 n8n v2 候選解析繞過敏感資料遮罩
**現象**：新版 `inquiries/parse/` 雖只回傳候選資料且不建單，但 Django 將使用者 `raw_text` 原文直接送到 n8n／Gemini；多間供應商名稱與具金額語境的數字未經 Phase 3 固定遮罩。
**排查過程**：沿 `InquiryCandidateParseView → parse_purchase_request_candidate() → request_candidate_parse()` 檢查資料流，確認 Service 未呼叫 masking service，Repository 直接以原文建立 webhook payload。另確認既有 `mask_text()` 專為 legacy 單供應商流程設計，兩間完整命中的供應商會被視為歧義，不能直接重用於新版多候選流程。
**根因**：D2 建立新候選解析契約時只分離「AI 候選」與「正式建單」，沒有把 FR-2／NFR-1 的遮罩邊界一併移植到新 webhook；因此形成新舊流程安全能力不一致。
**修復方式**：在 `backend/services/masking_service.py` 新增新版專用 `mask_candidate_text()`，將所有完整命中的已建檔供應商與金額 Token 化；顯式供應商片段混有未知名稱時採 fail closed，完全未知沿用查無分流，模糊命中沿用人工複核。新增 `unmask_payload()` 遞迴還原 n8n 回傳的巢狀候選字串。`backend/services/inquiry_service.py` 改為遮罩成功後才呼叫 Repository，mapping 只留在單次函式呼叫記憶體。
**驗證方式**：TDD RED 確認多供應商／金額仍以原文送出及遞迴還原函式不存在；GREEN 驗證單一與多供應商、金額、巢狀 payload、未知供應商、混合已知／未知、空值、Malformed payload 與 API 權限。目標測試、完整回歸、coverage、Ruff、Django check、Migration check 於 PROGRESS 記錄最終結果。
**未驗證範圍**：無。Robin 已以真實 n8n production webhook 從 Vue 驗證兩間供應商、兩品項與預算情境：LLM Input 僅含 `SUP_001`／`SUP_002`／`AMOUNT_001`，不含真實供應商名稱與金額；LLM Output 保留供應商 Token，Django 正確還原兩間候選供應商。workflow JSON 依 ignore／敏感資料規則不由 AI 讀取或修改。

---
updated: 2026-08-31
---

# Phase 5 前端與應用切換

## 2026-08-31 [標籤：使用者／AI] Phase 5.0 應用切換與安全收斂
**狀態**：accepted
**背景**：Phase 4.1 已完成企業採購核心 Schema、Migration、後端 command 與 D2 採購需求介面，但全專案盤點確認正式應用仍混用 legacy Quote／Approval：n8n v2 候選解析直接傳送原始文字、舊 Quote command API 仍可寫入、簽核與人工複核仍接舊資料模型，部分授權仍以單一 role 或 admin 判斷，且 DRF 預設權限仍為 `AllowAny`。若直接擴充 Phase 5 畫面，前端會建立在新舊混合契約上並造成後續重構。
**討論內容**：Robin 同意在 Phase 5 正式業務頁面前，先增加 Phase 5.0，完成新核心接管、安全邊界與共用 API 契約；legacy 資料保留供歷史追溯，不刪除既有 Migration 或資料表。
**決策**：
1. P5.0-A「AI 安全邊界」：新版候選解析必須先使用固定程式遮罩供應商與金額等敏感資訊，再呼叫 n8n／LLM；遮罩對照表只存在單次請求記憶體。補上正常、多供應商、金額、模糊命中、空值、外部服務錯誤與不得建立正式單據測試。
2. P5.0-B「command 切換」：新版 Purchase Request、RFQ、Supplier Quote、Award、Approval Case、PO、收貨／驗收與庫存流程成為唯一正式寫入路徑。legacy inquiry／Quote／Approval command 停止新增或修改；舊資料只保留唯讀歷史與受控回退，不執行 DROP。
3. P5.0-C「授權收斂」：簽核切換至 Approval Case／Step，人工複核不得再建立 legacy Quote；所有業務授權使用 permission code，不以 primary role 或 admin 身分代替能力檢查。DRF 預設改為 authenticated／fail closed，公開登入及內部 API Key 端點逐一明確例外。
4. P5.0-D「Phase 5 契約」：補齊主資料、版本價格、Purchase Request 詳情、RFQ、供應商報價、比較評分、得標、PO、收貨、驗收差異、庫存與採購建議的受權限控制查詢契約；前端主路由與型別改用新實體命名，舊 `/quotes` 僅提供相容 redirect 或歷史入口。
5. P5.0-E「相容性與文件」：保留 Quote、Approval、`legacy_quote_id`、舊欄位與所有 Migration；測試須證明 legacy command 已阻擋、新流程不再新增 Quote、舊資料仍可追溯、權限與競態防線有效。同步整理 API／DB／部署 Reference 與 README 的現行敘述。
6. 本階段預設不新增或刪除資料表。若實作時發現必須新增 permission、欄位、索引、constraint 或資料轉換，須另行提出 Migration 影響、SQL／資料轉換、鎖表風險與回滾策略，取得 Robin 明確核准後才可建立及套用。
**理由**：先讓新核心成為唯一正式寫入來源，並固定安全、授權與查詢契約，Phase 5 各頁面才能共用穩定 API，不需在完成 UI 後再次更換資料模型。
**後果**：Phase 4.1 核心能力維持完成，但原規劃的 4.1.9 應用切換改由 Phase 5.0 明確承接。Phase 5.0 完成並通過回歸前，不開始大批 Phase 5 業務頁面；D2 已上線的採購需求介面可繼續使用，但其 AI 遮罩缺口列為 P5.0-A 第一優先。

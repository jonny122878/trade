---
mode: ask
description: 查詢 T1 指定業者/月份/支付類型/聯營類型的筆數 SQL
---

## 資料來源說明

請參考以下 schema 文件：
- [BM_STORE_M路線對照.md](../../schema/BM_STORE_M路線對照.md)
- [T1.md](../../T1/T1.md)
- [T1_explain.md](../../T1/T1_explain.md)

### 關鍵資料表

| 資料表 | 資料庫 | 說明 |
|---|---|---|
| `RPT_ICP_SETTLE_DATA_D_FOR_T1` | `[dbo]` | 電支（QR乘車碼） |
| `RPT_SETTLE_DATA_D_FOR_T1` | `[B101]` | 電票（icash實體卡） |
| `BM_STORE_M` | `[B101]` | 路線/業者主檔，含 OPERATE_TYPE |

### 清分日邏輯
- `CPT_DATE`：清分日（資料入帳日）
- `BUSINESS_DATE`：營業日（旅客實際搭乘日）
- 一個 BUSINESS_DATE 可能對應多個 CPT_DATE
- 標準篩法：`CPT_DATE <= '{清分日}'`，BUSINESS_DATE 用子查詢取當次清分日涵蓋的範圍

### OPERATE_TYPE 對照
| 值 | 說明 |
|---|---|
| 01 | 新北市聯營段次 |
| 02 | 其他聯營段次 |
| 03 | 里程路線 |

---

## 查詢參數（請填入後送出）

- **業者名稱**：{MERCHANT_NAME}（如 三重客運）
- **MERCHANT_NO**：{MERCHANT_NO}（如 35025506）
- **月份**：{YYYYMM}（如 202606）
- **清分日（CPT_DATE）**：{CPT_DATE}（如 20260630，取當月最後清分日）
- **支付類型**：{PAYMENT_TYPE}（電支 / 電票 / 全部）
- **聯營類型 OPERATE_TYPE**：{OPERATE_TYPE_LIST}（如 01 / 01,02 / 01,02,03）

---

## 任務

根據上方參數與 schema 文件，幫我組出以下 SQL：

1. **筆數查詢（COUNT）**：
   - 依 BUSINESS_DATE 分組，輸出每個營業日的筆數與合計
   - 最後加一列 TOTAL 合計列

2. **篩選條件須包含**：
   - `D.MERCHANT_NO = '{MERCHANT_NO}'`
   - `D.BUSINESS_DATE LIKE '{YYYYMM}%'`
   - `D.CPT_DATE <= '{CPT_DATE}'`
   - `D.IS_ACT = 'Y'`
   - `S.OPERATE_TYPE IN ({OPERATE_TYPE_LIST})`
   - BUSINESS_DATE 需用子查詢限制在 CPT_DATE 範圍內（參考 T1.md 的子查詢寫法）

3. **支付類型對應**：
   - 電支 → 只查 `[dbo].[RPT_ICP_SETTLE_DATA_D_FOR_T1]`
   - 電票 → 只查 `[B101].[RPT_SETTLE_DATA_D_FOR_T1]`
   - 全部 → UNION ALL 兩表

只輸出 SQL，加上必要的欄位別名，不需要額外說明。

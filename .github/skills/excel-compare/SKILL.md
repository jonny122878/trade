---
name: excel-compare
description: '用於比對兩個 Excel 檔案是否一致，輸出 summary 與逐格差異 CSV。適用於報表驗收、批次產出比對、上線前資料核對。'
argument-hint: '輸入 A 檔路徑、B 檔路徑；可選 sheets 清單、是否忽略前後空白、輸出資料夾'
user-invocable: true
---

# Excel 差異比對

## 適用情境

### 模式 1: 檔案 vs 檔案（同名或檔案名稱模糊比對）
- 比對兩個 Excel 檔案中的工作表
- 優先比對同名工作表
- 若工作表不同名：
  - 若檔案 B **只有 1 個**工作表，自動用該工作表與 A 的工作表比對
  - 若檔案 B **有多個**工作表，進行模糊匹配
- 適合：定期產出報表、版本更新驗證、檔案名稱變動但內容結構相同的比對

### 模式 2: 多Sheet檔案 vs 資料夾（模糊匹配）
- 比對 1 個多工作表 Excel 檔案 vs 1 個資料夾內的多個 Excel 檔案
- 自動使用模糊匹配（Fuzzy Match）將 Sheet 名稱對應到檔案名稱
- 比對每個 Sheet 與對應檔案的內容
- 適合：跨期報表驗證、多檔案匯總報表核對

### 模式 3: 資料夾 vs 資料夾（檔案名稱模糊比對）
- 比對 2 個資料夾內的 Excel 檔案
- 自動使用模糊匹配將檔案進行配對
- 比對每對檔案的**第一個工作表**（Active Sheet）
- 自動找出未匹配的檔案
- 適合：同期不同版本報表核對、多目錄檔案批量驗證

## 預設工具
- 比對腳本：`.github/skills/excel-compare/script/compare_excel.py`
- Python 執行：優先使用 workspace 的 `.venv`

## 必做步驟
1. 確認輸入檔案/資料夾都存在且可讀取。
2. 以 `.venv` Python 執行 `.github/skills/excel-compare/script/compare_excel.py`。
3. 取得結果資料夾並檢查：
   - `summary.txt`
   - `differences.csv`
4. 回覆使用者：
   - 是否一致（IDENTICAL / DIFFERENT）
   - 差異總數
   - 報告路徑
5. 若有差異，優先摘要前 10 筆關鍵差異（sheet、cell、A/B 值）。

## 執行指令

### 模式 1: 檔案 vs 檔案（預設）

基礎用法：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<A.xlsx>" --b "<B.xlsx>"
```

指定工作表：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<A.xlsx>" --b "<B.xlsx>" --sheets Sheet1 Sheet2
```

忽略前後空白：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<A.xlsx>" --b "<B.xlsx>" --ignore-space
```

### 模式 2: 多Sheet檔案 vs 資料夾

基礎用法：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<multi_sheet.xlsx>" --folder-b "<folder_path>" --compare-mode file-vs-folder
```

忽略前後空白：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<multi_sheet.xlsx>" --folder-b "<folder_path>" --compare-mode file-vs-folder --ignore-space
```

指定輸出資料夾：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<multi_sheet.xlsx>" --folder-b "<folder_path>" --compare-mode file-vs-folder --report-dir "<output_dir>"
```

### 模式 3: 資料夾 vs 資料夾

基礎用法：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<folder_a>" --folder-b "<folder_b>" --compare-mode folder-vs-folder
```

忽略前後空白：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<folder_a>" --folder-b "<folder_b>" --compare-mode folder-vs-folder --ignore-space
```

指定輸出資料夾：
```powershell
.\.venv\Scripts\python.exe .github/skills/excel-compare/script/compare_excel.py --a "<folder_a>" --folder-b "<folder_b>" --compare-mode folder-vs-folder --report-dir "<output_dir>"
```

## 參數規則

### 共用參數
- `--a`：第一個 Excel 檔案路徑（必要）
- `--ignore-space`：忽略字串前後空白差異（可選）
- `--report-dir`：輸出報告資料夾（可選）

### 模式 1 參數（檔案 vs 檔案）
- `--compare-mode file-vs-file`：指定比對模式（預設值，可省略）
- `--b`：第二個 Excel 檔案路徑（必要）
- `--sheets`：僅比對指定工作表（可選）

### 模式 2 參數（多Sheet檔案 vs 資料夾）
- `--compare-mode file-vs-folder`：指定比對模式（必要）
- `--folder-b`：包含 Excel 檔案的資料夾路徑（必要）

### 模式 3 參數（資料夾 vs 資料夾）
- `--compare-mode folder-vs-folder`：指定比對模式（必要）
- `--folder-b`：第二個資料夾路徑（必要）
- 注意：`--a` 為第一個資料夾路徑

## 輸出解讀

### 模式 1 輸出
- `Result: IDENTICAL`：無儲存格差異，且所有工作表都成功匹配
- `Result: DIFFERENT`：存在儲存格差異，或工作表匹配失敗
- `summary.txt`：
  - 整體結果與備註
  - 工作表映射關係（若 A、B 的 Sheet 名稱不同）
- `differences.csv`：
  - 若工作表名稱完全相同：欄位為 `sheet, row, column, cell, value_a, value_b`
  - 若工作表名稱不同（如B只有1個Sheet）：欄位為 `sheet, sheet_b, row, column, cell, value_a, value_b`

### 模式 2 輸出
- `Result: IDENTICAL`：所有比對的 Sheet 內容無差異
- `Result: DIFFERENT`：存在儲存格差異或匹配失敗
- `summary.txt`：
  - Sheet 到檔案的對應關係（模糊匹配結果）
  - 未匹配的檔案清單
  - 其他錯誤訊息
- `differences.csv`：欄位：sheet, file_b, row, column, cell, value_a, value_b

### 模式 3 輸出
- `Result: IDENTICAL`：所有配對檔案的內容無差異
- `Result: DIFFERENT`：存在儲存格差異或檔案匹配失敗
- `summary.txt`：
  - 檔案配對關係（模糊匹配結果）
  - 未匹配檔案清單（只在 A 或只在 B）
  - 其他錯誤訊息
- `differences.csv`：欄位：file_a, file_b, row, column, cell, value_a, value_b

## 模糊匹配說明

### 模式 1: 單 Sheet 自動匹配
當檔案 B 只有 1 個工作表時，自動與 A 的對應工作表比對，無需名稱相同。

**範例：**
| 檔案 A | 檔案 B | 比對結果 |
|-------|-------|--------|
| Sheet1 (A只有1個) | Report (B只有1個) | ✓ 自動比對 Sheet1 ↔ Report |
| Sheet1, Sheet2 | 2026_Report (只有1個) | ✓ A的第一個待比對Sheet 與 2026_Report 比對 |

### 模式 2: 多檔案 Sheet 名稱 Fuzzy Match
模式 2 使用 Python 內置的 `difflib.SequenceMatcher` 進行模糊匹配：
- 預設相似度閾值：60%
- 比對時忽略檔案副檔名（.xlsx / .xls）
- 自動選擇相似度最高的匹配

**範例：**
| Sheet 名稱 | 檔案名稱 | 匹配結果 |
|-----------|---------|--------|
| 03_台中區月票月結餘額表 | 115年05月台中月票月結餘額表.xlsx | ✓ 匹配 |
| 01_全通勤月票月結餘額表 | 115年05月全通勤月票月結餘額表.xlsx | ✓ 匹配 |

### 模式 3: 資料夾 檔案名稱 Fuzzy Match
模式 3 也使用模糊匹配比對檔案名稱：
- 預設相似度閾值：60%
- 忽略檔案副檔名進行匹配
- 自動選擇相似度最高的匹配

**範例：**
| 資料夾 A 檔案 | 資料夾 B 檔案 | 匹配結果 |
|-------------|-------------|--------|
| 愛金卡_中彰投苗月票優惠補助金額申請總表202605.xlsx | 115年05月中彰投苗月票優惠補助金額申請總表.xlsx | ✓ 匹配 |
| 愛金卡_台中區月票優惠補助金額申請總表202605.xlsx | 115年05月台中區月票優惠補助金額申請總表.xlsx | ✓ 匹配 |

## 失敗處理
- 若缺少 `openpyxl`，先安裝至 `.venv`：

```powershell
uv pip install --python .\.venv\Scripts\python.exe openpyxl
```

- 若 `.venv` 不存在，先建立：

```powershell
uv venv .venv
```

## 參考檔案
- `.github/skills/excel-compare/script/compare_excel.py`

---
name: add-batch
description: 'Use when: 需要建立新的 bat 檔、替換 bat 內 PowerShell .ps1 名稱、或修改大 bat 插入 call 新批次流程。'
argument-hint: '輸入建立路徑、新 bat 名稱、PowerShell 名稱，及要修改的大 bat 路徑與新 bat 名稱'
user-invocable: true
---

# bat 批次建立與掛接

## 適用情境
- 需要依指定路徑與 bat 名稱，建立一支新的批次檔
- 需要把 bat 內 `PowerShell -Command` 呼叫的 `.ps1` 名稱一起替換
- 需要修改指定的大 bat，新增一段 `call 新批次.bat` 的執行流程
- 需要依照既有大 bat 範本格式，補齊 step log、成功失敗跳轉與 label

## 必做步驟
1. 建立新 bat。
   - 使用者提供 `目標路徑`、`新 bat 名稱`。
   - 以 [template/SERVICE_FEE_EXL.bat](template/SERVICE_FEE_EXL.bat) 為範本建立新檔，不是只回覆內容。
   - 將範本內的 `SERVICE_FEE_EXL.bat` 名稱替換成使用者指定的新 bat 名稱。
   - 將範本內 `PowerShell -Command ..\shell\SERVICE_FEE_EXL.ps1 %0; exit $LASTEXITCODE` 的 `.ps1` 名稱，替換成與新 bat 對應的 PowerShell 名稱。
   - 除了檔名與 PowerShell 名稱外，其餘 batch 結構、log 輸出與 errorlevel 判斷維持範本格式。
2. 修改指定的大 bat。
   - 使用者提供 `大 bat 路徑` 與 `要插入呼叫的新 bat 名稱`。
   - 以 [template/JGP_M_OMBT_GRANT_TPASS.bat](template/JGP_M_OMBT_GRANT_TPASS.bat) 中 `SERVICE_FEE_EXL` 這一段為參考。
   - 在使用者指定的大 bat 內，新增對應 label 區塊、`set step_job=新 bat 名稱`、`set step_log=...`、`call 新 bat 名稱`，以及成功失敗跳轉。
   - 新增位置固定插在文件 `success` 區塊之前；若前一個 step 的成功分支原本是直接 `GOTO :success`，要一併改成 `GOTO :新 bat label`，讓新 step 成為實際流程中的下一步，不可只塞一行 `call xxx.bat`。
   - 若大 bat 已存在相同 step，改為調整既有區塊，不重複新增。

## 輸入規則
- 若使用者只給新 bat 建立需求，至少要有 `目標路徑`、`新 bat 名稱`，並確認對應的 `.ps1` 名稱。
- 若使用者要修改大 bat，至少要有 `大 bat 路徑` 與 `要插入的新 bat 名稱`。
- 若 `.ps1` 名稱未提供，預設以新 bat 名稱去掉 `.bat` 後改成 `.ps1`。
- 修改大 bat 時不需要使用者指定插入位置，一律插在 `success` 區塊之前。

## 執行要求
- 使用者要求「建立」或「修改」時，直接動手編輯指定檔案，不要只提供教學。
- 建立 bat 時，只以 [template/SERVICE_FEE_EXL.bat](template/SERVICE_FEE_EXL.bat) 當範本。
- 修改大 bat 時，只以 [template/JGP_M_OMBT_GRANT_TPASS.bat](template/JGP_M_OMBT_GRANT_TPASS.bat) 的 step 區塊當格式參考。
- 保留原有編碼與換行風格；若檔案含中文，驗證時以 UTF-8 解析，避免誤判。
- 若需求同時包含建立 bat 與修改大 bat，依序先建立新 bat，再更新大 bat。

## 參考檔案
- [template/SERVICE_FEE_EXL.bat](template/SERVICE_FEE_EXL.bat)
- [template/JGP_M_OMBT_GRANT_TPASS.bat](template/JGP_M_OMBT_GRANT_TPASS.bat)

## 參數範例
- `建立 c:\path\to\bat\NEW_JOB.bat，PowerShell 用 NEW_JOB.ps1`
- `修改 c:\path\to\bat\JGP_M_xxx.bat，插入 call NEW_JOB.bat`
- `先建立 c:\path\to\bat\A123_JOB.bat，再修改 c:\path\to\bat\JGP_M_MAIN.bat 掛上 A123_JOB.bat`
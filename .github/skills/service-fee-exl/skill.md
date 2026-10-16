---
name: service-fee-exl
description: '用於依指定路徑與檔名建立 SERVICE_FEE_EXL 批次工作，包含建立 bat / ps1 檔案、改名、PowerShell 呼叫目標抽換、SERVICE_FEE_EXL 命名替換、TPASS 匯出流程調整與 reportctl.ini 對應設定。'
argument-hint: '輸入目標路徑、檔名、bat / ps1 類型或要替換的字串'
user-invocable: true
---

# SERVICE_FEE_EXL 批次產生

## 適用情境
- 需要依指定路徑與檔名建立新的 `SERVICE_FEE_EXL` 批次檔
- 需要從 `OMBT_TPASS_EXL` 複製或搬移出新的 `SERVICE_FEE_EXL` 批次檔
- 需要把對應的 PowerShell 入口檔從 `OMBT_TPASS_EXL*.ps1` 改成 `SERVICE_FEE_EXL*.ps1`
- 需要抽換 bat 內的 PowerShell 呼叫路徑、檔名、或 `SERVICE_FEE_EXL` 相關字串
- 需要整理 TPASS 匯出流程，並同步補 `reportctl.ini` 的設定區段

## 作法
1. 先根據使用者提供的目標路徑與檔名，決定要建立的 `bat` 或 `ps1`。
2. 若是建立 `SERVICE_FEE_EXL.bat`，把 PowerShell 呼叫改成 `..\shell\SERVICE_FEE_EXL.ps1`。
3. 若是建立 `SERVICE_FEE_EXL.ps1`，同步把標題、檔名、`iniSection` 前綴改成 `SERVICE_FEE_EXL`。
4. 若使用者是要「直接建立檔案」，就以指定路徑為準產生對應檔案，不要只回覆說明。
5. 若沒有新的資料路徑需求，維持既有執行流程、參數處理與 DLL 載入方式不變。
6. 如果腳本會讀取 `reportctl.ini`，要一併補上對應的 `SERVICE_FEE_EXL_*` 區段。
7. 檔案內容含中文或中文路徑時，驗證 `.ps1` 時請用 UTF-8 方式解析，避免誤判。

## 參考檔案
- [OMBT_TPASS_EXL.bat](../../../正式機/_ICASH_TPASS/ICMS/bat/OMBT_TPASS_EXL.bat)
- [OMSH_TPASS_GENM_EXL.ps1](../../../正式機/_ICASH_TPASS/ICMS/shell/OMSH_TPASS_GENM_EXL.ps1)
- [SERVICE_FEE_EXL.bat](../../../正式機/_ICASH_TPASS/ICMS/bat/SERVICE_FEE_EXL.bat)
- [SERVICE_FEE_EXL.ps1](../../../正式機/_ICASH_TPASS/ICMS/shell/SERVICE_FEE_EXL.ps1)

## 範本
- [template/OMBT_Tycg_EXL_0301.bat](template/OMBT_Tycg_EXL_0301.bat)
- [template/OMSH_Tycg_GENM_EXL_0301.ps1](template/OMSH_Tycg_GENM_EXL_0301.ps1)
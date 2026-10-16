# SERVICE_FEE_EXL 批次建立 Prompt

## 目的
依據使用者提供的多行參數（格式：`'CODE', #中文名`），在 `REPORTCTL_INI_PATH` 批次建立多個 `<SECTION_PREFIX>_*` 區塊。

## 可調整參數
- `REPORTCTL_INI_PATH`：目標 ini 路徑（預設：`正式機/_ICASH_TPASS/ICMS/parm/ini/reportctl.ini`）
- `SECTION_PREFIX`：section 前綴（預設：`SERVICE_FEE_EXL`）
- `TEMPLATE_CODE`：範本代碼（預設：`KEELUNG`）
- `TEMPLATE_SECTION`：`[<SECTION_PREFIX>_<TEMPLATE_CODE>]`

## 你要做的事
1. 讀取 `REPORTCTL_INI_PATH` 的 `TEMPLATE_SECTION` 作為唯一範本（預設即 `[SERVICE_FEE_EXL_KEELUNG]`）。
2. 解析我提供的參數清單（每行格式：`'CODE', #中文名`）。
3. 對每個參數建立一個新區塊：`[<SECTION_PREFIX>_<CODE>]`。
4. 只替換以下欄位，其餘欄位保持和 `TEMPLATE_SECTION` 範本一致：
  - 區段名稱（`[<SECTION_PREFIX>_<TEMPLATE_CODE>]` -> `[<SECTION_PREFIX>_<CODE>]`）
   - `cptIntervalRef_MERCHANT_NO`
   - `sqlFile_MERCHANT_NO`
   - `title1`
   - `file_name`
5. 若目標區塊已存在（同名 section），改為更新該區塊內容，不要重複新增。
6. 一次處理全部參數，不要只做第一筆。

## 輸入格式
我會貼這種清單：

```txt
'NANTOU', #南投
'TAICHUNG', #台中
'CHANGHUA', #彰化
'CCTM', #中彰投苗
'CHIAYI', #嘉義
'YUNLIN_199', #雲林199
'YUNLIN_399', #雲林399
'HUALIEN_199', #花蓮199
'HUALIEN_399', #花蓮399
'TAITUNG', #台東
'YILAN', #宜蘭
'YILAN_StateRoad' #宜蘭國道
```

## 欄位組字規則
### A. 預設規則
- `merchantLabel`（給 `cptIntervalRef_MERCHANT_NO` / `sqlFile_MERCHANT_NO` / `title1` 用）
  - 預設：`<中文名>區月票`
- `fileLabel`（給 `file_name` 用）
  - 預設：`<中文名>月票手續費`

### B. 特例優先（先套特例，再套預設）
- `CCTM`:
  - `merchantLabel=中彰投苗月票`
  - `fileLabel=中彰投苗月票手續費`
- `YUNLIN_199`:
  - `merchantLabel=雲林199月票`
  - `fileLabel=雲林199月票手續費`
- `YUNLIN_399`:
  - `merchantLabel=雲林399月票`
  - `fileLabel=雲林399月票手續費`
- `HUALIEN_199`:
  - `merchantLabel=花蓮199月票`
  - `fileLabel=花蓮199月票手續費`
- `HUALIEN_399`:
  - `merchantLabel=花蓮399月票`
  - `fileLabel=花蓮399月票手續費`
- `YILAN_StateRoad`:
  - `merchantLabel=宜蘭國道月票`
  - `fileLabel=宜蘭國道月票手續費`

## 替換模板
- `cptIntervalRef_MERCHANT_NO=<merchantLabel>`
- `sqlFile_MERCHANT_NO=<merchantLabel>`
- `title1=*1yyy年*1MM月<merchantLabel>|LAST_MONTH|1|A1:C1|NONE|NONE`
- `file_name=*1yyy年*1MM月<fileLabel>.xlsx|LAST_MONTH`

## 輸出要求
1. 直接修改 `REPORTCTL_INI_PATH`，不要只回說明。
2. 完成後列出：
   - 成功新增/更新的 section 名稱清單
   - 若有跳過（格式錯誤或缺中文名）請列原因
3. 不要改動非 `<SECTION_PREFIX>_*` 區塊。

## 這次可直接使用的參數清單（可覆蓋）
```txt
'NANTOU', #南投
'TAICHUNG', #台中
'CHANGHUA', #彰化
'CCTM', #中彰投苗
'CHIAYI', #嘉義
'YUNLIN_199', #雲林199
'YUNLIN_399', #雲林399
'HUALIEN_199', #花蓮199
'HUALIEN_399', #花蓮399
'TAITUNG', #台東
'YILAN', #宜蘭
'YILAN_StateRoad' #宜蘭國道
```

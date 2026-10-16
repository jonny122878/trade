---
mode: agent
description: Parse T1 record and answer field questions
---

When the user provides a T1 data record, do the following:

1. Run this command to parse it (replace <record> with the actual data):
   powershell -ExecutionPolicy Bypass -File "C:\Users\G0080\Desktop\Programs\T1\parse_T1_record.ps1" "<record>"

2. Display the full parsed output in the conversation.

3. Answer any questions the user has about the field values, based on the T1 field definitions in T1/T1_explain.md.

Field reference:
- BusDate(0,8): 營業日
- StoreNo(8,5): 路線編號
- StationNo(13,3): 站別
- DriverNo(16,5): 駕員編號
- LicenseNo(21,10): 車號
- ShiftTime(31,10): 開班日
- AreaCode(41,2): 固定00
- TicketType(43,2): 票種
- BoardingQty(45,5): 上車人次
- BoardingSeq(50,5): 旅次數
- TotalTxnAmt(55,6): 交易總金額
- QuestCsc(61,6): 固定000000
- ISSUER_ID(67,6): 003000=電票 003001=電支
- TestcardAmt(73,6): 固定000000
- RealPymnt(79,6): 實付金額
- TrfMRTBUSseq(85,5): 捷運轉公車筆數
- TrfMRTBUSamt(90,6): 捷運轉公車優惠金額
- Payment_Type(96,10): CCH=電票 QR=電支
- Field_C(106,6): 固定000000
- TrfMRTBUSpymnt(112,6): 捷運轉公車類實付
- Field_D(118,6): 固定000000
- Field_E(124,6): 固定000000
- Field_F(130,6): 固定000000
- PersonalDisc(136,6): 個人優惠合計
- TrfBUSseq(142,5): 公車轉公車筆數
- TrfBUSamt(147,6): 公車轉公車金額
- TrfERRseq(153,5): 非定義轉乘筆數
- TrfERRamt(158,6): 非定義轉乘金額
- TrfERRpymnt(164,6): 非定義轉乘實付
- TrasnsMRTBUSpymnt(170,6): 捷運轉公車實付合計
- TrasnsBUSpymnt(176,6): 公車轉公車實付
- TrasnsERRpymnt(182,6): 非定義轉乘實付
- PointAmt(188,6): 點數/社福優惠
- PointsMRTBUSdisc(194,6): 捷運轉公車點數優惠
- PointsBUSMRTdisc(200,6): 公車轉捷運點數優惠
- TrfERRdisc(206,6): 非定義轉乘點數優惠
- FILE_CptDate(212,8): 清分日
- FareType(220,3): 固定000
- XferCountUbike(223,5): YouBike轉乘筆數(固定)
- XferAmtUbike(228,6): YouBike轉乘金額(固定)
- RealPymntUbike(234,6): YouBike實付(固定)
- PersonalDiscUbike(240,6): YouBike優惠(固定)
- line_state(246,1): T=有效 F=剔退
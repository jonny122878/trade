@echo off
echo ----------------------START 執行批次檔----------------------
echo -- 執行批次路徑=%~dp0
echo -- 執行批次檔  =%0
echo -- 執行開始時間=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo ------------------------------------------------------------

PowerShell –Command ..\shell\OMSH_Tycg_GENM_EXL_0301.ps1 %0; exit $LASTEXITCODE


echo -----------------------批次檔執行結果-----------------------
IF %errorlevel%==1 ( set result="FAIL" ) ELSE ( set result="SUCCESS" )
echo -- 執行批次檔=%0，結果=%result%
echo -- 執行完成時間=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo -----------------------END 執行批次檔-----------------------
@echo off
::--------------------
set job_sdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
::--------------------
set jobdate=%date:~0,4%%date:~5,2%%date:~8,2%
set job_path=%~d0%~p0
cd %~dp0
cd ..
set parent_path=%cd%
cd %job_path%
echo ----------------------START 執行批次檔----------------------
echo -- 執行批次路徑=%job_path%
echo -- 執行批次檔  =%0
echo -- 執行開始時間=%job_sdate%
echo ------------------------------------------------------------

for /f "tokens=*" %%V in ('POWERSHELL –Command ..\shell\COSH_GET_LOG_PATH.ps1; exit $LASTEXITCODE') do set logpath=%%V
set log_path=%parent_path%\%logpath%

::------------------------------------------------------------
::
::------------------------------------------------------------
:OMBT_TPASS_CLEAN_FILE_FOLDER
echo --[OMBT_TPASS_CLEAN_FILE_FOLDER.bat]
set step_job=OMBT_TPASS_CLEAN_FILE_FOLDER.bat
set step_log=%log_path%%step_job%_%jobdate%.log
::--------------------
set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo     [執行開始時間]=%fdate%
::--------------------
call %step_job% > %step_log%

IF %errorlevel%==1  GOTO :fail
IF %errorlevel%==0  GOTO :SERVICE_FEE_EXL

::------------------------------------------------------------
::
::------------------------------------------------------------
:SERVICE_FEE_EXL
call COBT_Change_LOG.bat %step_log%
set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo     [執行完成時間]=%fdate%
echo     [執行結果]=SUCCESS
echo ............................................................
echo --[SERVICE_FEE_EXL.bat]
set step_job=SERVICE_FEE_EXL.bat
set step_log=%log_path%%step_job%_%jobdate%.log
::--------------------
set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo     [執行開始時間]=%fdate%
::--------------------
call %step_job% > %step_log%

IF %errorlevel%==1  GOTO :fail
IF %errorlevel%==0  GOTO :success

REM ::------------------------------------------------------------
REM ::
REM ::------------------------------------------------------------
REM :OMBT_TPASS_EXL
REM call COBT_Change_LOG.bat %step_log%
REM set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
REM echo     [執行完成時間]=%fdate%
REM echo     [執行結果]=SUCCESS
REM echo ............................................................
REM echo --[OMBT_TPASS_EXL.bat]
REM set step_job=OMBT_TPASS_EXL.bat
REM set step_log=%log_path%%step_job%_%jobdate%.log
REM ::--------------------
REM set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
REM echo     [執行開始時間]=%fdate%
REM ::--------------------
REM call %step_job% > %step_log%

REM IF %errorlevel%==1  GOTO :fail
REM IF %errorlevel%==0  GOTO :success


REM --SUCCESS--------------------------------------------------
:success

	call COBT_Change_LOG.bat %step_log%
	set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
	echo     [執行完成時間]=%fdate%
	echo     [執行結果]=SUCCESS
	GOTO :finish

REM --FAIL-----------------------------------------------------
:fail

	call COBT_Change_ERR.bat %step_log%
	set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
	echo     [執行完成時間]=%fdate%
	echo     [執行結果]=FAIL
	exit /b 1

REM --FINISH---------------------------------------------------
:finish

echo ------------------------------------------------------------
set fdate=%date:~0,4%/%date:~5,2%/%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%
echo -- 執行批次檔=%0，結果=%result%
echo -- 執行完成時間=%fdate%
echo -------------------------END 執行批次檔----------------------
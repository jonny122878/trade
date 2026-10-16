# ============================================================
# PROGRAM : 桃園市公車補助報表_補貼款申請表_非市民卡
# 說明    : 
# ============================================================
# 撰寫者  :
# 撰寫日期:
# 修改者  :
# 修改日期:
# ============================================================

# ====================================================================
# == JOB START ==
# ====================================================================
$ErrorActionPreference = 'Stop'
$path_ShellFolder = Split-Path $MyInvocation.MyCommand.Path
$job_Path = $path_ShellFolder
$name_Shell = $MyInvocation.MyCommand.Name
$path_Parent = Split-Path $path_ShellFolder
$parent_Path = $path_Parent
$time_Start = Get-Date -Format 'yyyy/MM/dd HH:mm:ss'

Write-Host '=========================================================='
Write-Host "[SHELL_PATH] = $path_ShellFolder"
Write-Host "[SHELL_NAME] = $name_Shell"
Write-Host "[PARENT_PATH]= $path_Parent"
Write-Host "[START_TIME] = $time_Start"
Write-Host '=========================================================='

# ====================================================================
# == 取得參數 ==
# ====================================================================
$path_ApFolder = $path_Parent + '\ap\'
$ap_FullPath = $path_ApFolder
Write-Host "[取得ap資料夾]=$path_ApFolder"

$path_IniSetup = $path_Parent + '\parm\ini\setup.ini'
$fullIni = $path_IniSetup
Write-Host "[取得setup.ini]=$path_IniSetup"

$path_LoadDll = $path_ShellFolder + '\COSH_IMPORT.ps1'
Write-Host "[取得共用DLL]=$path_LoadDll"
Import-Module $path_LoadDll

$path_DBParam = $path_ShellFolder + '\COSH_GET_DBINFO.ps1'
Write-Host "[取得DB帳密資訊]=$path_DBParam"
Import-Module $path_DBParam

$obj_CO_SetSettleDate = New-Object CO_SetSettleDate.CO_SetSettleDate
$cptDate = $obj_CO_SetSettleDate.GetSettleDate($Args[0])
if ($cptDate -eq 'FALSE')
{
    Write-Host '[ERROR]=清算日期 today.dat'
    exit 1
}

$obj_IniManager = New-Object icash.Tools.IniManager
$str_Rerun_SchemaID = $obj_IniManager.ReadValue('GrantReportRerun','GrantTycg_SchemaID',$path_IniSetup,'FALSE')
if ($str_Rerun_SchemaID -eq 'FALSE')
{
    Write-Host '[ERROR]=機構重跑SchemaID setup.ini [GrantReportRerun]GrantTycg_SchemaID'
    exit 1
}

# ====================================================================
# == 開始執行 ==
# ====================================================================
[string[]] $arr_MerchSchemaID =
'B116',#國光客運
'B301',#統聯客運(桃園)
'B303',#中壢客運
'B304',#亞通客運
'B306',#新竹客運
'B307',#金牌客運(金台通運)
'B313',#指南客運(桃園)
'B315',#捷順桃園
'B317',#三重客運(桃竹苗)
'B318', #桃園客運(Acer)
'B322' #真好小客車租賃股份有限公司

$path_FileFolder = $path_Parent + '\ftpdata\OUT_GRANT_M\GrantTycg'
if ([System.IO.Directory]::Exists($path_FileFolder) -eq $False) { $createResult = [System.IO.Directory]::CreateDirectory($path_FileFolder) }

$arr_Rerun_SchemaID = $Null
$str_Rerun_SchemaID = $str_Rerun_SchemaID.Replace(' ','')
if (($str_Rerun_SchemaID -ne '') -and ($str_Rerun_SchemaID.ToUpper() -ne 'ALL')) { $arr_Rerun_SchemaID = $str_Rerun_SchemaID.Split(',') }

$pathParam_Dll = 'OM_GEN_EXL_SIMPLE.dll'
$path_Dll = $path_ApFolder + '\' + $pathParam_Dll
Import-Module $path_Dll
Write-Host "[LOAD DLL]=$path_Dll"

$obj_OM_GEN_EXL_SIMPLE = New-Object OM_GEN_EXL_SIMPLE.OM_GEN_EXL_SIMPLE
for ($i = 0; $i -lt $arr_MerchSchemaID.Length; $i++)
{
	if ($arr_Rerun_SchemaID -and $arr_Rerun_SchemaID -is [array])
	{
		if ($arr_Rerun_SchemaID.Length -ne $Null)
		{
			if ([System.Array]::IndexOf($arr_Rerun_SchemaID, $arr_MerchSchemaID[$i]) -eq (-1)) { continue }
		}
	}

	$path_MerchantFileFolder = $path_FileFolder + '\' + $arr_MerchSchemaID[$i]
	if ([System.IO.Directory]::Exists($path_MerchantFileFolder) -eq $False) { $createResult = [System.IO.Directory]::CreateDirectory($path_MerchantFileFolder) }

	$iniSection = 'OMSH_Tycg_GENM_EXL_0301' + '_' + $arr_MerchSchemaID[$i]
	$remittance_SettleType = 'A'
	$callResult = $obj_OM_GEN_EXL_SIMPLE.Execute($Args[0], $DBId, $DBPwd, $cptDate, $remittance_SettleType, $iniSection)
	if ($callResult -eq 'FALSE')
	{
		Write-Host "Table Schema:"$arr_MerchSchemaID[$i] "機構執行失敗"
		exit 1
	}
}

# ====================================================================
# == JOB END ==
# ====================================================================
$time_End = Get-Date -Format 'yyyy/MM/dd HH:mm:ss'

Write-Host ''
Write-Host '=========================================================='
Write-Host "[SHELL_NAME]= $name_Shell"
Write-Host "[START_TIME]= $time_Start"
Write-Host "[END_TIME]  = $time_End"
Write-Host "[RESULT]    = $callResult"
Write-Host '=========================================================='
Write-Host ''
$ErrorActionPreference = 'Stop'

function Get-FilePathsFromValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return @()
    }

    if ($Value -is [string]) {
        return @()
    }

    if ($Value -is [System.Collections.IDictionary]) {
        $paths = @()
        foreach ($key in $Value.Keys) {
            if ($key -match '^(filePath|path)$' -and $Value[$key] -is [string]) {
                $paths += $Value[$key]
            }
            $paths += Get-FilePathsFromValue -Value $Value[$key]
        }
        return $paths
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $paths = @()
        foreach ($item in $Value) {
            $paths += Get-FilePathsFromValue -Value $item
        }
        return $paths
    }

    return @()
}

try {
    $event = [Console]::In.ReadToEnd() | ConvertFrom-Json -AsHashtable
    $sqlFiles = Get-FilePathsFromValue -Value $event.tool_input |
        Where-Object { $_ -match '\.sql$' -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -Unique

    foreach ($sqlFile in $sqlFiles) {
        $header = (Get-Content -LiteralPath $sqlFile -TotalCount 20 -Raw).TrimStart([char]0xFEFF)
        $hasCommentedCptDate = $header -match '(?im)^\s*--\s*DECLARE\s+@EXEC_CPT_DATE\b'
        $hasCommentedMerchantNo = $header -match '(?im)^\s*--\s*DECLARE\s+@EXEC_MERCHANT_NO\b'
        $hasActiveCptDate = $header -match '(?im)^\s*DECLARE\s+@EXEC_CPT_DATE\b'
        $hasActiveMerchantNo = $header -match '(?im)^\s*DECLARE\s+@EXEC_MERCHANT_NO\b'

        if (-not $hasCommentedCptDate -or -not $hasCommentedMerchantNo -or $hasActiveCptDate -or $hasActiveMerchantNo) {
            @{
                decision = 'block'
                reason = "SQL parameter header validation failed: $sqlFile must include commented --DECLARE @EXEC_CPT_DATE and --DECLARE @EXEC_MERCHANT_NO declarations within its first 20 lines. Ask the user to confirm before continuing."
                hookSpecificOutput = @{
                    hookEventName = 'PostToolUse'
                    additionalContext = 'Do not continue editing this SQL file until the user confirms the required commented parameter declarations.'
                }
            } | ConvertTo-Json -Compress
            exit 0
        }
    }
}
catch {
    [Console]::Error.WriteLine("SQL parameter header hook failed: $($_.Exception.Message)")
    exit 2
}

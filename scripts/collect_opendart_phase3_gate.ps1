param(
    [string]$EnvFile = ".env",
    [string]$StartDate = "20260101",
    [string]$EndDate = "20260831",
    [string]$BaselineFile = "raw/dart/disclosures_20260101_20260831.json"
)

$ErrorActionPreference = "Stop"

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line -split '=', 2
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Save-JsonUtf8 {
    param(
        [Parameter(Mandatory)]$Object,
        [Parameter(Mandatory)][string]$Path
    )
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location) $Path),
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Get-FileHashHex {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$config = Read-DotEnv -Path $EnvFile
$apiKey = $config['DART_API_KEY']
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "DART_API_KEY is empty in $EnvFile"
}
if ($apiKey.Length -ne 40) {
    throw "DART_API_KEY must be 40 characters; current length is $($apiKey.Length)"
}

$baseUrl = $config['DART_BASE_URL'].TrimEnd('/')
$corpCode = $config['DART_CORP_CODE']
$endpoint = $config['DART_DISCLOSURE_LIST_ENDPOINT']
$retrievedAt = [DateTimeOffset]::Now
$runId = $retrievedAt.ToString('yyyyMMddTHHmmsszzz').Replace(':', '')
$gateRoot = "raw/dart/phase3/gates/$runId"
$responsePath = "$gateRoot/disclosures_${StartDate}_${EndDate}.json"
$summaryPath = "$gateRoot/gate_summary.json"

$request = @{
    crtfc_key     = $apiKey
    corp_code     = $corpCode
    bgn_de        = $StartDate
    end_de        = $EndDate
    last_reprt_at = "N"
    page_no       = "1"
    page_count    = "100"
    sort          = "date"
    sort_mth      = "asc"
}
$response = Invoke-RestMethod -Method Get -Uri "$baseUrl/$($endpoint.TrimStart('/'))" -Body $request -TimeoutSec 60
$apiCallCount = 1
$pagesFetched = [System.Collections.Generic.List[int]]::new()
$pagesFetched.Add(1)

if ($response.status -ne "000") {
    throw "OpenDART list query failed: status=$($response.status), message=$($response.message)"
}

if ($null -ne $response.total_page -and [int]$response.total_page -gt 1) {
    $allRows = [System.Collections.Generic.List[object]]::new()
    foreach ($row in @($response.list)) { $allRows.Add($row) }
    for ($page = 2; $page -le [int]$response.total_page; $page++) {
        $pageRequest = @{} + $request
        $pageRequest['page_no'] = [string]$page
        $pageResponse = Invoke-RestMethod -Method Get -Uri "$baseUrl/$($endpoint.TrimStart('/'))" -Body $pageRequest -TimeoutSec 60
        if ($pageResponse.status -ne "000") {
            throw "OpenDART paged response failed at page ${page}: status=$($pageResponse.status)"
        }
        foreach ($row in @($pageResponse.list)) { $allRows.Add($row) }
        $pagesFetched.Add($page)
        $apiCallCount++
    }
    $response.list = @($allRows)
}

Save-JsonUtf8 -Object $response -Path $responsePath

$baselineRows = @()
if (Test-Path -LiteralPath $BaselineFile) {
    $baseline = Get-Content -LiteralPath $BaselineFile -Encoding utf8 -Raw | ConvertFrom-Json
    $baselineRows = @($baseline.list)
}
$baselineReceiptNos = @{}
foreach ($row in $baselineRows) { $baselineReceiptNos[[string]$row.rcept_no] = $true }

$rows = @($response.list)
$newRows = @($rows | Where-Object { -not $baselineReceiptNos.ContainsKey([string]$_.rcept_no) })
$periodicPattern = '\uBD84\uAE30\uBCF4\uACE0\uC11C|\uBC18\uAE30\uBCF4\uACE0\uC11C|\uC0AC\uC5C5\uBCF4\uACE0\uC11C'
$halfYearPattern = '\uBC18\uAE30\uBCF4\uACE0\uC11C'
$contractPattern = '\uB2E8\uC77C\uD310\uB9E4|\uACF5\uAE09\uACC4\uC57D|\uACC4\uC57D.*\uD574\uC9C0|\uD574\uC9C0.*\uACC4\uC57D'
$correctionPattern = '^\[\uAE30\uC7AC\uC815\uC815\]|^\[\uCCA8\uBD80\uC815\uC815\]|^\[\uC815\uC815'
$terminationPattern = '\uD574\uC9C0|\uCDE8\uC18C'
$relevantPattern = "$periodicPattern|$contractPattern|$terminationPattern"
$periodicRows = @($rows | Where-Object { $_.report_nm -match $periodicPattern })
$halfYearRows = @($rows | Where-Object { $_.report_nm -match $halfYearPattern })
$contractRows = @($rows | Where-Object { $_.report_nm -match $contractPattern })
$correctionRows = @($rows | Where-Object { $_.report_nm -match $correctionPattern })
$terminationRows = @($rows | Where-Object { $_.report_nm -match $terminationPattern })
$newRelevantRows = @($newRows | Where-Object { $_.report_nm -match $relevantPattern })

$sanitizedParameters = [ordered]@{
    corp_code     = $corpCode
    bgn_de        = $StartDate
    end_de        = $EndDate
    last_reprt_at = "N"
    page_no       = "1"
    page_count    = "100"
    sort          = "date"
    sort_mth      = "asc"
}

$summary = [ordered]@{
    phase = "Phase 3 latest-disclosure gate"
    source = "OpenDART disclosure list API"
    endpoint = $endpoint
    parameters = $sanitizedParameters
    retrieved_at = $retrievedAt.ToString('yyyy-MM-ddTHH:mm:sszzz')
    project_cutoff = $retrievedAt.ToString('yyyy-MM-ddTHH:mm:sszzz')
    status = $response.status
    message = $response.message
    api_call_count = $apiCallCount
    pages_fetched = @($pagesFetched)
    row_count = $rows.Count
    baseline_file = $BaselineFile.Replace('\', '/')
    baseline_row_count = $baselineRows.Count
    new_since_baseline_count = $newRows.Count
    new_since_baseline = $newRows
    periodic_count = $periodicRows.Count
    latest_periodic = @($periodicRows | Sort-Object rcept_dt, rcept_no | Select-Object -Last 1)
    half_year_count = $halfYearRows.Count
    half_year_filings = $halfYearRows
    contract_related_count = $contractRows.Count
    contract_related_filings = $contractRows
    correction_count = $correctionRows.Count
    termination_or_cancellation_count = $terminationRows.Count
    termination_or_cancellation_filings = $terminationRows
    new_relevant_count = $newRelevantRows.Count
    new_relevant_filings = $newRelevantRows
    response_file = $responsePath.Replace('\', '/')
    response_sha256 = Get-FileHashHex -Path $responsePath
    api_key_logged = $false
}
Save-JsonUtf8 -Object $summary -Path $summaryPath

[pscustomobject]@{
    retrieved_at = $summary.retrieved_at
    row_count = $summary.row_count
    baseline_row_count = $summary.baseline_row_count
    new_since_baseline_count = $summary.new_since_baseline_count
    half_year_count = $summary.half_year_count
    contract_related_count = $summary.contract_related_count
    termination_or_cancellation_count = $summary.termination_or_cancellation_count
    new_relevant_count = $summary.new_relevant_count
    summary_file = $summaryPath
}

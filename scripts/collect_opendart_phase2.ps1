param(
    [string]$EnvFile = ".env",
    [string]$CutoffDate = "20260831"
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
$rawRoot = $config['DART_RAW_DIR']
$retrievedAt = [DateTimeOffset]::Now.ToString('yyyy-MM-ddTHH:mm:sszzz')
$manifestRows = [System.Collections.Generic.List[object]]::new()

function Invoke-DartJson {
    param(
        [Parameter(Mandatory)][string]$Endpoint,
        [Parameter(Mandatory)][hashtable]$Parameters,
        [Parameter(Mandatory)][string]$OutputPath,
        [Parameter(Mandatory)][string]$Dataset
    )

    $request = @{} + $Parameters
    $request['crtfc_key'] = $script:apiKey
    $response = Invoke-RestMethod -Method Get -Uri "$script:baseUrl/$($Endpoint.TrimStart('/'))" -Body $request -TimeoutSec 60
    $pagesFetched = [System.Collections.Generic.List[int]]::new()
    $pagesFetched.Add(1)
    $apiCallCount = 1

    if ($null -ne $response.total_page -and [int]$response.total_page -gt 1) {
        $allRows = [System.Collections.Generic.List[object]]::new()
        foreach ($row in @($response.list)) { $allRows.Add($row) }
        for ($page = 2; $page -le [int]$response.total_page; $page++) {
            $pageRequest = @{} + $request
            $pageRequest['page_no'] = [string]$page
            $pageResponse = Invoke-RestMethod -Method Get -Uri "$script:baseUrl/$($Endpoint.TrimStart('/'))" -Body $pageRequest -TimeoutSec 60
            if ($pageResponse.status -ne $response.status) {
                throw "OpenDART paged response status mismatch at page $page"
            }
            foreach ($row in @($pageResponse.list)) { $allRows.Add($row) }
            $pagesFetched.Add($page)
            $apiCallCount++
        }
        $response.list = @($allRows)
    }
    Save-JsonUtf8 -Object $response -Path $OutputPath

    $sanitized = @{} + $Parameters
    $rowCount = if ($null -ne $response.list) { @($response.list).Count } else { 1 }
    $script:manifestRows.Add([pscustomobject]@{
        dataset       = $Dataset
        endpoint      = $Endpoint
        parameters    = ($sanitized | ConvertTo-Json -Compress)
        retrieved_at  = $script:retrievedAt
        status        = $response.status
        message       = $response.message
        row_count     = $rowCount
        api_call_count = $apiCallCount
        pages_fetched = @($pagesFetched)
        output_file   = $OutputPath.Replace('\', '/')
        sha256        = Get-FileHashHex -Path $OutputPath
    })
    return $response
}

function Invoke-DartDocument {
    param(
        [Parameter(Mandatory)][string]$ReceiptNo,
        [Parameter(Mandatory)][string]$OutputPath
    )

    $parent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $tempPath = "$OutputPath.download"
    Invoke-WebRequest -Method Get -Uri "$script:baseUrl/document.xml" -Body @{
        crtfc_key = $script:apiKey
        rcept_no  = $ReceiptNo
    } -OutFile $tempPath -TimeoutSec 90

    $bytes = [System.IO.File]::ReadAllBytes((Join-Path (Get-Location) $tempPath))
    $isZip = $bytes.Length -ge 2 -and $bytes[0] -eq 0x50 -and $bytes[1] -eq 0x4B
    if (-not $isZip) {
        $errorText = [System.Text.Encoding]::UTF8.GetString($bytes)
        Remove-Item -LiteralPath $tempPath -Force
        throw "OpenDART document download failed for receipt ${ReceiptNo}: $errorText"
    }

    Move-Item -LiteralPath $tempPath -Destination $OutputPath -Force
    $extractDir = Join-Path $script:rawRoot "documents/extracted/$ReceiptNo"
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    Expand-Archive -LiteralPath $OutputPath -DestinationPath $extractDir -Force

    $script:manifestRows.Add([pscustomobject]@{
        dataset       = "document_$ReceiptNo"
        endpoint      = "/document.xml"
        parameters    = (@{ rcept_no = $ReceiptNo } | ConvertTo-Json -Compress)
        retrieved_at  = $script:retrievedAt
        status        = "000"
        message       = "정상"
        row_count     = @(Get-ChildItem -LiteralPath $extractDir -File -Recurse).Count
        api_call_count = 1
        pages_fetched = @()
        output_file   = $OutputPath.Replace('\', '/')
        sha256        = Get-FileHashHex -Path $OutputPath
    })
}

New-Item -ItemType Directory -Path $rawRoot -Force | Out-Null

$company = Invoke-DartJson -Endpoint $config['DART_COMPANY_ENDPOINT'] -Parameters @{
    corp_code = $corpCode
} -OutputPath "$rawRoot/company.json" -Dataset "company"

$allDisclosures = Invoke-DartJson -Endpoint $config['DART_DISCLOSURE_LIST_ENDPOINT'] -Parameters @{
    corp_code     = $corpCode
    bgn_de        = $config['DART_BGN_DATE']
    end_de        = $CutoffDate
    last_reprt_at = "N"
    page_no       = "1"
    page_count    = "100"
    sort          = "date"
    sort_mth      = "asc"
} -OutputPath "$rawRoot/disclosures_$($config['DART_BGN_DATE'])_$CutoffDate.json" -Dataset "disclosures_all"

$disclosures2026 = Invoke-DartJson -Endpoint $config['DART_DISCLOSURE_LIST_ENDPOINT'] -Parameters @{
    corp_code     = $corpCode
    bgn_de        = "20260101"
    end_de        = $CutoffDate
    last_reprt_at = "N"
    page_no       = "1"
    page_count    = "100"
    sort          = "date"
    sort_mth      = "asc"
} -OutputPath "$rawRoot/disclosures_20260101_$CutoffDate.json" -Dataset "disclosures_2026"

$periodMatrix = @(
    @{ year = "2023"; code = "11013"; label = "Q1" },
    @{ year = "2023"; code = "11012"; label = "H1" },
    @{ year = "2023"; code = "11014"; label = "Q3" },
    @{ year = "2023"; code = "11011"; label = "FY" },
    @{ year = "2024"; code = "11013"; label = "Q1" },
    @{ year = "2024"; code = "11012"; label = "H1" },
    @{ year = "2024"; code = "11014"; label = "Q3" },
    @{ year = "2024"; code = "11011"; label = "FY" },
    @{ year = "2025"; code = "11013"; label = "Q1" },
    @{ year = "2025"; code = "11012"; label = "H1" },
    @{ year = "2025"; code = "11014"; label = "Q3" },
    @{ year = "2025"; code = "11011"; label = "FY" },
    @{ year = "2026"; code = "11013"; label = "Q1" },
    @{ year = "2026"; code = "11012"; label = "H1" }
)

$periodicReceiptNos = [System.Collections.Generic.List[string]]::new()
foreach ($period in $periodMatrix) {
    foreach ($fsDiv in @("CFS", "OFS")) {
        $file = "$rawRoot/financials/$($period.year)_$($period.label)_$fsDiv.json"
        $financialResponse = Invoke-DartJson -Endpoint $config['DART_FINANCIALS_ALL_ENDPOINT'] -Parameters @{
            corp_code  = $corpCode
            bsns_year  = $period.year
            reprt_code = $period.code
            fs_div     = $fsDiv
        } -OutputPath $file -Dataset "financials_$($period.year)_$($period.label)_$fsDiv"
        if ($fsDiv -eq "CFS" -and $null -ne $financialResponse.list -and @($financialResponse.list).Count -gt 0) {
            $periodicReceiptNos.Add([string]$financialResponse.list[0].rcept_no)
        }
    }

    foreach ($dataset in @(
        @{ name = "stock_total"; endpoint = $config['DART_STOCK_TOTAL_ENDPOINT'] },
        @{ name = "treasury_stock"; endpoint = $config['DART_TREASURY_STOCK_ENDPOINT'] },
        @{ name = "capital_change"; endpoint = $config['DART_CAPITAL_CHANGE_ENDPOINT'] },
        @{ name = "major_holder"; endpoint = $config['DART_MAJOR_HOLDER_ENDPOINT'] },
        @{ name = "major_holder_change"; endpoint = $config['DART_MAJOR_HOLDER_CHANGE_ENDPOINT'] }
    )) {
        $file = "$rawRoot/share/$($dataset.name)_$($period.year)_$($period.label).json"
        Invoke-DartJson -Endpoint $dataset.endpoint -Parameters @{
            corp_code  = $corpCode
            bsns_year  = $period.year
            reprt_code = $period.code
        } -OutputPath $file -Dataset "$($dataset.name)_$($period.year)_$($period.label)" | Out-Null
    }
}

$relevantReceiptNos = @(
    @($disclosures2026.list | ForEach-Object { [string]$_.rcept_no }) +
    @($periodicReceiptNos)
) | Sort-Object -Unique
foreach ($receiptNo in $relevantReceiptNos) {
    Invoke-DartDocument -ReceiptNo $receiptNo -OutputPath "$rawRoot/documents/$receiptNo.zip"
}

$manifest = [pscustomobject]@{
    run = [pscustomobject]@{
        retrieved_at    = $retrievedAt
        cutoff_date     = $CutoffDate
        corp_code       = $corpCode
        stock_code      = $config['DART_STOCK_CODE']
        api_key_logged  = $false
        collector       = "scripts/collect_opendart_phase2.ps1"
    }
    datasets = @($manifestRows)
}
Save-JsonUtf8 -Object $manifest -Path "$rawRoot/run_manifest.json"

$statusCounts = @($manifestRows | Group-Object status | Sort-Object Name | ForEach-Object {
    [pscustomobject]@{ status = $_.Name; count = $_.Count }
})
[pscustomobject]@{
    company_status       = $company.status
    disclosure_status    = $allDisclosures.status
    disclosures_total    = $allDisclosures.total_count
    disclosures_2026     = $disclosures2026.total_count
    relevant_documents   = $relevantReceiptNos.Count
    datasets_written     = $manifestRows.Count
    status_counts        = $statusCounts
    manifest             = "$rawRoot/run_manifest.json"
} | ConvertTo-Json -Depth 5

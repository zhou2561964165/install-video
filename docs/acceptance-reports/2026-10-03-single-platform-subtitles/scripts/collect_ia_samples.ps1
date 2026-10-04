$ErrorActionPreference = "Stop"
$ReportDir = "docs/acceptance-reports/2026-10-03-single-platform-subtitles"
$RawDir = Join-Path $ReportDir "raw-extra"
$StageDir = Join-Path $ReportDir "staging"
$LicenseDir = Join-Path $ReportDir "licenses"
$AllowedLicensePattern = '^https?://creativecommons\.org/licenses/by(?:-sa)?/[0-9.]+/?$'
$Samples = @(
    @{ sample_id="IA-youtube-6k-kbg3_Drc-en-vtt"; identifier="youtube-6k-kbg3_Drc"; file_name="Imagine_the_Consequences-6k-kbg3_Drc.en.vtt"; language="en" },
    @{ sample_id="IA-youtube-6k-kbg3_Drc-fr-vtt"; identifier="youtube-6k-kbg3_Drc"; file_name="Imagine_the_Consequences-6k-kbg3_Drc.fr.vtt"; language="fr" },
    @{ sample_id="IA-mnn_23214_387-en-srt"; identifier="mnn_23214_387"; file_name="23214_387.asr.srt"; language="en" },
    @{ sample_id="IA-mnn_23214_387-en-vtt"; identifier="mnn_23214_387"; file_name="23214_387.asr.vtt"; language="en" }
)

$MetadataByIdentifier = @{}
$Errors = @()
$Receipts = @()
$Utf8 = [System.Text.UTF8Encoding]::new($false)
foreach ($Sample in $Samples) {
    $RawPath = Join-Path $StageDir ($Sample.sample_id + "." + [IO.Path]::GetExtension($Sample.file_name).TrimStart('.'))
    $LicensePath = Join-Path $LicenseDir ($Sample.sample_id + ".license-metadata.json")
    $ReceiptPath = Join-Path $LicenseDir ($Sample.sample_id + ".capture.json")
    if ((Test-Path -LiteralPath $RawPath) -or (Test-Path -LiteralPath $LicensePath) -or (Test-Path -LiteralPath $ReceiptPath)) {
        $Errors += [pscustomobject]@{ sample_id=$Sample.sample_id; stage="preflight"; error_type="existing_file_refused" }
        continue
    }

    $Stage = "metadata_http"
    try {
        if (-not $MetadataByIdentifier.ContainsKey($Sample.identifier)) {
            $MetadataByIdentifier[$Sample.identifier] = Invoke-RestMethod -Uri ("https://archive.org/metadata/" + $Sample.identifier) -TimeoutSec 30
        }
        $Stage = "license_check"
        $Payload = $MetadataByIdentifier[$Sample.identifier]
        $Item = $Payload.metadata
        $LicenseUrl = [string]$Item.licenseurl
        if ($LicenseUrl -notmatch $AllowedLicensePattern) {
            throw "license_not_eligible"
        }
        $File = $Payload.files | Where-Object { $_.name -ceq $Sample.file_name } | Select-Object -First 1
        if (-not $File) {
            throw "caption_file_not_listed"
        }
        $ExpectedFormat = switch ([IO.Path]::GetExtension($Sample.file_name).ToLowerInvariant()) {
            ".vtt" { "Web Video Text Tracks" }
            ".srt" { "SubRip" }
            default { "unsupported_extension" }
        }
        if ([string]$File.format -notlike "*$ExpectedFormat*") {
            throw "caption_format_mismatch"
        }

        $Stage = "license_metadata_write"
        $CreatorText = (@($Item.creator) -join "; ")
        $CreatorText = [regex]::Replace($CreatorText, '(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[EMAIL REDACTED]')
        $CreatorText = [regex]::Replace($CreatorText, '(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)', '[PHONE REDACTED]')
        $CleanRecord = [ordered]@{
            identifier = $Sample.identifier
            title = $Item.title
            creator = $CreatorText
            language = $Item.language
            licenseurl = $Item.licenseurl
            file_name = $File.name
            file_format = $File.format
            source_page = "https://archive.org/details/$($Sample.identifier)"
            metadata_endpoint = "https://archive.org/metadata/$($Sample.identifier)"
            retrieved_at_utc = [DateTime]::UtcNow.ToString("o")
        }
        [IO.File]::WriteAllText($LicensePath, (($CleanRecord | ConvertTo-Json -Depth 8) + [Environment]::NewLine), $Utf8)

        $Stage = "caption_http_download"
        $EncodedName = [Uri]::EscapeDataString($Sample.file_name)
        $DownloadUrl = "https://archive.org/download/$($Sample.identifier)/$EncodedName"
        $CapturedAt = [DateTime]::UtcNow
        $Timer = [Diagnostics.Stopwatch]::StartNew()
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $RawPath -TimeoutSec 30 -ErrorAction Stop
        $Timer.Stop()
        $RawItem = Get-Item -LiteralPath $RawPath
        $Hash = (Get-FileHash -LiteralPath $RawPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $Receipt = [ordered]@{
            sample_id = $Sample.sample_id
            source_id = $Sample.identifier
            source_file = $Sample.file_name
            captured_at_utc = $CapturedAt.ToString("o")
            method = "PowerShell Invoke-WebRequest public HTTP GET to temporary staging; no login/cookies"
            status_code = 200
            elapsed_ms = $Timer.ElapsedMilliseconds
            bytes = $RawItem.Length
            sha256 = $Hash
            archive_md5 = $File.md5
        }
        $Stage = "capture_receipt_write"
        [IO.File]::WriteAllText($ReceiptPath, (($Receipt | ConvertTo-Json -Depth 4) + [Environment]::NewLine), $Utf8)
        $Receipts += [pscustomobject]@{ sample_id=$Sample.sample_id; status="success"; bytes=$RawItem.Length; elapsed_ms=$Timer.ElapsedMilliseconds; sha256=$Hash }
    } catch {
        $Inner = $_.Exception.InnerException
        $SafeMessage = [string]$_.Exception.Message
        $SafeMessage = [regex]::Replace($SafeMessage, 'https?://\S+', '[URL]')
        $Errors += [pscustomobject]@{
            sample_id=$Sample.sample_id
            stage=$Stage
            error_type=$_.Exception.GetType().Name
            error_message=$SafeMessage
            inner_error_type=if ($Inner) { $Inner.GetType().Name } else { $null }
            inner_error_message=if ($Inner) { [regex]::Replace([string]$Inner.Message, 'https?://\S+', '[URL]') } else { $null }
        }
    }
}

$ErrorPath = Join-Path $ReportDir "collection-errors.json"
$SummaryPath = Join-Path $ReportDir "collection-summary.json"
$Utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($ErrorPath, (([ordered]@{ attempts=$Errors } | ConvertTo-Json -Depth 5) + [Environment]::NewLine), $Utf8)
[IO.File]::WriteAllText($SummaryPath, (([ordered]@{ captured=$Receipts; errors=$Errors } | ConvertTo-Json -Depth 5) + [Environment]::NewLine), $Utf8)
ConvertTo-Json -InputObject @{ captured=$Receipts; errors=$Errors } -Depth 5

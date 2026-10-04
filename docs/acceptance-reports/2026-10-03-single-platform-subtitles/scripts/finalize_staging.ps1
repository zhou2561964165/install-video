$ErrorActionPreference = "Stop"
$ReportDir = (Resolve-Path -LiteralPath "docs/acceptance-reports/2026-10-03-single-platform-subtitles").Path
$Workspace = (Resolve-Path -LiteralPath "E:\install_video").Path
$StageDir = (Resolve-Path -LiteralPath (Join-Path $ReportDir "staging")).Path
$RawDir = (Resolve-Path -LiteralPath (Join-Path $ReportDir "raw-extra")).Path
foreach ($Path in @($StageDir, $RawDir)) {
    if (-not $Path.StartsWith($Workspace, [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside workspace" }
}

$Samples = @(
    @{ sample_id="IA-youtube-6k-kbg3_Drc-en-vtt"; extension="vtt" },
    @{ sample_id="IA-youtube-6k-kbg3_Drc-fr-vtt"; extension="vtt" },
    @{ sample_id="IA-mnn_23214_387-en-srt"; extension="srt" },
    @{ sample_id="IA-mnn_23214_387-en-vtt"; extension="vtt" }
)
$Results = @()
foreach ($Sample in $Samples) {
    $Name = $Sample.sample_id + "." + $Sample.extension
    $StagedFile = Join-Path $StageDir $Name
    $RawFile = Join-Path $RawDir $Name
    $ReceiptFile = Join-Path (Join-Path $ReportDir "licenses") ($Sample.sample_id + ".capture.json")
    $Receipt = Get-Content -Raw -Encoding utf8 -LiteralPath $ReceiptFile | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $StagedFile) -and (Test-Path -LiteralPath $RawFile)) {
        $ExistingHash = (Get-FileHash -LiteralPath $RawFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $ExistingSize = (Get-Item -LiteralPath $RawFile).Length
        if ($ExistingHash -ne $Receipt.sha256 -or $ExistingSize -ne $Receipt.bytes) { throw "Existing raw caption does not match receipt: $($Sample.sample_id)" }
        $Results += [pscustomobject]@{ sample_id=$Sample.sample_id; copied=$true; bytes=$ExistingSize; sha256=$ExistingHash }
        continue
    }
    if (-not (Test-Path -LiteralPath $StagedFile)) { throw "Staged caption missing: $($Sample.sample_id)" }
    if (Test-Path -LiteralPath $RawFile) { throw "Refusing to overwrite raw caption: $($Sample.sample_id)" }
    $StagedHash = (Get-FileHash -LiteralPath $StagedFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($StagedHash -ne $Receipt.sha256) { throw "Staged caption hash mismatch: $($Sample.sample_id)" }

    Copy-Item -LiteralPath $StagedFile -Destination $RawFile
    $RawHash = (Get-FileHash -LiteralPath $RawFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($RawHash -ne $Receipt.sha256) { throw "Raw caption copy hash mismatch: $($Sample.sample_id)" }
    $RawSize = (Get-Item -LiteralPath $RawFile).Length
    if ($RawSize -ne $Receipt.bytes) { throw "Raw caption copy size mismatch: $($Sample.sample_id)" }

    Remove-Item -LiteralPath $StagedFile -Force
    $Results += [pscustomobject]@{ sample_id=$Sample.sample_id; copied=$true; bytes=$RawSize; sha256=$RawHash }
}
ConvertTo-Json -InputObject $Results -Depth 4

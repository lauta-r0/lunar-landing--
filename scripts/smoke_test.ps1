# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
<#
.SYNOPSIS  Smoke test for a running LunaScout API (local or Cloud Run).
.EXAMPLE   powershell -File scripts/smoke_test.ps1 -BaseUrl https://lunascout-api-855190992553.southamerica-east1.run.app
.EXAMPLE   powershell -File scripts/smoke_test.ps1            # defaults to http://localhost:8000
#>
param([string]$BaseUrl = "http://localhost:8000")
$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")
$fail = 0

function Check($name, $ok, $detail) {
    if ($ok) { Write-Host ("[ OK ] {0}: {1}" -f $name, $detail) }
    else { Write-Host ("[FAIL] {0}: {1}" -f $name, $detail); $script:fail++ }
}

function Call($method, $path, $body) {
    $args = @{ Uri = "$BaseUrl$path"; Method = $method; UseBasicParsing = $true; ErrorAction = "Stop" }
    if ($body) { $args.Body = ($body | ConvertTo-Json -Depth 6); $args.ContentType = "application/json" }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { $r = Invoke-WebRequest @args; $status = [int]$r.StatusCode; $content = $r.Content; $headers = $r.Headers }
    catch {
        $resp = $_.Exception.Response
        if (-not $resp) { throw }
        $status = [int]$resp.StatusCode; $headers = $resp.Headers
        # Windows PowerShell 5.1 keeps the body in the response stream; PowerShell 7 in ErrorDetails
        $content = $_.ErrorDetails.Message
        if (-not $content) {
            $stream = $resp.GetResponseStream()
            if ($stream.CanSeek) { [void]$stream.Seek(0, [IO.SeekOrigin]::Begin) }
            $content = (New-Object IO.StreamReader($stream)).ReadToEnd()
        }
    }
    $sw.Stop()
    [pscustomobject]@{ Status = $status; Json = ($content | ConvertFrom-Json); Ms = [int]$sw.ElapsedMilliseconds; Headers = $headers }
}

$h = Call GET "/api/health" $null
Check "health" ($h.Status -eq 200 -and $h.Json.status -eq "ok" -and $h.Json.engine_ready) ("{0} ms, schema {1}" -f $h.Ms, $h.Json.schema_version)

$m = Call GET "/api/meta" $null
Check "meta" ($m.Status -eq 200 -and $m.Json.defaults.limits.min_sun_margin_deg -eq 0) ("{0} ms, {1} curated sites, default margin {2}" -f $m.Ms, $m.Json.curated_sites.Count, $m.Json.defaults.limits.min_sun_margin_deg)

$summit = @{ target = @{ lat = -85.47628; lon = 31.39691 } }
foreach ($pass in "first (cold or MISS)", "repeat (HIT)") {
    $a = Call POST "/api/analyze" $summit
    Check "analyze default $pass" ($a.Status -eq 200) ("{0} ms total, X-Cache {1}, X-Compute-Ms {2}, P={3}, verdict {4}" -f $a.Ms, $a.Headers["X-Cache"], $a.Headers["X-Compute-Ms"], $a.Json.summary.survival_probability, $a.Json.summary.verdict)
}

$athena = @{ target = @{ lat = -84.79059; lon = 29.19567 } }
$a = Call POST "/api/analyze" $athena
Check "analyze Athena actual site" ($a.Status -eq 200) ("{0} ms total, X-Cache {1}, X-Compute-Ms {2}, P={3}, verdict {4}" -f $a.Ms, $a.Headers["X-Cache"], $a.Headers["X-Compute-Ms"], $a.Json.summary.survival_probability, $a.Json.summary.verdict)

$o = Call POST "/api/analyze" @{ target = @{ lat = -80.0; lon = 10.0 } }
Check "out_of_coverage" ($o.Status -eq 400 -and $o.Json.error -eq "out_of_coverage") ("HTTP {0}, error {1}" -f $o.Status, $o.Json.error)

$v = Call POST "/api/analyze" @{ target = @{ lat = 120; lon = 0 } }
Check "422 on bad input" ($v.Status -eq 422) ("HTTP {0}" -f $v.Status)

if ($fail -gt 0) { Write-Host "$fail check(s) failed"; exit 1 }
Write-Host "All checks passed"

[CmdletBinding()]
param(
    [switch] $PreflightOnly,
    [string] $ReviewDirectory = (Join-Path (Get-Location) '.agents\review')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$reviewDirectory = (Resolve-Path -LiteralPath $ReviewDirectory).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $reviewDirectory '..\..')).Path
$stem = 'fable-imf1-4a9e6b8'
$requestPath = Join-Path $reviewDirectory "$stem.request.local.json"
$resultPath = Join-Path $reviewDirectory "$stem.result.local.json"
$stderrPath = Join-Path $reviewDirectory "$stem.stderr.local.txt"
$statusPath = Join-Path $reviewDirectory "$stem.status.local.json"
$claudePath = 'C:\Users\michael\.local\bin\claude.exe'
$baseSha = '6bf41b9a0a04b03e84cfbc5ea16794d7eb5fe4b3'
$reviewedSha = '4a9e6b89233e9549a4b9b05ca14613a2f2115eb6'
$model = 'claude-fable-5'
$effort = 'xhigh'
$timeoutMilliseconds = 1800000
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Write-Status {
    param([hashtable] $Value)
    [System.IO.File]::WriteAllText(
        $statusPath,
        ($Value | ConvertTo-Json -Depth 10),
        $utf8NoBom
    )
}

$request = Get-Content -LiteralPath $requestPath -Raw | ConvertFrom-Json
$prompt = [string]::Join([Environment]::NewLine, [string[]] $request.prompt_lines)
$schemaJson = $request.schema | ConvertTo-Json -Depth 100 -Compress

if (-not (Test-Path -LiteralPath $claudePath -PathType Leaf)) {
    throw "Claude executable is missing: $claudePath"
}
if ([string]::IsNullOrWhiteSpace($prompt) -or
    -not $prompt.Contains($baseSha) -or
    -not $prompt.Contains($reviewedSha)) {
    throw 'The change-review prompt is empty or missing a pinned SHA.'
}

$arguments = [System.Collections.Generic.List[string]]::new()
@(
    '--name', 'fable-review',
    '--model', $model,
    '--effort', $effort,
    '--output-format', 'json',
    '--json-schema', $schemaJson,
    '--allowedTools', 'Read', 'Grep', 'Glob', 'Bash(git *)', 'Bash(uv run *)', 'Bash(node *)',
    '--permission-mode', 'dontAsk',
    '--no-session-persistence',
    '--no-chrome',
    '-p', $prompt
) | ForEach-Object { [void] $arguments.Add([string] $_) }

if ($PreflightOnly) {
    [pscustomobject]@{
        job_name = 'fable-review'
        model = $model
        effort = $effort
        tier = 'standard'
        model_source = 'inline, session-only'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
        result_exists = Test-Path -LiteralPath $resultPath
        stderr_exists = Test-Path -LiteralPath $stderrPath
        status_exists = Test-Path -LiteralPath $statusPath
    } | ConvertTo-Json
    exit 0
}

foreach ($artifact in @($resultPath, $stderrPath, $statusPath)) {
    if (Test-Path -LiteralPath $artifact) {
        throw "Refusing a duplicate launch because an artifact exists: $artifact"
    }
}

$reservation = [System.IO.File]::Open(
    $statusPath,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
)
$reservation.Dispose()

$startedAt = [DateTimeOffset]::UtcNow
Write-Status @{
    state = 'starting'
    started_at = $startedAt.ToString('o')
    job_name = 'fable-review'
    model = $model
    effort = $effort
    tier = 'standard'
    model_source = 'inline, session-only'
    base_sha = $baseSha
    reviewed_sha = $reviewedSha
}

$child = $null
try {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $claudePath
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $arguments) {
        [void] $startInfo.ArgumentList.Add($argument)
    }

    $child = [System.Diagnostics.Process]::new()
    $child.StartInfo = $startInfo
    if (-not $child.Start()) {
        throw 'Claude failed to start.'
    }

    $stdoutTask = $child.StandardOutput.ReadToEndAsync()
    $stderrTask = $child.StandardError.ReadToEndAsync()
    Write-Status @{
        state = 'running'
        started_at = $startedAt.ToString('o')
        child_process_id = $child.Id
        job_name = 'fable-review'
        model = $model
        effort = $effort
        tier = 'standard'
        model_source = 'inline, session-only'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }

    $timedOut = -not $child.WaitForExit($timeoutMilliseconds)
    if ($timedOut) {
        $child.Kill($true)
        $child.WaitForExit()
    }

    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [System.IO.File]::WriteAllText($resultPath, $stdout, $utf8NoBom)
    [System.IO.File]::WriteAllText($stderrPath, $stderr, $utf8NoBom)

    $endedAt = [DateTimeOffset]::UtcNow
    Write-Status @{
        state = if ($timedOut) { 'timed_out' } else { 'completed' }
        started_at = $startedAt.ToString('o')
        ended_at = $endedAt.ToString('o')
        child_process_id = $child.Id
        exit_code = $child.ExitCode
        timed_out = $timedOut
        stdout_bytes = $utf8NoBom.GetByteCount($stdout)
        stderr_bytes = $utf8NoBom.GetByteCount($stderr)
        job_name = 'fable-review'
        model = $model
        effort = $effort
        tier = 'standard'
        model_source = 'inline, session-only'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }

    if ($timedOut) { exit 124 }
    exit $child.ExitCode
}
catch {
    Write-Status @{
        state = 'wrapper_failed'
        started_at = $startedAt.ToString('o')
        ended_at = [DateTimeOffset]::UtcNow.ToString('o')
        child_process_id = if ($null -ne $child -and $child.Id) { $child.Id } else { $null }
        error = $_.Exception.ToString()
        job_name = 'fable-review'
        model = $model
        effort = $effort
        tier = 'standard'
        model_source = 'inline, session-only'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
}

[CmdletBinding()]
param(
    [switch] $PreflightOnly,
    [string] $ReviewDirectory = (Join-Path (Get-Location) '.agents\review')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedReviewDirectory = (Resolve-Path -LiteralPath $ReviewDirectory).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $resolvedReviewDirectory '..\..')).Path
$requestPath = Join-Path $resolvedReviewDirectory 'fable-cl7-bfc84cc.request.local.json'
$resultPath = Join-Path $resolvedReviewDirectory 'fable-cl7-bfc84cc.result.local.json'
$claudeStderrPath = Join-Path $resolvedReviewDirectory 'fable-cl7-bfc84cc.stderr.local.txt'
$statusPath = Join-Path $resolvedReviewDirectory 'fable-cl7-bfc84cc.status.local.json'
$claudePath = 'C:\Users\michael\.local\bin\claude.exe'
$baseSha = '8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57'
$reviewedSha = 'bfc84cc4a664a0c28f92949ae9844e0799319407'
$timeoutMilliseconds = 1200000
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Write-Status {
    param([hashtable] $Value)

    $json = $Value | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($statusPath, $json, $utf8NoBom)
}

$request = Get-Content -Raw -LiteralPath $requestPath | ConvertFrom-Json
$prompt = [string]::Join([Environment]::NewLine, [string[]] $request.prompt_lines)
$schemaJson = $request.schema | ConvertTo-Json -Depth 100 -Compress

if (-not (Test-Path -LiteralPath $claudePath -PathType Leaf)) {
    throw "Claude executable is missing: $claudePath"
}
if ([string]::IsNullOrWhiteSpace($prompt)) {
    throw 'The review prompt is empty.'
}
if (-not $prompt.Contains($baseSha) -or -not $prompt.Contains($reviewedSha)) {
    throw 'The review prompt does not contain both pinned SHAs.'
}
if ($request.schema.properties.verdict.enum -notcontains 'accepted' -or
    $request.schema.properties.verdict.enum -notcontains 'reopened' -or
    $request.schema.properties.verdict.enum -notcontains 'invalid') {
    throw 'The review schema is missing a required verdict.'
}

$claudeArguments = [System.Collections.Generic.List[string]]::new()
@(
    '--name', 'fable-review',
    '--model', 'claude-opus-5',
    '--effort', 'xhigh',
    '--output-format', 'json',
    '--json-schema', $schemaJson,
    '--allowedTools', 'Read', 'Grep', 'Glob', 'Bash(git *)', 'Bash(uv run *)',
    '--permission-mode', 'dontAsk',
    '--no-session-persistence',
    '--no-chrome',
    '-p', $prompt
) | ForEach-Object { [void] $claudeArguments.Add([string] $_) }

if ($PreflightOnly) {
    [pscustomobject]@{
        claude_path = $claudePath
        job_name = 'fable-review'
        model = 'claude-opus-5'
        effort = 'xhigh'
        tier = 'frontier'
        escalation = 'T2'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
        output_format = 'json'
        schema_bytes = $utf8NoBom.GetByteCount($schemaJson)
        prompt_bytes = $utf8NoBom.GetByteCount($prompt)
        result_exists = Test-Path -LiteralPath $resultPath
        stderr_exists = Test-Path -LiteralPath $claudeStderrPath
        status_exists = Test-Path -LiteralPath $statusPath
    } | ConvertTo-Json
    exit 0
}

foreach ($artifactPath in @($resultPath, $claudeStderrPath, $statusPath)) {
    if (Test-Path -LiteralPath $artifactPath) {
        throw "Refusing a duplicate launch because an artifact already exists: $artifactPath"
    }
}

$statusStream = [System.IO.File]::Open(
    $statusPath,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
)
$statusStream.Dispose()

$startedAt = [DateTimeOffset]::UtcNow
Write-Status @{
    state = 'starting'
    started_at = $startedAt.ToString('o')
    job_name = 'fable-review'
    model = 'claude-opus-5'
    effort = 'xhigh'
    tier = 'frontier'
    escalation = 'T2'
    base_sha = $baseSha
    reviewed_sha = $reviewedSha
}

$childProcess = $null
try {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $claudePath
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $claudeArguments) {
        [void] $startInfo.ArgumentList.Add($argument)
    }

    $childProcess = [System.Diagnostics.Process]::new()
    $childProcess.StartInfo = $startInfo
    if (-not $childProcess.Start()) {
        throw 'Claude failed to start.'
    }

    $stdoutTask = $childProcess.StandardOutput.ReadToEndAsync()
    $stderrTask = $childProcess.StandardError.ReadToEndAsync()
    Write-Status @{
        state = 'running'
        started_at = $startedAt.ToString('o')
        child_process_id = $childProcess.Id
        job_name = 'fable-review'
        model = 'claude-opus-5'
        effort = 'xhigh'
        tier = 'frontier'
        escalation = 'T2'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }

    $timedOut = -not $childProcess.WaitForExit($timeoutMilliseconds)
    if ($timedOut) {
        $childProcess.Kill($true)
        $childProcess.WaitForExit()
    }

    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [System.IO.File]::WriteAllText($resultPath, $stdout, $utf8NoBom)
    [System.IO.File]::WriteAllText($claudeStderrPath, $stderr, $utf8NoBom)

    $endedAt = [DateTimeOffset]::UtcNow
    Write-Status @{
        state = if ($timedOut) { 'timed_out' } else { 'completed' }
        started_at = $startedAt.ToString('o')
        ended_at = $endedAt.ToString('o')
        child_process_id = $childProcess.Id
        exit_code = $childProcess.ExitCode
        timed_out = $timedOut
        stdout_bytes = $utf8NoBom.GetByteCount($stdout)
        stderr_bytes = $utf8NoBom.GetByteCount($stderr)
        job_name = 'fable-review'
        model = 'claude-opus-5'
        effort = 'xhigh'
        tier = 'frontier'
        escalation = 'T2'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }

    if ($timedOut) {
        exit 124
    }
    exit $childProcess.ExitCode
}
catch {
    $endedAt = [DateTimeOffset]::UtcNow
    Write-Status @{
        state = 'wrapper_failed'
        started_at = $startedAt.ToString('o')
        ended_at = $endedAt.ToString('o')
        child_process_id = if ($null -ne $childProcess -and $childProcess.Id) { $childProcess.Id } else { $null }
        error = $_.Exception.ToString()
        job_name = 'fable-review'
        model = 'claude-opus-5'
        effort = 'xhigh'
        tier = 'frontier'
        escalation = 'T2'
        base_sha = $baseSha
        reviewed_sha = $reviewedSha
    }
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
}

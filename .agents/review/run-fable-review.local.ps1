[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Stem,
    [Parameter(Mandatory)] [string] $BaseSha,
    [Parameter(Mandatory)] [string] $ReviewedSha,
    [string] $Model = 'claude-opus-5',
    [string] $Effort = 'high',
    [string] $JobName = 'fable-review',
    [ValidateSet('standard', 'frontier')] [string] $Tier = 'standard',
    [string] $Escalated = '',
    [switch] $PreflightOnly,
    [string] $ReviewDirectory = (Join-Path (Get-Location) '.agents\review')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$reviewDirectory = (Resolve-Path -LiteralPath $ReviewDirectory).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $reviewDirectory '..\..')).Path
$requestPath = Join-Path $reviewDirectory "$Stem.request.local.json"
$resultPath = Join-Path $reviewDirectory "$Stem.result.local.json"
$stderrPath = Join-Path $reviewDirectory "$Stem.stderr.local.txt"
$statusPath = Join-Path $reviewDirectory "$Stem.status.local.json"
$claudePath = 'C:\Users\michael\.local\bin\claude.exe'
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
    -not $prompt.Contains($BaseSha) -or
    -not $prompt.Contains($ReviewedSha)) {
    throw 'The review prompt is empty or missing a pinned SHA.'
}

$arguments = [System.Collections.Generic.List[string]]::new()
@(
    '--name', $JobName,
    '--model', $Model,
    '--effort', $Effort,
    '--output-format', 'json',
    '--json-schema', $schemaJson,
    '--allowedTools', 'Read', 'Grep', 'Glob',
    'Bash(git *)', 'Bash(uv run *)', 'Bash(node *)',
    '--permission-mode', 'dontAsk',
    '--no-session-persistence',
    '--no-chrome',
    '-p', $prompt
) | ForEach-Object { [void] $arguments.Add([string] $_) }

$provenance = @{
    job_name = $JobName
    model = $Model
    effort = $Effort
    tier = $Tier
    model_source = 'inline, session-only'
    base_sha = $BaseSha
    reviewed_sha = $ReviewedSha
}
if (-not [string]::IsNullOrWhiteSpace($Escalated)) {
    $provenance.escalated = $Escalated
}
if ($PreflightOnly) {
    [pscustomobject] ($provenance + @{
        result_exists = Test-Path -LiteralPath $resultPath
        stderr_exists = Test-Path -LiteralPath $stderrPath
        status_exists = Test-Path -LiteralPath $statusPath
    }) | ConvertTo-Json
    exit 0
}

foreach ($artifact in @($resultPath, $stderrPath, $statusPath)) {
    if (Test-Path -LiteralPath $artifact) {
        throw "Refusing a duplicate launch because an artifact exists: $artifact"
    }
}

$startedAt = [DateTimeOffset]::UtcNow
Write-Status ($provenance + @{
    state = 'starting'
    started_at = $startedAt.ToString('o')
})
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
    if (-not $child.Start()) { throw 'Claude failed to start.' }
    $stdoutTask = $child.StandardOutput.ReadToEndAsync()
    $stderrTask = $child.StandardError.ReadToEndAsync()
    Write-Status ($provenance + @{
        state = 'running'
        started_at = $startedAt.ToString('o')
        child_process_id = $child.Id
    })

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
    Write-Status ($provenance + @{
        state = if ($timedOut) { 'timed_out' } else { 'completed' }
        started_at = $startedAt.ToString('o')
        ended_at = $endedAt.ToString('o')
        child_process_id = $child.Id
        exit_code = $child.ExitCode
        timed_out = $timedOut
        stdout_bytes = $utf8NoBom.GetByteCount($stdout)
        stderr_bytes = $utf8NoBom.GetByteCount($stderr)
    })
    if ($timedOut) { exit 124 }
    exit $child.ExitCode
}
catch {
    Write-Status ($provenance + @{
        state = 'wrapper_failed'
        started_at = $startedAt.ToString('o')
        ended_at = [DateTimeOffset]::UtcNow.ToString('o')
        child_process_id = if ($null -ne $child -and $child.Id) { $child.Id } else { $null }
        error = $_.Exception.ToString()
    })
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
}

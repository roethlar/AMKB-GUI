[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9-]+$')]
    [string] $Stem,
    [string] $ReviewDirectory = (Join-Path (Get-Location) '.agents\review')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$reviewDirectory = (Resolve-Path -LiteralPath $ReviewDirectory).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $reviewDirectory '..\..')).Path
$stdoutPath = Join-Path $reviewDirectory "$Stem.stdout.local.txt"
$stderrPath = Join-Path $reviewDirectory "$Stem.stderr.local.txt"
$statusPath = Join-Path $reviewDirectory "$Stem.status.local.json"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

foreach ($artifact in @($stdoutPath, $stderrPath, $statusPath)) {
    if (Test-Path -LiteralPath $artifact) {
        throw "Refusing a duplicate gate because an artifact exists: $artifact"
    }
}

[System.IO.File]::WriteAllText($stdoutPath, '', $utf8NoBom)
[System.IO.File]::WriteAllText($stderrPath, '', $utf8NoBom)

$steps = @(
    @{Name='python-tests'; File='uv'; Args=@('run','--frozen','python','-m','unittest','discover','-s','tests','-v')},
    @{Name='python-compile'; File='uv'; Args=@('run','--frozen','python','-m','compileall','-q','am_configurator','packaging','build_tools')},
    @{Name='browser-tests'; File='node'; Args=@('--test','tests/web/*.test.js')},
    @{Name='syntax-lighting-state'; File='node'; Args=@('--check','am_configurator/web/lighting_state.js')},
    @{Name='syntax-lighting-workspace'; File='node'; Args=@('--check','am_configurator/web/lighting_workspace.js')},
    @{Name='syntax-lighting-review'; File='node'; Args=@('--check','am_configurator/web/lighting_review.js')},
    @{Name='syntax-lighting-targets'; File='node'; Args=@('--check','am_configurator/web/lighting_targets.js')},
    @{Name='syntax-lighting-composer'; File='node'; Args=@('--check','am_configurator/web/lighting_composer.js')},
    @{Name='syntax-library-state'; File='node'; Args=@('--check','am_configurator/web/library_state.js')},
    @{Name='syntax-app'; File='node'; Args=@('--check','am_configurator/web/app.js')},
    @{Name='package-build'; File='uv'; Args=@('build')}
)

function Write-Status {
    param([hashtable] $Value)
    [System.IO.File]::WriteAllText(
        $statusPath,
        ($Value | ConvertTo-Json -Depth 20),
        $utf8NoBom
    )
}

function Invoke-Step {
    param([hashtable] $Step)
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Step.File
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $Step.Args) {
        [void] $startInfo.ArgumentList.Add([string] $argument)
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Failed to start gate step $($Step.Name)."
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(300000)) {
        $process.Kill($true)
        $process.WaitForExit()
        throw "Gate step $($Step.Name) exceeded five minutes."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [System.IO.File]::AppendAllText(
        $stdoutPath,
        "--- $($Step.Name) ---`r`n$stdout",
        $utf8NoBom
    )
    [System.IO.File]::AppendAllText(
        $stderrPath,
        "--- $($Step.Name) ---`r`n$stderr",
        $utf8NoBom
    )
    return $process.ExitCode
}

$startedAt = [DateTimeOffset]::UtcNow
$completed = [System.Collections.Generic.List[string]]::new()
Write-Status @{state='running'; started_at=$startedAt.ToString('o'); completed_steps=@()}

try {
    foreach ($step in $steps) {
        Write-Status @{
            state='running'
            started_at=$startedAt.ToString('o')
            current_step=$step.Name
            completed_steps=@($completed)
        }
        $exitCode = Invoke-Step $step
        if ($exitCode -ne 0) {
            Write-Status @{
                state='failed'
                started_at=$startedAt.ToString('o')
                ended_at=[DateTimeOffset]::UtcNow.ToString('o')
                failed_step=$step.Name
                exit_code=$exitCode
                completed_steps=@($completed)
            }
            exit $exitCode
        }
        [void] $completed.Add($step.Name)
    }
    Write-Status @{
        state='completed'
        started_at=$startedAt.ToString('o')
        ended_at=[DateTimeOffset]::UtcNow.ToString('o')
        exit_code=0
        completed_steps=@($completed)
        stdout_bytes=(Get-Item -LiteralPath $stdoutPath).Length
        stderr_bytes=(Get-Item -LiteralPath $stderrPath).Length
    }
    exit 0
}
catch {
    Write-Status @{
        state='wrapper_failed'
        started_at=$startedAt.ToString('o')
        ended_at=[DateTimeOffset]::UtcNow.ToString('o')
        error=$_.Exception.ToString()
        completed_steps=@($completed)
    }
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 1
}

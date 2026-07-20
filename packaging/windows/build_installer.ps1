$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $projectRoot
try {
    $sourceDir = (Resolve-Path "dist\AM Configurator").Path
    $outputDir = (Resolve-Path "dist").Path
    $version = (& uv run --frozen python build_tools/release_info.py version).Trim()
    $artifactName = (& uv run --frozen python build_tools/release_info.py artifact windows).Trim()
    $outputBase = [System.IO.Path]::GetFileNameWithoutExtension($artifactName)
    $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) {
        throw "Inno Setup compiler not found at $iscc"
    }

    & $iscc "/DMyAppVersion=$version" "/DMySourceDir=$sourceDir" "/DMyOutputDir=$outputDir" "/DMyOutputBaseFilename=$outputBase" "packaging\windows\AMConfigurator.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }

    $installer = Join-Path $outputDir $artifactName
    if (-not (Test-Path $installer)) {
        throw "Installer was not created: $installer"
    }

    $smokeDir = Join-Path ([System.IO.Path]::GetTempPath()) "am-configurator-installer-smoke-$PID"
    try {
        & $installer /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- "/DIR=$smokeDir"
        if ($LASTEXITCODE -ne 0) {
            throw "Silent installer failed with exit code $LASTEXITCODE"
        }
        & (Join-Path $smokeDir "AM Configurator.exe") --smoke-test
        if ($LASTEXITCODE -ne 0) {
            throw "Installed application smoke test failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        $uninstaller = Join-Path $smokeDir "unins000.exe"
        if (Test-Path $uninstaller) {
            & $uninstaller /VERYSILENT /SUPPRESSMSGBOXES /NORESTART | Out-Null
        }
        if (Test-Path $smokeDir) {
            Remove-Item -LiteralPath $smokeDir -Recurse -Force
        }
    }

    Write-Output $installer
}
finally {
    Pop-Location
}

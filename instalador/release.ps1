param(
    [string]$Version = (Get-Date -Format "yyyy.MM.dd.HHmm"),
    [switch]$SkipDependencyInstall,
    [switch]$KeepBuildFolders,
    [switch]$SkipQtTrim,
    [switch]$AggressiveQtTrim
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Remove-PathIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )
    if (Test-Path $TargetPath) {
        Remove-Item $TargetPath -Recurse -Force
    }
}

function Remove-FilesIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$FilePaths
    )
    foreach ($filePath in $FilePaths) {
        if (Test-Path $filePath) {
            Remove-Item $filePath -Force
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCmd) {
        throw "No se encontro Python. Crea/activa .venv o instala Python en PATH."
    }
    $pythonExe = $pythonCmd.Source
}

if (-not $SkipDependencyInstall) {
    & $pythonExe -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo instalar/actualizar PyInstaller."
    }
}

if (-not $KeepBuildFolders) {
    $buildDir = Join-Path $repoRoot "build"
    $distDir = Join-Path $repoRoot "dist"
    Remove-PathIfExists -TargetPath $buildDir
    Remove-PathIfExists -TargetPath $distDir
}

$specPath = Join-Path $scriptDir "cambio_precios.spec"
& $pythonExe -m PyInstaller --noconfirm --clean $specPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller fallo durante el build."
}

$appDir = Join-Path $repoRoot "dist\\CambioPrecios"
$appExe = Join-Path $appDir "CambioPrecios.exe"
if (-not (Test-Path $appExe)) {
    throw "No se encontro el ejecutable esperado: $appExe"
}

if (-not $SkipQtTrim) {
    $qtDir = Join-Path $appDir "_internal\\PySide6"
    if (Test-Path $qtDir) {
        $safeQtTrimFiles = @(
            "Qt6Quick.dll",
            "Qt6Qml.dll",
            "Qt6QmlModels.dll",
            "Qt6QmlMeta.dll",
            "Qt6QmlWorkerScript.dll",
            "Qt6Pdf.dll",
            "Qt6VirtualKeyboard.dll"
        ) | ForEach-Object { Join-Path $qtDir $_ }

        Remove-FilesIfExists -FilePaths $safeQtTrimFiles

        $translationsDir = Join-Path $qtDir "translations"
        if (Test-Path $translationsDir) {
            Get-ChildItem $translationsDir -File |
                Where-Object { $_.Name -notin @("qtbase_es.qm", "qtbase_en.qm") } |
                ForEach-Object { Remove-Item $_.FullName -Force }
        }

        if ($AggressiveQtTrim) {
            $aggressiveQtTrimFiles = @(
                "QtOpenGL.pyd",
                "QtOpenGLWidgets.pyd",
                "Qt6OpenGL.dll",
                "Qt6OpenGLWidgets.dll",
                "opengl32sw.dll"
            ) | ForEach-Object { Join-Path $qtDir $_ }
            Remove-FilesIfExists -FilePaths $aggressiveQtTrimFiles
        }
    }
}

Get-ChildItem -Path $appDir -Recurse -File -Filter "*.pdb" | ForEach-Object {
    Remove-Item $_.FullName -Force
}

$isccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\\ISCC.exe"),
    (Join-Path ${env:ProgramFiles} "Inno Setup 6\\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }

$isccExe = $isccCandidates | Select-Object -First 1
if (-not $isccExe) {
    throw "No se encontro ISCC.exe (Inno Setup 6)."
}

$issPath = Join-Path $scriptDir "cambio_precios.iss"
Push-Location $scriptDir
try {
    & $isccExe "/DAppVersion=$Version" $issPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC fallo al compilar el instalador."
    }
} finally {
    Pop-Location
}

$outputDir = Join-Path $scriptDir "output"
$installer = Get-ChildItem -Path $outputDir -Filter "*.exe" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $installer) {
    throw "No se genero el instalador en: $outputDir"
}

$distSizeBytes = (Get-ChildItem -Path $appDir -Recurse -File | Measure-Object Length -Sum).Sum
$distSizeMb = [math]::Round(($distSizeBytes / 1MB), 2)
$installerSizeMb = [math]::Round(($installer.Length / 1MB), 2)

Write-Host ""
Write-Host "Release completado."
Write-Host "Version: $Version"
Write-Host "App: $appExe ($distSizeMb MB)"
Write-Host "Installer: $($installer.FullName) ($installerSizeMb MB)"

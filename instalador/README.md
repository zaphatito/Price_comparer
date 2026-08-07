# Installer and Release

This directory contains the complete packaging workflow:

- `cambio_precios.spec`: optimized PyInstaller build in `onedir` mode.
- `cambio_precios.iss`: Inno Setup script with high compression.
- `release.ps1`: complete PyInstaller and Inno Setup pipeline.

By default, `release.ps1` safely reduces the package size:

- removes Qt DLLs unused by this application (`QML/Quick/PDF`),
- keeps only the base English and Spanish translations,
- removes `.pdb` files.

## Requirements

- Windows x64
- Python 3.13, preferably from the project's `.venv`
- Inno Setup 6 with `ISCC.exe`

## Build a complete release

Run from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalador\release.ps1
```

Specify a version:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalador\release.ps1 -Version 1.0.0
```

Useful flags:

- `-SkipDependencyInstall`: do not install or update PyInstaller.
- `-KeepBuildFolders`: keep `build/` and `dist/` before compilation.
- `-SkipQtTrim`: disable Qt cleanup for QML, Quick, PDF, and translations.
- `-AggressiveQtTrim`: perform additional cleanup, including software OpenGL.

## Output

- Packaged application: `dist\CambioPrecios\`
- Installer: `instalador\output\CambioPrecios-Setup-<version>.exe`

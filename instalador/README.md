# Instalador y Release

Esta carpeta contiene todo el flujo de empaquetado:

- `cambio_precios.spec`: build optimizado de PyInstaller (modo `onedir`).
- `cambio_precios.iss`: script de Inno Setup con compresion alta.
- `release.ps1`: pipeline completo (PyInstaller + Inno Setup).

`release.ps1` aplica por defecto una poda segura para reducir tamano:
- elimina DLLs de Qt no usadas por esta app (`QML/Quick/PDF`),
- conserva solo traducciones base (`es/en`),
- elimina archivos `.pdb`.

## Requisitos

- Windows x64
- Python 3.13 (idealmente el `.venv` del proyecto)
- Inno Setup 6 (con `ISCC.exe`)

## Ejecutar release completo

Desde la raiz del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalador\release.ps1
```

Con version explicita:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalador\release.ps1 -Version 1.0.0
```

Flags utiles:

- `-SkipDependencyInstall`: no instala/actualiza PyInstaller.
- `-KeepBuildFolders`: no borra `build/` y `dist/` antes de compilar.
- `-SkipQtTrim`: desactiva poda de Qt (QML/Quick/PDF + traducciones).
- `-AggressiveQtTrim`: recorte extra (tambien elimina OpenGL por software).

## Salida

- App empaquetada: `dist\CambioPrecios\`
- Instalador final: `instalador\output\CambioPrecios-Setup-<version>.exe`

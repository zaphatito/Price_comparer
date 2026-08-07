# CODEX.md

Guia operativa extendida para mantener coherencia tecnica del proyecto.

## Fuente unica de verdad
- Este archivo (`CODEX.md`) define todas las reglas del proyecto para el agente.
- No usar ni mantener reglas en otros archivos paralelos.

## Mantenimiento de reglas (obligatorio)
- Toda regla nueva, modificada o eliminada debe actualizarse directamente en `CODEX.md` en el mismo cambio.
- Cada actualizacion de reglas debe incluir:
  - Regla nueva o modificada.
  - Motivo tecnico.
  - Impacto esperado.
  - Forma de validarla.

## Arquitectura y rutas
- Mantener rutas centrales en `app/config.py`.
- Persistencia principal:
  - `data/relations.xlsx` como hoja prioritaria de relaciones.
  - `manual_comparisons.json` como fallback historico por firma.
- Vistas por modulo:
  - `views/main_window/main_window.ui`
  - `views/comparison_editor/comparison_editor.ui`

## UI y temas
- Un solo `.ui` por modulo, sin duplicar por tema.
- El tema light/dark debe resolverse con propiedad dinamica:
  - `themeMode="light"`
  - `themeMode="dark"`
- Aplicacion de tema en runtime:
  - `setProperty("themeMode", mode)`
  - repolish del widget raiz.

## Matching y relaciones
- Prioridad de relaciones:
  1. `data/relations.xlsx`
  2. Hoja `Relations` del Excel de salida
  3. `manual_comparisons.json`
- Deduplicar relaciones manuales por combinacion tienda-producto.
- Ignorar placeholders vacios/no validos (ejemplo: `-`, `--`, `N/A`, `none`, `null`, `—`).

## Criterios de cambios
- Evitar cambios grandes fuera del alcance solicitado.
- Mantener compatibilidad con variantes de nombres de proveedor.
- No romper logs o textos existentes sin razon funcional.

## Checklist minimo antes de cerrar un cambio
1. Ejecutar `python -m compileall app main.py`.
2. Si se tocaron rutas o UI, validar que `MainWindow` abre sin error.
3. Si se tocaron reglas, validar que `CODEX.md` quedo actualizado y consistente.

## Mejora continua sugerida
- Registrar mini historial de reglas al final del archivo cuando haya cambios importantes.
- Convertir esta guia en plantilla para futuros modulos nuevos.

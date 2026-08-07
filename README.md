# Price Comparator

Ahora el proyecto incluye una version web compilable con Vite.

- Fuente web: [`web/`](./web/)
- Salida para GitHub Pages: [`docs/`](./docs/)

## Version web

- Entrada HTML: [`web/index.html`](./web/index.html)
- Logica cliente: [`web/app.mjs`](./web/app.mjs) y [`web/core.mjs`](./web/core.mjs)
- Estilos: [`web/styles.css`](./web/styles.css)
- Configuracion de build: [`vite.config.mjs`](./vite.config.mjs)

La app web funciona completamente en el navegador:

- carga PDFs locales
- intenta detectar proveedor
- parsea productos y precios
- compara listas con matching difuso
- importa y exporta hoja de relaciones
- genera el Excel final para descarga

## Publicar en GitHub Pages

1. Sube el repositorio a GitHub.
2. En GitHub entra a `Settings > Pages`.
3. En `Build and deployment`, elige `Deploy from a branch`.
4. Selecciona tu rama y la carpeta `/docs`.
5. Guarda los cambios.

GitHub Pages publicara el contenido de `docs/`.

## Uso local

Instala dependencias:

```powershell
npm install
```

Servidor de desarrollo:

```powershell
npm run dev
```

Build para GitHub Pages:

```powershell
npm run build
```

Preview del build:

```powershell
npm run preview
```

`npm run build` toma `web/` como fuente y regenera `docs/`.

La version web usa dependencias instaladas por npm para:

- leer PDFs
- leer hojas Excel
- generar el archivo `.xlsx`

## App de escritorio

El codigo original en Python/PySide sigue en el repositorio. La version web no reemplaza esos archivos; vive aparte para poder desplegarse en GitHub Pages sin backend.

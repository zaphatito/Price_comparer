# Price Comparator

The project includes a Vite-powered web application and the original Python/PySide desktop application.

- Web source: [`web/`](./web/)
- GitHub Pages build: [`docs/`](./docs/)
- Authoritative product relations: [`data/relations.xlsx`](./data/relations.xlsx)

## Web application

- HTML entry point: [`web/index.html`](./web/index.html)
- Client logic: [`web/app.mjs`](./web/app.mjs) and [`web/core.mjs`](./web/core.mjs)
- Styles: [`web/styles.css`](./web/styles.css)
- Build configuration: [`vite.config.mjs`](./vite.config.mjs)

The web application runs entirely in the browser. It reads local supplier PDFs, detects the supplier, extracts every product and case price, applies the preloaded relations workbook, and downloads the completed Excel comparison. Files are not uploaded to a server.

## Local web development

Install dependencies:

```powershell
npm install
```

Start the development server:

```powershell
npm run dev
```

Build the GitHub Pages site:

```powershell
npm run build
```

Preview the production build:

```powershell
npm run preview
```

`npm run build` uses `web/` as its source and regenerates `docs/`.

## GitHub Pages

The repository is configured to publish the generated `docs/` directory from the default branch.

## Desktop application

The original Python/PySide application remains available in the repository. It uses the same authoritative relations workbook and the same product-completeness rules as the web application.

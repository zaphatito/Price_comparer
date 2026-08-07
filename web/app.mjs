import {
  DEFAULT_OUTPUT_FILE,
  DEFAULT_STORE_NAMES,
  STANDARD_RELATIONS_COLUMNS,
  buildComparisonBundle,
  buildComparisonSignature,
  buildRankingRows,
  cleanText,
  deduplicateManualRows,
  defaultStoreNameForIndex,
  detectProviderNameFromText,
  ensureUniqueNames,
  formatCurrency,
  manualRowsToStandardRows,
  normalizeKey,
  parseListingPdfPages,
  relationsRowsToStandard,
  relationsSheetRowsToManualRows,
  rgbGradientGreenWhite,
} from "./core.mjs";
import pdfWorkerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";

const STORAGE_KEYS = {
  priorityRelations: "price-comparer.priority-relations.v1",
  cachedRuns: "price-comparer.generated-relations.v1",
};

const state = {
  busy: false,
  fileEntries: [],
  priorityStandardRows: [],
  cachedStandardRowsBySignature: {},
  latestResult: null,
};

const elements = {
  pickPdfBtn: document.getElementById("pickPdfBtn"),
  pdfInput: document.getElementById("pdfInput"),
  relationsInput: document.getElementById("relationsInput"),
  uploadRelationsBtn: document.getElementById("uploadRelationsBtn"),
  downloadRelationsBtn: document.getElementById("downloadRelationsBtn"),
  removeSelectedBtn: document.getElementById("removeSelectedBtn"),
  clearListBtn: document.getElementById("clearListBtn"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  generateBtn: document.getElementById("generateBtn"),
  dropzone: document.getElementById("dropzone"),
  listingRows: document.getElementById("listingRows"),
  selectAllRows: document.getElementById("selectAllRows"),
  outputFileInput: document.getElementById("outputFileInput"),
  progressLabel: document.getElementById("progressLabel"),
  progressBar: document.getElementById("progressBar"),
  logOutput: document.getElementById("logOutput"),
  priorityStatus: document.getElementById("priorityStatus"),
  priorityRowsLabel: document.getElementById("priorityRowsLabel"),
  cachedRunsLabel: document.getElementById("cachedRunsLabel"),
  summaryLabel: document.getElementById("summaryLabel"),
  resultsCard: document.getElementById("resultsCard"),
  rankingRows: document.getElementById("rankingRows"),
  comparisonHead: document.getElementById("comparisonHead"),
  comparisonRows: document.getElementById("comparisonRows"),
  resultSearch: document.getElementById("resultSearch"),
};

let libraryPromise = null;

async function ensureLibraries() {
  if (!libraryPromise) {
    libraryPromise = Promise.all([
      import("pdfjs-dist/legacy/build/pdf.mjs"),
      import("xlsx"),
      import("exceljs"),
    ]).then(([pdfjsModule, xlsxModule, excelJsModule]) => {
      pdfjsModule.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      return {
        pdfjsLib: pdfjsModule,
        XLSX: xlsxModule,
        ExcelJS: excelJsModule.default ?? excelJsModule,
      };
    });
  }

  return libraryPromise;
}

function makeFileId(file) {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function logLine(message) {
  const timestamp = new Date().toLocaleTimeString("es-PE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  elements.logOutput.textContent += `[${timestamp}] ${message}\n`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

function setSummary(message) {
  elements.summaryLabel.textContent = message;
}

function setProgress(done, total) {
  const safeTotal = Math.max(total, 1);
  elements.progressBar.max = safeTotal;
  elements.progressBar.value = Math.min(done, safeTotal);
  elements.progressLabel.textContent = `Progreso: ${done}/${total}`;
}

function setBusy(isBusy) {
  state.busy = isBusy;
  const disabled = isBusy;
  [
    elements.pickPdfBtn,
    elements.uploadRelationsBtn,
    elements.downloadRelationsBtn,
    elements.removeSelectedBtn,
    elements.clearListBtn,
    elements.generateBtn,
    elements.outputFileInput,
    elements.resultSearch,
  ].forEach((element) => {
    element.disabled = disabled;
  });
  elements.selectAllRows.disabled = disabled || state.fileEntries.length === 0;
}

function updateStorageStatus() {
  const priorityCount = state.priorityStandardRows.length;
  const cachedCount = Object.keys(state.cachedStandardRowsBySignature).length;

  elements.priorityStatus.textContent =
    priorityCount > 0 ? `${priorityCount} filas disponibles` : "Sin hoja cargada";
  elements.priorityRowsLabel.textContent = `${priorityCount} fila${priorityCount === 1 ? "" : "s"}`;
  elements.cachedRunsLabel.textContent = `${cachedCount} firma${cachedCount === 1 ? "" : "s"}`;
}

function savePriorityRelations() {
  localStorage.setItem(STORAGE_KEYS.priorityRelations, JSON.stringify(state.priorityStandardRows));
  updateStorageStatus();
}

function saveCachedRuns() {
  localStorage.setItem(STORAGE_KEYS.cachedRuns, JSON.stringify(state.cachedStandardRowsBySignature));
  updateStorageStatus();
}

function loadPersistedState() {
  try {
    const priorityRows = JSON.parse(localStorage.getItem(STORAGE_KEYS.priorityRelations) ?? "[]");
    if (Array.isArray(priorityRows)) {
      state.priorityStandardRows = priorityRows;
    }
  } catch {
    state.priorityStandardRows = [];
  }

  try {
    const cachedRuns = JSON.parse(localStorage.getItem(STORAGE_KEYS.cachedRuns) ?? "{}");
    if (cachedRuns && typeof cachedRuns === "object" && !Array.isArray(cachedRuns)) {
      state.cachedStandardRowsBySignature = cachedRuns;
    }
  } catch {
    state.cachedStandardRowsBySignature = {};
  }
}

function renderListings() {
  elements.listingRows.textContent = "";

  if (state.fileEntries.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    row.innerHTML = '<td colspan="4">No hay PDFs agregados todavía.</td>';
    elements.listingRows.append(row);
    elements.selectAllRows.checked = false;
    elements.selectAllRows.disabled = true;
    return;
  }

  state.fileEntries.forEach((entry, index) => {
    const row = document.createElement("tr");
    row.dataset.entryId = entry.id;

    const checkboxCell = document.createElement("td");
    checkboxCell.className = "checkbox-col";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(entry.selected);
    checkbox.addEventListener("change", () => {
      entry.selected = checkbox.checked;
      syncSelectAllState();
    });
    checkboxCell.append(checkbox);

    const nameCell = document.createElement("td");
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = entry.storeName;
    nameInput.placeholder = defaultStoreNameForIndex(index);
    nameInput.addEventListener("input", () => {
      entry.storeName = nameInput.value;
    });
    nameCell.append(nameInput);

    const fileCell = document.createElement("td");
    const fileWrap = document.createElement("div");
    fileWrap.className = "file-name";
    const strong = document.createElement("strong");
    strong.textContent = entry.file.name;
    const info = document.createElement("small");
    info.textContent = `Modificado: ${new Date(entry.file.lastModified).toLocaleDateString("es-PE")}`;
    fileWrap.append(strong, info);
    fileCell.append(fileWrap);

    const sizeCell = document.createElement("td");
    sizeCell.className = "size-cell";
    sizeCell.textContent = formatBytes(entry.file.size);

    row.append(checkboxCell, nameCell, fileCell, sizeCell);
    elements.listingRows.append(row);
  });

  syncSelectAllState();
}

function syncSelectAllState() {
  if (state.fileEntries.length === 0) {
    elements.selectAllRows.checked = false;
    elements.selectAllRows.disabled = true;
    return;
  }

  const selectedCount = state.fileEntries.filter((entry) => entry.selected).length;
  elements.selectAllRows.disabled = state.busy;
  elements.selectAllRows.checked = selectedCount > 0 && selectedCount === state.fileEntries.length;
  elements.selectAllRows.indeterminate =
    selectedCount > 0 && selectedCount < state.fileEntries.length;
}

function ensureOutputFilename(rawName) {
  const text = cleanText(rawName) || DEFAULT_OUTPUT_FILE;
  return text.toLowerCase().endsWith(".xlsx") ? text : `${text}.xlsx`;
}

function addFiles(fileList) {
  const existingIds = new Set(state.fileEntries.map((entry) => entry.id));
  let added = 0;
  let skipped = 0;

  for (const file of fileList) {
    const id = makeFileId(file);
    if (!file.name.toLowerCase().endsWith(".pdf") || existingIds.has(id)) {
      skipped += 1;
      continue;
    }

    const defaultName = defaultStoreNameForIndex(state.fileEntries.length);
    const detectedName = detectProviderNameFromText(file.name);
    state.fileEntries.push({
      id,
      file,
      storeName: detectedName ?? defaultName,
      selected: false,
    });
    existingIds.add(id);
    added += 1;
  }

  renderListings();
  if (added > 0 || skipped > 0) {
    logLine(`PDFs agregados: ${added} | omitidos: ${skipped}`);
  }
}

function removeSelectedRows() {
  const before = state.fileEntries.length;
  state.fileEntries = state.fileEntries.filter((entry) => !entry.selected);
  const removed = before - state.fileEntries.length;
  renderListings();
  if (removed > 0) {
    logLine(`Filas eliminadas: ${removed}`);
  }
}

function clearRows() {
  if (state.fileEntries.length === 0) {
    return;
  }
  state.fileEntries = [];
  renderListings();
  logLine("Lista limpiada.");
}

function collectNamedEntries() {
  const baseNames = state.fileEntries.map((entry, index) => cleanText(entry.storeName) || defaultStoreNameForIndex(index));
  const uniqueNames = ensureUniqueNames(baseNames);
  return state.fileEntries.map((entry, index) => ({
    file: entry.file,
    storeName: uniqueNames[index],
  }));
}

function renderResults() {
  const latest = state.latestResult;
  if (!latest) {
    elements.resultsCard.classList.add("hidden");
    return;
  }

  elements.resultsCard.classList.remove("hidden");
  renderRankingRows(latest.rankingRows);
  renderComparisonTable();
}

function renderRankingRows(rows) {
  elements.rankingRows.textContent = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const storeCell = document.createElement("td");
    storeCell.textContent = row.Store;
    const countCell = document.createElement("td");
    countCell.textContent = String(row["Products with best price"]);
    tr.append(storeCell, countCell);
    elements.rankingRows.append(tr);
  }
}

function gradientCssColor(ratio) {
  return `#${rgbGradientGreenWhite(ratio).slice(2)}`;
}

function renderComparisonTable() {
  const latest = state.latestResult;
  if (!latest) {
    return;
  }

  const filter = normalizeKey(elements.resultSearch.value);
  const storeColumns = latest.bundle.storeColumns;
  const rows = latest.bundle.comparisonRows.filter((row) => {
    if (!filter) {
      return true;
    }
    return normalizeKey(row.Product).includes(filter);
  });

  elements.comparisonHead.textContent = "";
  elements.comparisonRows.textContent = "";

  const headerRow = document.createElement("tr");
  const productHeader = document.createElement("th");
  productHeader.textContent = "Producto";
  headerRow.append(productHeader);
  for (const storeName of storeColumns) {
    const th = document.createElement("th");
    th.textContent = storeName;
    headerRow.append(th);
  }
  elements.comparisonHead.append(headerRow);

  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 1 + storeColumns.length;
    td.textContent = "No hay productos que coincidan con el filtro.";
    td.className = "muted";
    tr.append(td);
    elements.comparisonRows.append(tr);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const productCell = document.createElement("td");
    productCell.textContent = row.Product;
    tr.append(productCell);

    const values = storeColumns
      .map((storeName) => Number(row[storeName]))
      .filter((value) => Number.isFinite(value));
    const min = values.length > 0 ? Math.min(...values) : null;
    const max = values.length > 0 ? Math.max(...values) : null;

    for (const storeName of storeColumns) {
      const td = document.createElement("td");
      td.className = "price-cell";
      const price = Number(row[storeName]);
      if (Number.isFinite(price)) {
        td.textContent = formatCurrency(price);
        const ratio = min === null || max === null || max === min ? 0 : (price - min) / (max - min);
        td.style.background = gradientCssColor(ratio);
        if (Math.abs(price - min) < 1e-9) {
          td.classList.add("best-price");
        }
      } else {
        td.textContent = "—";
        td.classList.add("muted");
      }
      tr.append(td);
    }
    elements.comparisonRows.append(tr);
  }
}

function buildLineText(items) {
  const ordered = [...items].sort((left, right) => left.x - right.x);
  let text = "";
  let previousEnd = null;

  for (const item of ordered) {
    const chunk = cleanText(item.text);
    if (!chunk) {
      continue;
    }
    if (text) {
      const needsGap = previousEnd === null || item.x - previousEnd > 2.5;
      text += needsGap ? " " : "";
    }
    text += chunk;
    previousEnd = item.endX;
  }

  return cleanText(text);
}

function groupTextItemsIntoLines(items) {
  const fragments = items
    .map((item) => {
      const text = cleanText(item.str);
      return {
        text,
        x: item.transform[4],
        y: item.transform[5],
        width: Number(item.width ?? 0),
      };
    })
    .filter((item) => item.text);

  fragments.sort((left, right) => {
    if (Math.abs(right.y - left.y) > 2) {
      return right.y - left.y;
    }
    return left.x - right.x;
  });

  const lines = [];
  for (const fragment of fragments) {
    const targetLine = lines.find((line) => Math.abs(line.y - fragment.y) <= 2.5);
    const normalizedItem = {
      text: fragment.text,
      x: fragment.x,
      endX: fragment.x + fragment.width,
    };
    if (targetLine) {
      targetLine.items.push(normalizedItem);
      continue;
    }
    lines.push({
      y: fragment.y,
      items: [normalizedItem],
    });
  }

  return lines
    .map((line) => {
      const orderedItems = line.items.sort((left, right) => left.x - right.x);
      return {
        items: orderedItems,
        text: buildLineText(orderedItems),
      };
    })
    .filter((line) => line.text);
}

async function extractPdfPages(file) {
  const { pdfjsLib } = await ensureLibraries();
  const data = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({
    data,
    useSystemFonts: true,
  }).promise;

  const pages = [];
  let previewText = "";
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const textContent = await page.getTextContent();
    const lines = groupTextItemsIntoLines(textContent.items);
    const text = lines.map((line) => line.text).join("\n");
    pages.push({ lines, text });
    if (pageNumber <= 2) {
      previewText += `${text}\n`;
    }
  }

  return { pages, previewText };
}

function autosizeWorksheet(worksheet, maxWidth = 45) {
  worksheet.columns?.forEach((column) => {
    let length = 10;
    column.eachCell({ includeEmpty: true }, (cell) => {
      length = Math.max(length, String(cell.value ?? "").length + 2);
    });
    column.width = Math.min(length, maxWidth);
  });
}

function applyComparisonSheetStyles(worksheet, comparisonRows, storeColumns) {
  worksheet.views = [{ state: "frozen", xSplit: 1, ySplit: 1 }];
  worksheet.getRow(1).font = { bold: true };

  const gradientSteps = 11;
  for (let rowIndex = 0; rowIndex < comparisonRows.length; rowIndex += 1) {
    const row = comparisonRows[rowIndex];
    const numericValues = storeColumns
      .map((storeName) => Number(row[storeName]))
      .filter((value) => Number.isFinite(value));
    if (numericValues.length === 0) {
      continue;
    }

    const min = Math.min(...numericValues);
    const max = Math.max(...numericValues);

    storeColumns.forEach((storeName, storeIndex) => {
      const price = Number(row[storeName]);
      if (!Number.isFinite(price)) {
        return;
      }
      const ratio = max === min ? 0 : (price - min) / (max - min);
      const step = Math.round(ratio * (gradientSteps - 1)) / (gradientSteps - 1);
      const cell = worksheet.getCell(rowIndex + 2, storeIndex + 2);
      cell.numFmt = "$#,##0.00";
      cell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: rgbGradientGreenWhite(step) },
      };
      if (Math.abs(price - min) < 1e-9) {
        cell.font = { bold: true, color: { argb: "FF10210A" } };
      }
    });
  }
}

async function downloadWorkbook(buffer, filename) {
  const blob = new Blob(
    [buffer],
    { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  );
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportComparisonWorkbook(comparisonRows, rankingRows, storeColumns, standardRelationsRows, filename) {
  const { ExcelJS } = await ensureLibraries();
  const workbook = new ExcelJS.Workbook();

  const comparisonSheet = workbook.addWorksheet("Comparison");
  comparisonSheet.columns = [
    { header: "Product", key: "Product" },
    ...storeColumns.map((storeName) => ({ header: storeName, key: storeName })),
  ];
  comparisonRows.forEach((row) => {
    const outRow = { Product: row.Product };
    for (const storeName of storeColumns) {
      outRow[storeName] = Number.isFinite(Number(row[storeName])) ? Number(row[storeName]) : null;
    }
    comparisonSheet.addRow(outRow);
  });
  applyComparisonSheetStyles(comparisonSheet, comparisonRows, storeColumns);
  autosizeWorksheet(comparisonSheet);

  const rankingSheet = workbook.addWorksheet("Ranking");
  rankingSheet.columns = [
    { header: "Store", key: "Store" },
    { header: "Products with best price", key: "Products with best price" },
  ];
  rankingRows.forEach((row) => rankingSheet.addRow(row));
  rankingSheet.getRow(1).font = { bold: true };
  autosizeWorksheet(rankingSheet);

  const relationsSheet = workbook.addWorksheet("Relations");
  relationsSheet.columns = STANDARD_RELATIONS_COLUMNS.map((columnName) => ({
    header: columnName,
    key: columnName,
  }));
  standardRelationsRows.forEach((row) => relationsSheet.addRow(row));
  relationsSheet.getRow(1).font = { bold: true };
  autosizeWorksheet(relationsSheet);

  const buffer = await workbook.xlsx.writeBuffer();
  await downloadWorkbook(buffer, filename);
}

async function exportRelationsWorkbook(standardRelationsRows, filename = "relations.xlsx") {
  const { ExcelJS } = await ensureLibraries();
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet("Relations");
  worksheet.columns = STANDARD_RELATIONS_COLUMNS.map((columnName) => ({
    header: columnName,
    key: columnName,
  }));
  standardRelationsRows.forEach((row) => worksheet.addRow(row));
  worksheet.getRow(1).font = { bold: true };
  autosizeWorksheet(worksheet);

  const buffer = await workbook.xlsx.writeBuffer();
  await downloadWorkbook(buffer, filename);
}

function currentStoreColumnsOrDefaults() {
  const namedEntries = collectNamedEntries();
  if (namedEntries.length === 0) {
    return [...DEFAULT_STORE_NAMES];
  }
  return namedEntries.map(({ storeName }) => storeName);
}

function loadPrioritizedManualRows(storeColumns, signature) {
  const merged = [];

  if (state.priorityStandardRows.length > 0) {
    const priorityRows = relationsSheetRowsToManualRows(state.priorityStandardRows, storeColumns);
    merged.push(...priorityRows);
    logLine(`[INFO] Relaciones prioritarias cargadas: ${priorityRows.length} fila(s)`);
  }

  const cachedStandardRows = state.cachedStandardRowsBySignature[signature];
  if (Array.isArray(cachedStandardRows) && cachedStandardRows.length > 0) {
    const cachedRows = relationsSheetRowsToManualRows(cachedStandardRows, storeColumns);
    merged.push(...cachedRows);
    logLine(`[INFO] Relaciones recuperadas del último resultado: ${cachedRows.length} fila(s)`);
  }

  return deduplicateManualRows(merged);
}

async function parseRelationsFile(file) {
  const { XLSX } = await ensureLibraries();
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });
  const sheetName =
    workbook.SheetNames.find((name) => name === "Relations" || name === "Cuadro_Relaciones") ??
    workbook.SheetNames[0];

  if (!sheetName) {
    throw new Error("El archivo no contiene hojas legibles.");
  }

  const sheet = workbook.Sheets[sheetName];
  return XLSX.utils.sheet_to_json(sheet, { defval: "" });
}

async function handleRelationsUpload(file) {
  const storeColumns = currentStoreColumnsOrDefaults();
  const rows = await parseRelationsFile(file);
  const manualRows = relationsSheetRowsToManualRows(rows, storeColumns);
  state.priorityStandardRows = manualRowsToStandardRows(manualRows, storeColumns);
  savePriorityRelations();

  logLine(
    `[INFO] Hoja de relaciones cargada: ${file.name} (${state.priorityStandardRows.length} fila(s))`,
  );
}

async function runComparison({ relationsOnly = false } = {}) {
  if (state.busy) {
    return;
  }
  if (state.fileEntries.length === 0) {
    window.alert("Agrega al menos un PDF antes de continuar.");
    return;
  }

  const namedEntries = collectNamedEntries();
  const signature = buildComparisonSignature(namedEntries);
  const storeColumns = namedEntries.map(({ storeName }) => storeName);

  setBusy(true);
  setProgress(0, namedEntries.length);
  setSummary("Procesando PDFs...");
  logLine("------------------------------------------------");
  logLine(`[INFO] Iniciando comparación de ${namedEntries.length} listado(s).`);

  try {
    const manualRows = loadPrioritizedManualRows(storeColumns, signature);
    if (manualRows.length > 0) {
      logLine(`[INFO] Overrides manuales aplicados: ${manualRows.length} fila(s)`);
    }

    const framesByStore = {};
    for (let index = 0; index < namedEntries.length; index += 1) {
      const { file, storeName } = namedEntries[index];
      try {
        const { pages, previewText } = await extractPdfPages(file);
        const detectedProvider =
          detectProviderNameFromText(file.name) ?? detectProviderNameFromText(previewText);
        const { items, sourceFormat } = parseListingPdfPages(pages);
        framesByStore[storeName] = items;
        logLine(
          `[OK] ${storeName}: ${file.name} (${items.length} productos, formato: ${sourceFormat}${
            detectedProvider ? `, detectado: ${detectedProvider}` : ""
          })`,
        );
      } catch (error) {
        logLine(`[ERROR] ${file.name}: ${error.message}`);
      } finally {
        setProgress(index + 1, namedEntries.length);
      }
    }

    if (Object.keys(framesByStore).length === 0) {
      throw new Error("Ningún PDF válido pudo ser procesado.");
    }

    logLine("[INFO] Emparejando productos con similitud difusa...");
    const bundle = buildComparisonBundle(framesByStore, manualRows);
    const rankingRows = buildRankingRows(bundle.comparisonRows, bundle.storeColumns);
    const standardRelationsRows = relationsRowsToStandard(bundle.relationsRows, bundle.storeColumns);

    state.latestResult = {
      bundle,
      rankingRows,
      standardRelationsRows,
      signature,
    };

    state.cachedStandardRowsBySignature[signature] = standardRelationsRows;
    saveCachedRuns();
    renderResults();

    if (relationsOnly) {
      await exportRelationsWorkbook(standardRelationsRows, "relations.xlsx");
      logLine("[OK] Hoja de relaciones exportada.");
      setSummary(`Relaciones listas: ${standardRelationsRows.length} fila(s)`);
    } else {
      const filename = ensureOutputFilename(elements.outputFileInput.value);
      await exportComparisonWorkbook(
        bundle.comparisonRows,
        rankingRows,
        bundle.storeColumns,
        standardRelationsRows,
        filename,
      );
      logLine(`[OK] Excel generado: ${filename}`);
      setSummary(`Tiendas: ${bundle.storeColumns.length} | Productos: ${bundle.comparisonRows.length}`);
    }
  } catch (error) {
    logLine(`[ERROR] ${error.message}`);
    window.alert(error.message);
    setSummary("Proceso con errores");
  } finally {
    setBusy(false);
  }
}

async function handleDownloadRelations() {
  if (state.fileEntries.length === 0) {
    await exportRelationsWorkbook(state.priorityStandardRows, "relations.xlsx");
    logLine("[OK] Hoja de relaciones exportada.");
    return;
  }
  await runComparison({ relationsOnly: true });
}

function bindEvents() {
  elements.pickPdfBtn.addEventListener("click", () => elements.pdfInput.click());
  elements.dropzone.addEventListener("click", () => elements.pdfInput.click());
  elements.pdfInput.addEventListener("change", (event) => {
    addFiles([...event.target.files]);
    event.target.value = "";
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropzone.classList.add("is-dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropzone.classList.remove("is-dragover");
    });
  });
  elements.dropzone.addEventListener("drop", (event) => {
    addFiles([...event.dataTransfer.files]);
  });

  elements.selectAllRows.addEventListener("change", () => {
    state.fileEntries.forEach((entry) => {
      entry.selected = elements.selectAllRows.checked;
    });
    renderListings();
  });
  elements.removeSelectedBtn.addEventListener("click", removeSelectedRows);
  elements.clearListBtn.addEventListener("click", clearRows);
  elements.clearLogBtn.addEventListener("click", () => {
    elements.logOutput.textContent = "";
  });

  elements.uploadRelationsBtn.addEventListener("click", () => elements.relationsInput.click());
  elements.relationsInput.addEventListener("change", async (event) => {
    const [file] = [...event.target.files];
    event.target.value = "";
    if (!file) {
      return;
    }
    try {
      await handleRelationsUpload(file);
    } catch (error) {
      logLine(`[ERROR] ${error.message}`);
      window.alert(error.message);
    }
  });

  elements.downloadRelationsBtn.addEventListener("click", () => {
    void handleDownloadRelations();
  });
  elements.generateBtn.addEventListener("click", () => {
    void runComparison();
  });
  elements.resultSearch.addEventListener("input", renderComparisonTable);
}

async function init() {
  loadPersistedState();
  updateStorageStatus();
  renderListings();
  setBusy(false);
  setProgress(0, 0);
  setSummary("Sin resultados");
  bindEvents();
  elements.outputFileInput.value = DEFAULT_OUTPUT_FILE;
  logLine("[INFO] Aplicación lista. Los archivos se procesan localmente en el navegador.");

  ensureLibraries()
    .then(() => {
      logLine("[INFO] Librerías cliente preparadas.");
    })
    .catch((error) => {
      logLine(`[ERROR] No se pudieron cargar las librerías del navegador: ${error.message}`);
    });
}

void init();

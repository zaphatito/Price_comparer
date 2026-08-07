const FUZZY_MATCH_THRESHOLD = 0.5;
const FUZZY_MATCH_AMBIGUITY_MARGIN = 0.06;

const DEFAULT_STORE_NAMES = ["sysco", "us food", "kohls"];
const DEFAULT_OUTPUT_FILE = "price_comparison.xlsx";

const TOKEN_NORMALIZATION_MAP = {
  aceite: "oil",
  aguacate: "avocado",
  aluminio: "aluminum",
  amarilla: "yellow",
  amarillo: "yellow",
  arroz: "rice",
  azucar: "sugar",
  blanca: "white",
  blanco: "white",
  blanqueador: "bleach",
  bolsa: "bag",
  camaron: "shrimp",
  camarones: "shrimp",
  carne: "meat",
  cebolla: "onion",
  cerdo: "pork",
  champinon: "mushroom",
  chile: "pepper",
  costilla: "rib",
  crudo: "raw",
  cruda: "raw",
  desinfectante: "disinfectant",
  enlatada: "canned",
  enlatado: "canned",
  entera: "whole",
  entero: "whole",
  espuma: "foam",
  fresca: "fresh",
  fresco: "fresh",
  frijol: "bean",
  hueso: "bone",
  huevo: "egg",
  jalapeno: "jalapeno",
  leche: "milk",
  limon: "lime",
  manteca: "shortening",
  margarina: "margarine",
  mezcla: "mix",
  molida: "ground",
  muslo: "thigh",
  papel: "paper",
  pechuga: "breast",
  pimiento: "pepper",
  pollo: "chicken",
  queso: "cheese",
  recipiente: "container",
  res: "beef",
  rebanada: "sliced",
  rebanado: "sliced",
  roja: "red",
  rojo: "red",
  sal: "salt",
  salmuera: "canned",
  servilleta: "napkin",
  surtidos: "mixed",
  tallos: "stem",
  tapa: "lid",
  tilapia: "tilapia",
  tomate: "tomato",
  tomatillo: "tomatillo",
  vegetales: "vegetable",
  verde: "green",
  vaso: "cup",
  vaca: "beef",
  alum: "aluminum",
  brst: "breast",
  brgr: "burger",
  bnsls: "boneless",
  bnsl: "boneless",
  chix: "chicken",
  cmpt: "compartment",
  cmp: "compartment",
  comp: "compartment",
  cont: "container",
  ctn: "carton",
  dsp: "dispenser",
  frsh: "fresh",
  frzn: "frozen",
  grnd: "ground",
  nugg: "nugget",
  pk: "pack",
  oz: "ounce",
  lbs: "pound",
  lb: "pound",
  pty: "patty",
  stk: "steak",
  wht: "white",
  ylw: "yellow",
  xmlt: "melting",
  ez: "easy",
};

const STATE_TOKEN_MAP = {
  fresh: "fresh",
  frozen: "frozen",
  canned: "canned",
  iqf: "frozen",
};

const CONFLICTING_STATE_PAIRS = new Set(["canned|fresh", "fresh|frozen"]);

const GENERIC_TOKENS = new Set([
  "a",
  "an",
  "and",
  "at",
  "by",
  "for",
  "from",
  "in",
  "of",
  "on",
  "or",
  "the",
  "to",
  "with",
  "without",
  "al",
  "con",
  "de",
  "del",
  "el",
  "en",
  "la",
  "las",
  "los",
  "o",
  "para",
  "por",
  "sin",
  "y",
  "anaquel",
  "case",
  "caja",
  "estables",
  "estable",
  "grade",
  "liquida",
  "liquido",
  "pack",
  "ref",
  "seleccion",
  "selecto",
  "suelto",
  "tipo",
  "unidad",
  "unidades",
  "units",
  "fresh",
  "frozen",
  "raw",
  "whole",
  "mixed",
  "special",
]);

const CATEGORY_KEYWORDS = {
  beef: new Set(["beef", "ribeye", "burger", "patty", "steak", "chub", "ground", "namp"]),
  pork: new Set(["pork", "ham", "bacon", "rib", "shoulder", "butt"]),
  chicken: new Set(["chicken", "breast", "thigh", "nugget", "wing"]),
  seafood: new Set(["shrimp", "tilapia", "fish", "salmon", "tuna"]),
  produce: new Set([
    "avocado",
    "onion",
    "tomato",
    "tomatillo",
    "jalapeno",
    "cilantro",
    "pepper",
    "lime",
    "mushroom",
    "vegetable",
    "bean",
    "rice",
  ]),
  dairy: new Set(["cheese", "milk", "margarine", "butter", "cream"]),
  paper: new Set(["paper", "napkin", "bag", "towel"]),
  container: new Set(["container", "compartment", "foam", "aluminum", "cup", "lid", "tray"]),
  cleaning: new Set(["bleach", "disinfectant", "soap", "detergent"]),
};

const CATEGORY_BY_TOKEN = new Map();
for (const [category, tokens] of Object.entries(CATEGORY_KEYWORDS)) {
  for (const token of tokens) {
    if (!CATEGORY_BY_TOKEN.has(token)) {
      CATEGORY_BY_TOKEN.set(token, new Set());
    }
    CATEGORY_BY_TOKEN.get(token).add(category);
  }
}

const productFeaturesCache = new Map();

function cleanText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).replace(/\n/g, " ").replace(/\s+/g, " ").trim();
}

function normalizeKey(text) {
  return cleanText(text)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function ensureUniqueNames(names) {
  const seen = new Map();
  return names.map((rawName) => {
    const base = cleanText(rawName) || "listing";
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return count === 1 ? base : `${base}_${count}`;
  });
}

function defaultStoreNameForIndex(index) {
  return DEFAULT_STORE_NAMES[index] ?? `listing_${index + 1}`;
}

function buildComparisonSignature(namedEntries) {
  const parts = namedEntries.map(({ storeName, file }) => {
    const id = `${file.name}|${file.size}|${file.lastModified}`;
    return `${cleanText(storeName).toUpperCase()}|${id}`;
  });
  parts.sort();
  return parts.join("\n");
}

function detectProviderNameFromText(rawText) {
  const text = normalizeKey(rawText);
  if (!text) {
    return null;
  }
  if (text.includes("kohl")) {
    return "KOHL";
  }
  if (text.includes("us foods") || text.includes("us food") || text.includes("usfoods")) {
    return "US FOOD";
  }
  if (text.includes("sysco")) {
    return "SYSCO";
  }
  return null;
}

function headerRowScore(text) {
  const joined = normalizeKey(text);
  if (!joined) {
    return -999;
  }

  let score = 0;
  if (["product", "description", "item", "name", "line"].some((word) => joined.includes(word))) {
    score += 4;
  }
  if (joined.includes("price") || joined.includes("cost")) {
    score += 4;
  }
  if (["qty", "pack", "size", "brand"].some((word) => joined.includes(word))) {
    score += 1;
  }
  if (/\d/.test(joined)) {
    score -= 1;
  }
  return score;
}

function findHeaderLineIndex(lines) {
  let bestIndex = -1;
  let bestScore = -999;
  for (let index = 0; index < Math.min(lines.length, 8); index += 1) {
    const score = headerRowScore(lines[index].text);
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  }
  return bestScore >= 4 ? bestIndex : null;
}

function detectHeaderAnchors(line) {
  let productX = null;
  let priceX = null;

  for (const item of line.items) {
    const normalized = normalizeKey(item.text);
    if (!normalized) {
      continue;
    }
    if (
      ["product", "description", "item", "name", "line"].some((word) => normalized.includes(word))
      && (productX === null || item.x < productX)
    ) {
      productX = item.x;
    }
    if (
      ["price", "cost", "unit"].some((word) => normalized.includes(word))
      && (priceX === null || item.x < priceX)
    ) {
      priceX = item.x;
    }
  }

  if (productX === null || priceX === null || productX >= priceX) {
    return null;
  }

  return { productX, priceX };
}

function extractTrailingPrice(text) {
  const match = cleanText(text).match(
    /\$?(\d{1,5}(?:,\d{3})*(?:\.\d+)?)\s*\/?\s*(?:CS|EA|LB|CT|PK|BX|BG|RL|DZ)\s*$/i,
  );
  if (!match) {
    return Number.NaN;
  }
  return Number.parseFloat(match[1].replaceAll(",", ""));
}

function parseSingleColumnLine(lineText) {
  const text = cleanText(lineText);
  if (!text || !/^\d{4,}\b/.test(text)) {
    return null;
  }

  const normalized = normalizeKey(text);
  if (normalized.includes("item pack pack size")) {
    return null;
  }

  const priceMatch = text.match(
    /\$?(\d{1,5}(?:,\d{3})*(?:\.\d+)?)\s*(?:CS|EA|LB|CT|PK|BX|BG|RL|DZ)\s*$/i,
  );
  if (!priceMatch) {
    return null;
  }

  const price = Number.parseFloat(priceMatch[1].replaceAll(",", ""));
  if (Number.isNaN(price)) {
    return null;
  }

  const leftText = text.slice(0, priceMatch.index).replace(/[_-]+\s*$/, "").trim();
  const tokens = leftText.split(/\s+/);
  if (tokens.length < 4) {
    return null;
  }

  const tailTokens = tokens.slice(3);
  const productTokens = tailTokens.length >= 2 ? tailTokens.slice(1) : tailTokens;
  const productName = cleanText(productTokens.join(" "));
  if (!productName) {
    return null;
  }

  return { product_name: productName, price };
}

function groupParsedRecords(records) {
  const valid = [];
  for (const record of records) {
    const productName = cleanText(record.product_name);
    const hasPrice = record.price !== null && record.price !== undefined && record.price !== "";
    const price = hasPrice ? Number(record.price) : null;
    const productKey = normalizeKey(productName);
    if (
      !productName
      || !productKey
      || (price !== null && (!Number.isFinite(price) || price <= 0))
    ) {
      continue;
    }
    valid.push({ product_key: productKey, product_name: productName, price });
  }

  valid.sort((left, right) => {
    const keyCmp = left.product_key.localeCompare(right.product_key);
    if (keyCmp !== 0) {
      return keyCmp;
    }
    if (left.price !== right.price) {
      if (left.price === null) {
        return 1;
      }
      if (right.price === null) {
        return -1;
      }
      return left.price - right.price;
    }
    return left.product_name.localeCompare(right.product_name);
  });

  const grouped = new Map();
  for (const item of valid) {
    const current = grouped.get(item.product_key);
    if (
      !current
      || (current.price === null && item.price !== null)
      || (
        item.price !== null
        && current.price !== null
        && (item.price < current.price || (item.price === current.price && item.product_name < current.product_name))
      )
    ) {
      grouped.set(item.product_key, item);
    }
  }
  return [...grouped.values()];
}

function isProductHeader(text) {
  const normalized = normalizeKey(text);
  return (
    normalized.includes("product description")
    || normalized.includes("product name")
    || normalized === "description"
    || normalized === "item description"
  );
}

function isPriceHeader(text) {
  const normalized = normalizeKey(text);
  return normalized.includes("price") || normalized.includes("cost");
}

function findTabularHeader(lines, pageHeight) {
  const searchLimit = Number.isFinite(pageHeight) ? pageHeight * 0.48 : Number.POSITIVE_INFINITY;
  const productCandidates = [];
  const priceCandidates = [];

  lines.forEach((line, lineIndex) => {
    if (line.y > searchLimit) {
      return;
    }
    line.items.forEach((item) => {
      if (isProductHeader(item.text)) {
        productCandidates.push({ ...item, y: line.y, lineIndex });
      }
      if (isPriceHeader(item.text)) {
        priceCandidates.push({ ...item, y: line.y, lineIndex });
      }
    });
  });

  let bestPair = null;
  for (const product of productCandidates) {
    for (const price of priceCandidates) {
      const verticalDistance = Math.abs(product.y - price.y);
      if (product.x >= price.x || verticalDistance > 32) {
        continue;
      }
      const score = verticalDistance + Math.abs(product.lineIndex - price.lineIndex) * 3;
      if (!bestPair || score < bestPair.score) {
        bestPair = { product, price, score };
      }
    }
  }

  if (!bestPair) {
    return null;
  }

  const centerY = (bestPair.product.y + bestPair.price.y) / 2;
  const headerItems = lines
    .filter((line) => Math.abs(line.y - centerY) <= 8)
    .flatMap((line) => line.items.map((item) => ({ ...item, y: line.y })));
  const previous = headerItems
    .filter((item) => item.endX < bestPair.product.x)
    .sort((left, right) => right.endX - left.endX)[0];
  const next = headerItems
    .filter((item) => item.x > bestPair.product.endX + 8)
    .sort((left, right) => left.x - right.x)[0];
  const afterPrice = headerItems
    .filter((item) => item.x > bestPair.price.endX + 8)
    .sort((left, right) => left.x - right.x)[0];

  const packHeader = headerItems
    .filter((item) => normalizeKey(item.text).includes("pack"))
    .sort((left, right) => left.x - right.x)[0];
  const productIdHeader =
    headerItems.find((item) => normalizeKey(item.text).includes("upc"))
    ?? headerItems.find((item) => normalizeKey(item.text) === "item")
    ?? headerItems.find((item) => item.text.includes("#") && normalizeKey(item.text).includes("product"));

  const columnBounds = (headerItem) => {
    if (!headerItem) {
      return { start: null, end: null };
    }
    const columnPrevious = headerItems
      .filter((item) => item.endX < headerItem.x)
      .sort((left, right) => right.endX - left.endX)[0];
    const columnNext = headerItems
      .filter((item) => item.x > headerItem.endX)
      .sort((left, right) => left.x - right.x)[0];
    return {
      start: columnPrevious
        ? (columnPrevious.endX + headerItem.x) / 2
        : Math.max(0, headerItem.x - 40),
      end: columnNext
        ? (headerItem.endX + columnNext.x) / 2
        : Number.POSITIVE_INFINITY,
    };
  };

  const packBounds = columnBounds(packHeader);
  const productIdBounds = columnBounds(productIdHeader);

  return {
    headerBottom: Math.max(...headerItems.map((item) => item.y)) + 4,
    productStart: previous ? previous.endX + 4 : Math.max(0, bestPair.product.x - 40),
    productEnd: next ? (bestPair.product.endX + next.x) / 2 : bestPair.price.x - 24,
    priceStart: bestPair.price.x - 32,
    priceEnd: afterPrice ? afterPrice.x - 6 : Number.POSITIVE_INFINITY,
    packStart: packBounds.start,
    packEnd: packBounds.end,
    productIdStart: productIdBounds.start,
    productIdEnd: productIdBounds.end,
  };
}

function parsePriceCandidate(text) {
  const cleaned = cleanText(text).replaceAll(",", "");
  const unitMatch = cleaned.match(
    /\$?\s*(-?\d{1,5}(?:\.\d+)?)\s*\/?\s*(CS|EA|LB|CT|PK|BX|BG|RL|DZ)\b/i,
  );
  if (unitMatch) {
    return { price: Number.parseFloat(unitMatch[1]), unit: unitMatch[2].toUpperCase() };
  }

  const currencyMatch = cleaned.match(/\$\s*(-?\d{1,5}(?:\.\d+)?)/);
  if (currencyMatch) {
    return { price: Number.parseFloat(currencyMatch[1]), unit: "" };
  }

  const plainMatch = cleaned.match(/^\s*(-?\d{1,5}(?:\.\d+)?)\s*$/);
  if (plainMatch) {
    return { price: Number.parseFloat(plainMatch[1]), unit: "" };
  }
  return null;
}

function median(values) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function preferCasePrices(records) {
  const grouped = new Map();
  for (const record of records) {
    const key = cleanText(record.product_id)
      || `${normalizeKey(record.product_name)}|${normalizeKey(record.pack_size)}`;
    const current = grouped.get(key);
    const isCase = record.price_unit === "CS";
    const currentIsCase = current?.price_unit === "CS";
    if (!current || (isCase && !currentIsCase)) {
      grouped.set(key, record);
    }
  }
  return [...grouped.values()];
}

function disambiguateDuplicateProductNames(records) {
  const grouped = new Map();
  for (const record of records) {
    const key = normalizeKey(record.product_name);
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key).push(record);
  }

  const output = [];
  for (const group of grouped.values()) {
    if (group.length === 1) {
      output.push(group[0]);
      continue;
    }

    const qualifierCounts = new Map();
    for (const record of group) {
      const packQualifier = cleanText(record.pack_size).replace(/^1\s+(?=\S)/, "");
      const qualifier = packQualifier || `Item ${cleanText(record.product_id)}`;
      qualifierCounts.set(qualifier, (qualifierCounts.get(qualifier) ?? 0) + 1);
    }

    for (const record of group) {
      const packQualifier = cleanText(record.pack_size).replace(/^1\s+(?=\S)/, "");
      let qualifier = packQualifier || `Item ${cleanText(record.product_id)}`;
      if ((qualifierCounts.get(qualifier) ?? 0) > 1 && cleanText(record.product_id)) {
        qualifier = `${qualifier} · ${cleanText(record.product_id)}`;
      }
      output.push({
        ...record,
        product_name: `${cleanText(record.product_name)} [${qualifier}]`,
      });
    }
  }
  return output;
}

function columnTextNearRow(lines, rowY, rowWindow, start, end) {
  if (start === null || end === null) {
    return "";
  }
  return cleanText(
    lines
      .filter((line) => Math.abs(line.y - rowY) <= rowWindow)
      .flatMap((line) =>
        line.items
          .filter((item) => item.x >= start && item.x < end)
          .map((item) => ({ text: item.text, x: item.x, y: line.y })),
      )
      .sort((left, right) => left.y - right.y || left.x - right.x)
      .map((item) => item.text)
      .join(" "),
  );
}

function parseTabularCandidateRows(pages) {
  const records = [];

  for (const page of pages) {
    const lines = page.lines ?? [];
    const header = findTabularHeader(lines, page.height);
    if (!header) {
      continue;
    }

    const dataLines = lines.filter((line) => line.y > header.headerBottom);
    const priceRows = [];
    for (const line of dataLines) {
      const priceText = line.items
        .filter((item) => item.x >= header.priceStart && item.x < header.priceEnd)
        .map((item) => item.text)
        .join(" ");
      const parsedPrice = parsePriceCandidate(priceText);
      if (parsedPrice && Number.isFinite(parsedPrice.price) && parsedPrice.price > 0) {
        priceRows.push({ ...parsedPrice, y: line.y });
      } else if (normalizeKey(priceText).includes("no price")) {
        priceRows.push({ price: null, unit: "", y: line.y });
      }
    }

    const rowGaps = [];
    for (let index = 1; index < priceRows.length; index += 1) {
      const gap = priceRows[index].y - priceRows[index - 1].y;
      if (gap > 4) {
        rowGaps.push(gap);
      }
    }
    const typicalGap = median(rowGaps.filter((gap) => gap >= median(rowGaps)));
    const rowWindow = Math.min(24, Math.max(6, typicalGap * 0.45 || 12));

    for (const priceRow of priceRows) {
      const productParts = dataLines
        .filter((line) => Math.abs(line.y - priceRow.y) <= rowWindow)
        .flatMap((line) =>
          line.items
            .filter((item) => item.x >= header.productStart && item.x < header.productEnd)
            .map((item) => ({ text: item.text, x: item.x, y: line.y })),
        )
        .sort((left, right) => left.y - right.y || left.x - right.x)
        .map((item) => item.text);
      const productName = cleanText(productParts.join(" "));
      if (!productName) {
        continue;
      }
      const packSize = columnTextNearRow(
        dataLines,
        priceRow.y,
        rowWindow,
        header.packStart,
        header.packEnd,
      );
      const productIdText = columnTextNearRow(
        dataLines,
        priceRow.y,
        rowWindow,
        header.productIdStart,
        header.productIdEnd,
      );
      const productId = productIdText.match(/\b\d{5,8}\b/)?.[0] ?? "";
      records.push({
        product_name: productName,
        price: priceRow.price,
        price_unit: priceRow.unit,
        pack_size: packSize,
        product_id: productId,
      });
    }
  }

  return groupParsedRecords(disambiguateDuplicateProductNames(preferCasePrices(records)));
}

function parseSingleColumnCandidateRows(pages) {
  const records = [];

  for (const page of pages) {
    for (const line of page.lines ?? []) {
      const parsed = parseSingleColumnLine(line.text);
      if (parsed) {
        records.push(parsed);
      }
    }
    if (records.length > 0) {
      continue;
    }
    for (const rawLine of (page.text ?? "").split(/\r?\n/)) {
      const parsed = parseSingleColumnLine(rawLine);
      if (parsed) {
        records.push(parsed);
      }
    }
  }

  return groupParsedRecords(records);
}

function parseListingPdfPages(pages) {
  let parsed = parseTabularCandidateRows(pages);
  let sourceFormat = "tabular";
  if (parsed.length === 0) {
    parsed = parseSingleColumnCandidateRows(pages);
    sourceFormat = "single-column";
  }
  if (parsed.length === 0) {
    throw new Error("No valid products were found in this PDF format.");
  }
  return { items: parsed, sourceFormat };
}

function singularizeToken(token) {
  if (token.length > 5 && token.endsWith("es")) {
    return token.slice(0, -2);
  }
  if (token.length > 4 && token.endsWith("s")) {
    return token.slice(0, -1);
  }
  return token;
}

function productFeatures(productName) {
  const cacheKey = productName ?? "";
  if (productFeaturesCache.has(cacheKey)) {
    return productFeaturesCache.get(cacheKey);
  }

  const normalized = normalizeKey(productName);
  const tokens = [];
  const categories = new Set();
  const states = new Set();

  for (const rawToken of normalized.split(" ")) {
    if (!rawToken) {
      continue;
    }
    const mapped = TOKEN_NORMALIZATION_MAP[rawToken] ?? rawToken;
    for (const mappedToken of mapped.split(" ")) {
      const token = singularizeToken(mappedToken);
      const state = STATE_TOKEN_MAP[token];
      if (state) {
        states.add(state);
      }
      if (GENERIC_TOKENS.has(token)) {
        continue;
      }
      tokens.push(token);
      const itemCategories = CATEGORY_BY_TOKEN.get(token);
      if (itemCategories) {
        for (const category of itemCategories) {
          categories.add(category);
        }
      }
    }
  }

  const features = {
    canonicalText: tokens.join(" "),
    tokenSet: new Set(tokens),
    strongTokens: new Set(tokens.filter((token) => token.length >= 4 && !/\d/.test(token))),
    numberTokens: new Set(tokens.filter((token) => /\d/.test(token))),
    categories,
    states,
  };
  productFeaturesCache.set(cacheKey, features);
  return features;
}

function setIntersection(left, right) {
  const out = new Set();
  for (const value of left) {
    if (right.has(value)) {
      out.add(value);
    }
  }
  return out;
}

function setUnionSize(left, right) {
  const union = new Set(left);
  for (const value of right) {
    union.add(value);
  }
  return union.size;
}

function hasStateConflict(statesA, statesB) {
  if (statesA.size === 0 || statesB.size === 0) {
    return false;
  }
  for (const stateA of statesA) {
    for (const stateB of statesB) {
      if (stateA === stateB) {
        continue;
      }
      const pair = [stateA, stateB].sort().join("|");
      if (CONFLICTING_STATE_PAIRS.has(pair)) {
        return true;
      }
    }
  }
  return false;
}

function sequenceRatio(textA, textB) {
  const a = textA ?? "";
  const b = textB ?? "";
  if (a === b) {
    return 1;
  }
  if (!a || !b) {
    return 0;
  }

  const rows = a.length + 1;
  const cols = b.length + 1;
  const table = Array.from({ length: rows }, () => new Uint16Array(cols));

  for (let row = 1; row < rows; row += 1) {
    for (let col = 1; col < cols; col += 1) {
      if (a[row - 1] === b[col - 1]) {
        table[row][col] = table[row - 1][col - 1] + 1;
      } else {
        table[row][col] = Math.max(table[row - 1][col], table[row][col - 1]);
      }
    }
  }

  return (2 * table[rows - 1][cols - 1]) / (a.length + b.length);
}

function productSimilarity(nameA, nameB) {
  const featuresA = productFeatures(nameA);
  const featuresB = productFeatures(nameB);

  if (featuresA.tokenSet.size === 0 || featuresB.tokenSet.size === 0) {
    return 0;
  }
  if (hasStateConflict(featuresA.states, featuresB.states)) {
    return 0;
  }

  const sharedTokens = setIntersection(featuresA.tokenSet, featuresB.tokenSet);
  const sharedStrong = setIntersection(featuresA.strongTokens, featuresB.strongTokens);
  const sharedNumbers = setIntersection(featuresA.numberTokens, featuresB.numberTokens);

  if (sharedStrong.size === 0 && sharedTokens.size < 2) {
    const guard = sequenceRatio(featuresA.canonicalText, featuresB.canonicalText);
    if (guard < 0.78) {
      return 0;
    }
  }

  if (featuresA.numberTokens.size > 0 && featuresB.numberTokens.size > 0 && sharedNumbers.size === 0) {
    return 0;
  }

  const unionSize = setUnionSize(featuresA.tokenSet, featuresB.tokenSet);
  const overlap = sharedTokens.size;
  const jaccard = unionSize ? overlap / unionSize : 0;
  const containment = overlap / Math.max(1, Math.min(featuresA.tokenSet.size, featuresB.tokenSet.size));
  const seqRatio = sequenceRatio(featuresA.canonicalText, featuresB.canonicalText);
  const strongOverlap =
    sharedStrong.size / Math.max(1, Math.min(featuresA.strongTokens.size, featuresB.strongTokens.size));

  let score = 0.44 * Math.max(jaccard, containment) + 0.3 * seqRatio + 0.26 * strongOverlap;

  if (sharedNumbers.size > 0) {
    score += 0.07;
  }

  if (featuresA.categories.size > 0 && featuresB.categories.size > 0) {
    if (setIntersection(featuresA.categories, featuresB.categories).size > 0) {
      score += 0.05;
    } else {
      score -= 0.22;
    }
  }

  return Math.max(0, Math.min(1, score));
}

function buildStoreCatalog(framesByStore) {
  const out = {};
  for (const [storeName, items] of Object.entries(framesByStore)) {
    const valid = items
      .map((item) => ({
        product_key: cleanText(item.product_key).toLowerCase(),
        product_name: cleanText(item.product_name),
        price:
          item.price === null || item.price === undefined || item.price === ""
            ? null
            : Number(item.price),
      }))
      .filter(
        (item) =>
          item.product_key
          && item.product_name
          && (item.price === null || (Number.isFinite(item.price) && item.price > 0)),
      );

    valid.sort((left, right) => {
      const keyCmp = left.product_key.localeCompare(right.product_key);
      if (keyCmp !== 0) {
        return keyCmp;
      }
      if (left.price !== right.price) {
        if (left.price === null) {
          return 1;
        }
        if (right.price === null) {
          return -1;
        }
        return left.price - right.price;
      }
      return left.product_name.localeCompare(right.product_name);
    });

    const grouped = new Map();
    for (const item of valid) {
      const current = grouped.get(item.product_key);
      if (
        !current
        || (current.price === null && item.price !== null)
        || (
          item.price !== null
          && current.price !== null
          && (item.price < current.price || (item.price === current.price && item.product_name < current.product_name))
        )
      ) {
        grouped.set(item.product_key, item);
      }
    }
    out[storeName] = [...grouped.values()];
  }
  return out;
}

function clusterDisplayName(cluster) {
  const candidates = [];
  for (const item of Object.values(cluster.items_by_store)) {
    if (item?.product_name) {
      candidates.push(String(item.product_name));
    }
  }
  const current = cleanText(cluster.product_name);
  if (String(cluster.source ?? "") === "manual" && current) {
    return current;
  }
  if (current) {
    candidates.push(current);
  }
  if (candidates.length === 0) {
    return "UNNAMED PRODUCT";
  }
  return [...new Set(candidates)].sort((left, right) => {
    if (left.length !== right.length) {
      return left.length - right.length;
    }
    return left.localeCompare(right, undefined, { sensitivity: "base" });
  })[0];
}

function upsertClusterItem(cluster, storeName, item, score, source) {
  cluster.items_by_store[storeName] = {
    product_key: String(item.product_key),
    product_name: String(item.product_name),
    price:
      item.price === null || item.price === undefined || item.price === ""
        ? null
        : Number(item.price),
    score: Number(score),
    source,
  };
  if (source === "manual") {
    cluster.source = "manual";
  }
  cluster.product_name = clusterDisplayName(cluster);
}

function newCluster(storeName, item, source, score = 1, productName = "") {
  const cluster = {
    product_name: cleanText(productName) || String(item.product_name),
    source,
    items_by_store: {},
  };
  upsertClusterItem(cluster, storeName, item, score, source);
  return cluster;
}

function clusterSimilarity(productName, cluster) {
  const items = Object.values(cluster.items_by_store);
  if (items.length === 0) {
    return 0;
  }
  let best = 0;
  for (const item of items) {
    best = Math.max(best, productSimilarity(productName, String(item.product_name)));
  }
  return best;
}

function bestClusterForItem(item, clusters, storeName) {
  let bestIndex = -1;
  let bestScore = 0;
  let secondScore = 0;
  const productKey = String(item.product_key);
  const productName = String(item.product_name);

  for (let index = 0; index < clusters.length; index += 1) {
    const cluster = clusters[index];
    if (cluster.items_by_store[storeName]) {
      continue;
    }

    const exactKeyMatch = Object.values(cluster.items_by_store).some(
      (entry) => String(entry.product_key) === productKey,
    );
    if (exactKeyMatch) {
      return { bestIndex: index, bestScore: 1, secondScore: 0 };
    }

    const score = clusterSimilarity(productName, cluster);
    if (score > bestScore) {
      secondScore = bestScore;
      bestScore = score;
      bestIndex = index;
    } else if (score > secondScore) {
      secondScore = score;
    }
  }

  return { bestIndex, bestScore, secondScore };
}

function assignStoreItemsToClusters(clusters, storeName, items, threshold, ambiguityMargin) {
  const eligible = [];
  for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
    const { bestIndex, bestScore, secondScore } = bestClusterForItem(items[itemIndex], clusters, storeName);
    if (bestIndex < 0 || bestScore < threshold || bestScore - secondScore < ambiguityMargin) {
      continue;
    }
    eligible.push({ score: bestScore, itemIndex, clusterIndex: bestIndex });
  }

  eligible.sort((left, right) => right.score - left.score);
  const usedItems = new Set();
  const usedClusters = new Set();
  const assigned = new Set();

  for (const candidate of eligible) {
    if (usedItems.has(candidate.itemIndex) || usedClusters.has(candidate.clusterIndex)) {
      continue;
    }
    usedItems.add(candidate.itemIndex);
    usedClusters.add(candidate.clusterIndex);
    assigned.add(candidate.itemIndex);
    upsertClusterItem(clusters[candidate.clusterIndex], storeName, items[candidate.itemIndex], candidate.score, "auto");
  }

  const unassigned = new Set();
  for (let index = 0; index < items.length; index += 1) {
    if (!assigned.has(index)) {
      unassigned.add(index);
    }
  }
  return { unassigned };
}

function storeLookupTables(itemsByStore) {
  const byKey = {};
  const byName = {};
  for (const [storeName, items] of Object.entries(itemsByStore)) {
    byKey[storeName] = {};
    byName[storeName] = {};
    for (const item of items) {
      byKey[storeName][String(item.product_key)] = item;
      const normalizedName = normalizeKey(String(item.product_name));
      if (normalizedName && !byName[storeName][normalizedName]) {
        byName[storeName][normalizedName] = item;
      }
    }
  }
  return { byKey, byName };
}

function resolveManualItem(storeName, refValue, lookupByKey, lookupByName) {
  const text = cleanText(refValue);
  if (!text) {
    return null;
  }
  if (lookupByKey[storeName]?.[text]) {
    return lookupByKey[storeName][text];
  }
  const normalized = normalizeKey(text);
  if (lookupByName[storeName]?.[normalized]) {
    return lookupByName[storeName][normalized];
  }
  return null;
}

function applyManualRows(clusters, usedKeysByStore, manualRows, lookupByKey, lookupByName) {
  for (const rawRow of manualRows ?? []) {
    if (!rawRow || typeof rawRow !== "object" || typeof rawRow.stores !== "object") {
      continue;
    }

    const cluster = {
      product_name: cleanText(rawRow.product_name),
      source: "manual",
      items_by_store: {},
    };

    for (const [storeName, refValue] of Object.entries(rawRow.stores)) {
      const item = resolveManualItem(storeName, refValue, lookupByKey, lookupByName);
      if (!item) {
        continue;
      }
      const productKey = String(item.product_key);
      if (usedKeysByStore[storeName]?.has(productKey)) {
        continue;
      }
      upsertClusterItem(cluster, storeName, item, 1, "manual");
      usedKeysByStore[storeName].add(productKey);
    }

    if (Object.keys(cluster.items_by_store).length > 0) {
      cluster.product_name = clusterDisplayName(cluster);
      clusters.push(cluster);
    }
  }
}

function clustersToRows(clusters, storeNames) {
  const comparisonRows = [];
  const relationRows = [];
  const relationsRows = [];

  const sortedClusters = [...clusters].sort((left, right) =>
    normalizeKey(clusterDisplayName(left)).localeCompare(normalizeKey(clusterDisplayName(right))),
  );

  sortedClusters.forEach((cluster, rowIndex) => {
    const productName = clusterDisplayName(cluster);
    const productKey = normalizeKey(productName) || `cluster_${rowIndex + 1}`;
    const source = String(cluster.source ?? "auto");
    const itemsByStore = cluster.items_by_store;

    const comparisonRow = { product_key: productKey, Product: productName };
    const relationRow = { product_name: productName, source, stores: {} };
    const relationsRow = { Product: productName, "Match Source": source };

    for (const storeName of storeNames) {
      const item = itemsByStore[storeName];
      if (!item) {
        comparisonRow[storeName] = null;
        relationRow.stores[storeName] = null;
        relationsRow[`${storeName} Product`] = null;
        relationsRow[`${storeName} Price`] = null;
        relationsRow[`${storeName} Score`] = null;
        continue;
      }

      const price =
        item.price === null || item.price === undefined || item.price === ""
          ? null
          : Number(item.price);
      const score = Number(item.score);
      comparisonRow[storeName] = price;
      relationRow.stores[storeName] = {
        product_key: String(item.product_key),
        product_name: String(item.product_name),
        price,
        score,
        source: String(item.source),
      };
      relationsRow[`${storeName} Product`] = String(item.product_name);
      relationsRow[`${storeName} Price`] = price;
      relationsRow[`${storeName} Score`] = Number(score.toFixed(4));
    }

    comparisonRows.push(comparisonRow);
    relationRows.push(relationRow);
    relationsRows.push(relationsRow);
  });

  return { comparisonRows, relationRows, relationsRows };
}

function buildComparisonBundle(
  framesByStore,
  manualRows = null,
  threshold = FUZZY_MATCH_THRESHOLD,
  ambiguityMargin = FUZZY_MATCH_AMBIGUITY_MARGIN,
) {
  const storeNames = Object.keys(framesByStore);
  if (storeNames.length === 0) {
    throw new Error("Listings could not be combined.");
  }

  const itemsByStore = buildStoreCatalog(framesByStore);
  const clusters = [];
  const usedKeysByStore = Object.fromEntries(storeNames.map((storeName) => [storeName, new Set()]));
  const { byKey, byName } = storeLookupTables(itemsByStore);

  if (manualRows?.length) {
    applyManualRows(clusters, usedKeysByStore, manualRows, byKey, byName);
  }

  for (const storeName of storeNames) {
    const remainingItems = itemsByStore[storeName].filter(
      (item) => !usedKeysByStore[storeName].has(String(item.product_key)),
    );

    if (remainingItems.length === 0) {
      continue;
    }

    if (clusters.length === 0) {
      for (const item of remainingItems) {
        clusters.push(newCluster(storeName, item, "auto"));
        usedKeysByStore[storeName].add(String(item.product_key));
      }
      continue;
    }

    const { unassigned } = assignStoreItemsToClusters(
      clusters,
      storeName,
      remainingItems,
      Number(threshold),
      Number(ambiguityMargin),
    );

    [...unassigned].sort((left, right) => left - right).forEach((index) => {
      const item = remainingItems[index];
      clusters.push(newCluster(storeName, item, "auto"));
      usedKeysByStore[storeName].add(String(item.product_key));
    });

    for (const cluster of clusters) {
      const item = cluster.items_by_store[storeName];
      if (item) {
        usedKeysByStore[storeName].add(String(item.product_key));
      }
    }
  }

  if (clusters.length === 0) {
    throw new Error("Listings could not be combined.");
  }

  const { comparisonRows, relationRows, relationsRows } = clustersToRows(clusters, storeNames);
  comparisonRows.sort((left, right) => String(left.Product).localeCompare(String(right.Product)));
  relationsRows.sort((left, right) => String(left.Product).localeCompare(String(right.Product)));

  return {
    comparisonRows,
    relationRows,
    relationsRows,
    storeColumns: storeNames,
  };
}

function buildRankingRows(comparisonRows, storeColumns) {
  const counts = Object.fromEntries(storeColumns.map((store) => [store, 0]));

  for (const row of comparisonRows) {
    const prices = {};
    for (const storeName of storeColumns) {
      const value = row[storeName];
      if (
        value === null
        || value === undefined
        || value === ""
        || !Number.isFinite(Number(value))
        || Number(value) <= 0
      ) {
        continue;
      }
      prices[storeName] = Number(value);
    }

    const numericValues = Object.values(prices);
    if (numericValues.length === 0) {
      continue;
    }

    const minimum = Math.min(...numericValues);
    for (const [storeName, price] of Object.entries(prices)) {
      if (Math.abs(price - minimum) < 1e-9) {
        counts[storeName] += 1;
      }
    }
  }

  return storeColumns
    .map((storeName) => ({
      Store: storeName,
      "Products with best price": counts[storeName],
    }))
    .sort((left, right) => {
      const diff = right["Products with best price"] - left["Products with best price"];
      if (diff !== 0) {
        return diff;
      }
      return left.Store.localeCompare(right.Store);
    });
}

const PROVIDER_KEYS = ["sysco", "kohl", "usfood"];
const PROVIDER_COLUMN_BY_KEY = {
  sysco: "nombre_sysco",
  kohl: "nombre_kohl",
  usfood: "nombre_usfood",
};
const STANDARD_RELATIONS_COLUMNS = [
  "nombre_producto",
  "nombre_sysco",
  "nombre_kohl",
  "nombre_usfood",
];
const RELATION_VALUE_PLACEHOLDERS = new Set([
  "-",
  "--",
  "—",
  "n/a",
  "na",
  "none",
  "null",
  "sin dato",
  "s/d",
]);

function normalizeRelationValue(value) {
  const text = cleanText(value);
  if (!text) {
    return "";
  }
  if (RELATION_VALUE_PLACEHOLDERS.has(text.toLowerCase())) {
    return "";
  }
  return normalizeKey(text) ? text : "";
}

function providerKeyFromStoreName(storeName) {
  const normalized = normalizeKey(storeName);
  if (!normalized) {
    return null;
  }
  const tokens = new Set(normalized.split(" "));
  if (tokens.has("sysco") || normalized.includes("sysco")) {
    return "sysco";
  }
  if (tokens.has("kohl") || normalized.includes("kohl")) {
    return "kohl";
  }
  if (tokens.has("usfoods") || (tokens.has("us") && (tokens.has("food") || tokens.has("foods")))) {
    return "usfood";
  }
  return null;
}

function buildStoreProviderMapping(storeColumns) {
  const storeToProvider = {};
  const usedProviders = new Set();

  for (const storeName of storeColumns) {
    const providerKey = providerKeyFromStoreName(storeName);
    if (!providerKey || usedProviders.has(providerKey)) {
      continue;
    }
    storeToProvider[storeName] = providerKey;
    usedProviders.add(providerKey);
  }

  const remaining = PROVIDER_KEYS.filter((providerKey) => !usedProviders.has(providerKey));
  for (const storeName of storeColumns) {
    if (storeToProvider[storeName] || remaining.length === 0) {
      continue;
    }
    const providerKey = remaining.shift();
    storeToProvider[storeName] = providerKey;
    usedProviders.add(providerKey);
  }

  const providerToStore = Object.fromEntries(PROVIDER_KEYS.map((providerKey) => [providerKey, null]));
  for (const [storeName, providerKey] of Object.entries(storeToProvider)) {
    if (!providerToStore[providerKey]) {
      providerToStore[providerKey] = storeName;
    }
  }

  return { storeToProvider, providerToStore };
}

function relationsRowsToStandard(relationsRows, storeColumns) {
  const { storeToProvider } = buildStoreProviderMapping(storeColumns);
  return (relationsRows ?? []).map((row) => {
    const outRow = Object.fromEntries(STANDARD_RELATIONS_COLUMNS.map((column) => [column, ""]));
    outRow.nombre_producto = normalizeRelationValue(row.Product);

    for (const storeName of storeColumns) {
      const providerKey = storeToProvider[storeName];
      if (!providerKey) {
        continue;
      }
      const productName = normalizeRelationValue(row[`${storeName} Product`]);
      if (productName) {
        outRow[PROVIDER_COLUMN_BY_KEY[providerKey]] = productName;
      }
    }

    if (!outRow.nombre_producto) {
      for (const columnName of STANDARD_RELATIONS_COLUMNS.slice(1)) {
        if (outRow[columnName]) {
          outRow.nombre_producto = outRow[columnName];
          break;
        }
      }
    }
    return outRow;
  });
}

function manualRowsToStandardRows(manualRows, storeColumns) {
  const { storeToProvider } = buildStoreProviderMapping(storeColumns);
  return (manualRows ?? [])
    .map((row) => {
      const outRow = Object.fromEntries(STANDARD_RELATIONS_COLUMNS.map((column) => [column, ""]));
      outRow.nombre_producto = normalizeRelationValue(row.product_name);

      for (const [storeName, refValue] of Object.entries(row.stores ?? {})) {
        const providerKey = storeToProvider[storeName];
        if (!providerKey) {
          continue;
        }
        const text = normalizeRelationValue(refValue);
        if (text) {
          outRow[PROVIDER_COLUMN_BY_KEY[providerKey]] = text;
        }
      }

      if (!outRow.nombre_producto) {
        for (const columnName of STANDARD_RELATIONS_COLUMNS.slice(1)) {
          if (outRow[columnName]) {
            outRow.nombre_producto = outRow[columnName];
            break;
          }
        }
      }
      return outRow;
    })
    .filter((row) => STANDARD_RELATIONS_COLUMNS.some((column) => row[column]));
}

function findProviderColumns(rows) {
  const columns = new Map();
  for (const row of rows) {
    for (const columnName of Object.keys(row ?? {})) {
      const providerKey = providerKeyFromStoreName(columnName);
      if (providerKey && !columns.has(providerKey)) {
        columns.set(providerKey, columnName);
      }
    }
  }
  return columns;
}

function findGroupColumn(rows) {
  const preferred = ["nombre_producto", "COMMON NAME", "Common Name", "Product", "producto"];
  const available = new Set();
  for (const row of rows) {
    for (const columnName of Object.keys(row ?? {})) {
      available.add(columnName);
    }
  }

  for (const columnName of preferred) {
    if (available.has(columnName)) {
      return columnName;
    }
  }

  for (const columnName of available) {
    if (new Set(["common name", "nombre producto", "product", "producto"]).has(normalizeKey(columnName))) {
      return columnName;
    }
  }
  return null;
}

function providerRelationsRowsToManualRows(rows, storeColumns) {
  const providerColumns = findProviderColumns(rows);
  if (providerColumns.size === 0) {
    return [];
  }

  const { providerToStore } = buildStoreProviderMapping(storeColumns);
  const groupColumn = findGroupColumn(rows);
  const manualRows = [];

  for (const row of rows) {
    const stores = {};
    for (const [providerKey, sourceColumn] of providerColumns.entries()) {
      const storeName = providerToStore[providerKey];
      if (!storeName) {
        continue;
      }
      const productName = normalizeRelationValue(row[sourceColumn]);
      if (productName) {
        stores[storeName] = productName;
      }
    }

    if (Object.keys(stores).length === 0) {
      continue;
    }

    let groupName = "";
    if (groupColumn) {
      groupName = normalizeRelationValue(row[groupColumn]);
    }
    if (!groupName) {
      groupName = Object.values(stores)[0];
    }

    manualRows.push({ product_name: groupName, stores });
  }

  return manualRows;
}

function legacyRelationsRowsToManualRows(rows, storeColumns) {
  const productColumns = storeColumns.map((storeName) => `${storeName} Product`);
  const allColumnsExist = productColumns.every((columnName) =>
    rows.some((row) => Object.prototype.hasOwnProperty.call(row, columnName)),
  );
  if (!allColumnsExist) {
    return [];
  }

  const manualRows = [];
  for (const row of rows) {
    const stores = {};
    storeColumns.forEach((storeName, index) => {
      const productName = normalizeRelationValue(row[productColumns[index]]);
      if (productName) {
        stores[storeName] = productName;
      }
    });

    if (Object.keys(stores).length === 0) {
      continue;
    }

    const groupName = normalizeRelationValue(row.Product) || Object.values(stores)[0];
    manualRows.push({ product_name: groupName, stores });
  }
  return manualRows;
}

function standardRelationsRowsToManualRows(rows, storeColumns) {
  const rowColumns = new Set();
  for (const row of rows) {
    for (const columnName of Object.keys(row ?? {})) {
      rowColumns.add(columnName);
    }
  }
  const isStandard = STANDARD_RELATIONS_COLUMNS.every((columnName) => rowColumns.has(columnName));
  if (!isStandard) {
    return [];
  }

  const { providerToStore } = buildStoreProviderMapping(storeColumns);
  const manualRows = [];

  for (const row of rows) {
    const stores = {};
    for (const providerKey of PROVIDER_KEYS) {
      const storeName = providerToStore[providerKey];
      if (!storeName) {
        continue;
      }
      const productName = normalizeRelationValue(row[PROVIDER_COLUMN_BY_KEY[providerKey]]);
      if (productName) {
        stores[storeName] = productName;
      }
    }

    if (Object.keys(stores).length === 0) {
      continue;
    }

    const groupName = normalizeRelationValue(row.nombre_producto) || Object.values(stores)[0];
    manualRows.push({ product_name: groupName, stores });
  }

  return manualRows;
}

function relationsSheetRowsToManualRows(rows, storeColumns) {
  const standardRows = standardRelationsRowsToManualRows(rows, storeColumns);
  if (standardRows.length > 0) {
    return standardRows;
  }

  const providerRows = providerRelationsRowsToManualRows(rows, storeColumns);
  if (providerRows.length > 0) {
    return providerRows;
  }

  return legacyRelationsRowsToManualRows(rows, storeColumns);
}

function deduplicateManualRows(rows) {
  const uniqueRows = [];
  const seen = new Set();

  for (const row of rows ?? []) {
    if (!row || typeof row !== "object" || typeof row.stores !== "object") {
      continue;
    }

    const normalizedStores = {};
    for (const [storeName, productRef] of Object.entries(row.stores)) {
      const storeText = cleanText(storeName);
      const productText = cleanText(productRef);
      if (storeText && productText) {
        normalizedStores[storeText] = productText;
      }
    }

    if (Object.keys(normalizedStores).length === 0) {
      continue;
    }

    const signature = Object.entries(normalizedStores)
      .sort(([leftName], [rightName]) => leftName.localeCompare(rightName))
      .map(([storeName, productName]) => `${storeName}:${productName}`)
      .join("|");
    if (seen.has(signature)) {
      continue;
    }
    seen.add(signature);
    uniqueRows.push({
      product_name: cleanText(row.product_name),
      stores: normalizedStores,
    });
  }

  return uniqueRows;
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function rgbGradientGreenWhite(ratio) {
  const bounded = Math.max(0, Math.min(1, Number(ratio)));
  const green = [0, 200, 0];
  const white = [255, 255, 255];
  const red = Math.round(green[0] + (white[0] - green[0]) * bounded);
  const greenValue = Math.round(green[1] + (white[1] - green[1]) * bounded);
  const blue = Math.round(green[2] + (white[2] - green[2]) * bounded);
  return `FF${red.toString(16).padStart(2, "0")}${greenValue
    .toString(16)
    .padStart(2, "0")}${blue.toString(16).padStart(2, "0")}`.toUpperCase();
}

export {
  DEFAULT_OUTPUT_FILE,
  DEFAULT_STORE_NAMES,
  FUZZY_MATCH_AMBIGUITY_MARGIN,
  FUZZY_MATCH_THRESHOLD,
  STANDARD_RELATIONS_COLUMNS,
  buildComparisonBundle,
  buildComparisonSignature,
  buildRankingRows,
  buildStoreCatalog,
  cleanText,
  deduplicateManualRows,
  defaultStoreNameForIndex,
  detectProviderNameFromText,
  ensureUniqueNames,
  formatCurrency,
  manualRowsToStandardRows,
  normalizeKey,
  parseListingPdfPages,
  providerKeyFromStoreName,
  relationsRowsToStandard,
  relationsSheetRowsToManualRows,
  rgbGradientGreenWhite,
};

/* global DecompressionStream, speechSynthesis, SpeechSynthesisUtterance */

const state = {
  data: null,
  locale: null,
  localeName: "ru",
  pageIndex: 0,
  zoom: 1,
  selected: new Set(),
  activeWord: null,
  showBoxes: true,
  showRegions: true,
  showLines: true,
  showBlocks: true,
  isReading: false,
  readerCursor: null,
};

const $ = (id) => document.getElementById(id);

async function fetchJsonWithBrotliFallback(basePath) {
  const brPath = `${basePath}.br`;
  try {
    const response = await fetch(brPath);
    if (!response.ok) throw new Error(`${brPath}: ${response.status}`);

    if (typeof DecompressionStream !== "undefined") {
      let stream = null;
      try {
        stream = response.body.pipeThrough(new DecompressionStream("br"));
      } catch (_error) {
        stream = response.body.pipeThrough(new DecompressionStream("brotli"));
      }
      const text = await new Response(stream).text();
      return JSON.parse(text);
    }
  } catch (error) {
    console.warn("Brotli JSON fallback to plain JSON:", error);
  }

  const fallback = await fetch(basePath);
  if (!fallback.ok) throw new Error(`${basePath}: ${fallback.status}`);
  return fallback.json();
}

async function loadLocale(name) {
  state.localeName = name;
  try {
    state.locale = await fetchJsonWithBrotliFallback(`locales/${name}.json`);
  } catch (error) {
    console.warn(`Locale ${name} not loaded`, error);
    state.locale = null;
  }
  updateStatus();
}

function restoreWords(page) {
  if (page._restoredWords) return page._restoredWords;

  let x = 0;
  let y = 0;
  page._restoredWords = page.words.map((encoded, index) => {
    const [wordIdx, dx, dy, w, h, conf] = encoded;
    x += dx;
    y += dy;

    const meta = page.wordMeta?.[index] || {};
    return {
      index,
      text: state.data.dict.words[wordIdx] || "",
      x,
      y,
      w,
      h,
      conf,
      source: meta.source || "",
      rule: meta.rule || "",
      sentenceId: null,
      lineId: null,
    };
  });

  for (const line of page.lines || []) {
    for (const wordIndex of line.wordIndexes || []) {
      if (page._restoredWords[wordIndex]) page._restoredWords[wordIndex].lineId = line.id;
    }
  }

  for (const sentence of page.sentences || []) {
    for (const wordIndex of sentence.wordIndexes || []) {
      if (page._restoredWords[wordIndex]) page._restoredWords[wordIndex].sentenceId = sentence.id;
    }
  }

  return page._restoredWords;
}

function currentPage() {
  return state.data.pages[state.pageIndex];
}

function pageSelectedText() {
  const page = currentPage();
  const words = restoreWords(page);
  const lines = [...(page.lines || [])].sort((a, b) => a.y - b.y || a.x - b.x);

  if (lines.length) {
    return lines
      .map((line) => (line.wordIndexes || [])
        .filter((idx) => state.selected.has(idx))
        .sort((a, b) => words[a].x - words[b].x)
        .map((idx) => words[idx].text)
        .join(" "))
      .filter(Boolean)
      .join("\n");
  }

  return [...state.selected]
    .sort((a, b) => a - b)
    .map((idx) => words[idx]?.text)
    .filter(Boolean)
    .join(" ");
}

function updateStatus(message = "") {
  const data = state.data;
  if (!data) return;

  const page = currentPage();
  const selectedCount = state.selected.size;
  $("status").textContent = [
    `Страница ${state.pageIndex + 1}/${data.pages.length}`,
    `${restoreWords(page).length} слов`,
    `${selectedCount} выбрано`,
    `zoom ${Math.round(state.zoom * 100)}%`,
    `locale ${state.localeName}`,
    message,
  ].filter(Boolean).join(" · ");
}

function clearSelection() {
  state.selected.clear();
  state.activeWord = null;
  renderSelection();
}

function selectWords(wordIndexes, activeWord = null) {
  state.selected = new Set(wordIndexes);
  state.activeWord = activeWord;
  renderSelection();
}

function selectSentence(wordIndex) {
  const page = currentPage();
  const word = restoreWords(page)[wordIndex];
  if (!word) return;

  const sentence = (page.sentences || []).find((item) => item.id === word.sentenceId);
  if (sentence) {
    selectWords(sentence.wordIndexes || [], wordIndex);
    return;
  }

  selectLineLeftPart(wordIndex);
}

function selectLineLeftPart(wordIndex) {
  const page = currentPage();
  const words = restoreWords(page);
  const word = words[wordIndex];
  if (!word) return;

  const line = (page.lines || []).find((item) => item.id === word.lineId);
  if (!line) {
    selectWords([wordIndex], wordIndex);
    return;
  }

  const selected = (line.wordIndexes || []).filter((idx) => words[idx] && words[idx].x <= word.x);
  selectWords(selected, wordIndex);
}

function renderSelection() {
  document.querySelectorAll(".word-box").forEach((node) => {
    const index = Number(node.dataset.wordIndex);
    node.classList.toggle("selected", state.selected.has(index));
    node.classList.toggle("active", state.activeWord === index);
  });
  updateStatus();
}

function scaledStyle(item) {
  return [
    `left:${item.x * state.zoom}px`,
    `top:${item.y * state.zoom}px`,
    `width:${item.w * state.zoom}px`,
    `height:${item.h * state.zoom}px`,
  ].join(";");
}

function drawRectLayer(container, className, items, labelFactory) {
  for (const item of items || []) {
    const node = document.createElement("div");
    node.className = className;
    node.style.cssText = scaledStyle(item);
    if (labelFactory) node.textContent = labelFactory(item);
    container.appendChild(node);
  }
}

function drawLines(container, page) {
  for (const line of page.lineObjects || []) {
    const node = document.createElement("div");
    node.className = "detected-line";

    const x = Math.min(line.x1, line.x2) * state.zoom;
    const y = Math.min(line.y1, line.y2) * state.zoom;
    const w = Math.max(1, Math.abs(line.x2 - line.x1)) * state.zoom;
    const h = Math.max(1, Math.abs(line.y2 - line.y1)) * state.zoom;

    node.style.cssText = [
      `left:${x}px`,
      `top:${y}px`,
      `width:${Math.max(w, 2)}px`,
      `height:${Math.max(h, 2)}px`,
    ].join(";");
    node.title = `${line.orientation}, ${line.rule}`;
    container.appendChild(node);
  }
}

function renderPage() {
  const page = currentPage();
  const words = restoreWords(page);
  const container = $("page-container");
  container.innerHTML = "";
  container.style.width = `${page.w * state.zoom}px`;

  const pageNode = document.createElement("div");
  pageNode.className = "page";
  pageNode.style.width = `${page.w * state.zoom}px`;
  pageNode.style.height = `${page.h * state.zoom}px`;

  const image = document.createElement("img");
  image.className = "page-image";
  image.src = `data/${page.img}`;
  image.width = page.w * state.zoom;
  image.height = page.h * state.zoom;
  pageNode.appendChild(image);

  const overlay = document.createElement("div");
  overlay.className = "overlay";
  pageNode.appendChild(overlay);

  if (state.showBlocks) drawRectLayer(overlay, "text-block", page.blocks || [], (item) => String(item.id));
  if (state.showRegions) drawRectLayer(overlay, "empty-region", page.regions || [], (item) => String(item.order || ""));
  if (state.showLines) drawLines(overlay, page);

  if (state.showBoxes) {
    for (const word of words) {
      const node = document.createElement("button");
      node.type = "button";
      node.className = "word-box";
      node.dataset.wordIndex = String(word.index);
      node.style.cssText = scaledStyle(word);
      node.title = `${word.text}\nconf=${word.conf}\nsource=${word.source}\nrule=${word.rule}`;
      node.setAttribute("aria-label", word.text);
      node.addEventListener("click", (event) => {
        event.preventDefault();
        selectSentence(word.index);
      });
      overlay.appendChild(node);
    }
  }

  drawRectLayer(overlay, "marker", page.markers || [], (item) => item.marker || "");

  container.appendChild(pageNode);
  renderSelection();
}

function setPage(index) {
  state.pageIndex = Math.max(0, Math.min(state.data.pages.length - 1, index));
  clearSelection();
  renderPage();
}

function setZoom(value) {
  state.zoom = Math.max(0.25, Math.min(4, Number(value)));
  $("zoom").value = String(state.zoom);
  renderPage();
}

function selectedOrCurrentSentenceText() {
  if (state.selected.size) return pageSelectedText();

  const page = currentPage();
  const sentence = page.sentences?.[0];
  if (sentence) {
    selectWords(sentence.wordIndexes || [], sentence.wordIndexes?.[0] ?? null);
    return sentence.text || "";
  }

  return restoreWords(page).map((word) => word.text).join(" ");
}

function localeSentenceText(pageIndex, sentenceId) {
  const pageLocale = state.locale?.[pageIndex];
  if (!pageLocale) return "";
  if (Array.isArray(pageLocale)) return pageLocale[sentenceId] || "";
  return pageLocale[String(sentenceId)] || "";
}

function speakText(text, lang, onEnd) {
  if (!text || !("speechSynthesis" in window)) {
    if (onEnd) onEnd();
    return;
  }

  speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = Number($("speech-rate").value || 1);

  utterance.onboundary = (event) => {
    if (event.name !== "word" && event.charIndex == null) return;
    highlightWordByCharIndex(text, event.charIndex || 0);
  };
  utterance.onend = () => {
    if (onEnd) onEnd();
  };
  utterance.onerror = () => {
    if (onEnd) onEnd();
  };

  speechSynthesis.speak(utterance);
}

function highlightWordByCharIndex(text, charIndex) {
  if (!state.selected.size) return;
  const selected = [...state.selected].sort((a, b) => a - b);
  const page = currentPage();
  const words = restoreWords(page);

  let offset = 0;
  for (const idx of selected) {
    const word = words[idx];
    if (!word) continue;
    const start = offset;
    const end = offset + word.text.length;
    if (charIndex >= start && charIndex <= end) {
      state.activeWord = idx;
      renderSelection();
      return;
    }
    offset = end + 1;
  }
}

function speakSelected() {
  const text = selectedOrCurrentSentenceText();
  speakText(text, "en-US", () => {
    const page = currentPage();
    const active = state.activeWord != null ? restoreWords(page)[state.activeWord] : null;
    const sentenceId = active?.sentenceId ?? 0;
    const translated = localeSentenceText(state.pageIndex, sentenceId);
    if (translated) speakText(translated, "ru-RU");
  });
}

function sentenceAtSelectionOrStart() {
  const page = currentPage();
  if (state.activeWord != null) {
    const word = restoreWords(page)[state.activeWord];
    if (word && word.sentenceId != null) return word.sentenceId;
  }
  return 0;
}

function readNextSentence() {
  if (!state.isReading) return;

  const page = currentPage();
  const sentences = page.sentences || [];
  const sentenceId = state.readerCursor?.sentenceId ?? 0;

  if (sentenceId >= sentences.length) {
    if (state.pageIndex + 1 >= state.data.pages.length) {
      state.isReading = false;
      updateStatus("Чтение завершено");
      return;
    }
    state.pageIndex += 1;
    state.readerCursor = { pageIndex: state.pageIndex, sentenceId: 0 };
    renderPage();
    readNextSentence();
    return;
  }

  const sentence = sentences[sentenceId];
  selectWords(sentence.wordIndexes || [], sentence.wordIndexes?.[0] ?? null);

  speakText(sentence.text, "en-US", () => {
    const translated = localeSentenceText(state.pageIndex, sentenceId);
    const continueReading = () => {
      state.readerCursor = { pageIndex: state.pageIndex, sentenceId: sentenceId + 1 };
      readNextSentence();
    };
    if (translated) speakText(translated, "ru-RU", continueReading);
    else continueReading();
  });
}

function toggleSequentialReading() {
  state.isReading = !state.isReading;
  $("read-doc").textContent = state.isReading ? "Остановить чтение" : "Последовательное чтение";
  if (!state.isReading) {
    speechSynthesis.cancel();
    return;
  }

  state.readerCursor = {
    pageIndex: state.pageIndex,
    sentenceId: sentenceAtSelectionOrStart(),
  };
  readNextSentence();
}

function bindUi() {
  $("prev-page").addEventListener("click", () => setPage(state.pageIndex - 1));
  $("next-page").addEventListener("click", () => setPage(state.pageIndex + 1));
  $("zoom").addEventListener("input", (event) => setZoom(event.target.value));

  $("toggle-boxes").addEventListener("change", (event) => {
    state.showBoxes = event.target.checked;
    renderPage();
  });
  $("toggle-regions").addEventListener("change", (event) => {
    state.showRegions = event.target.checked;
    renderPage();
  });
  $("toggle-lines").addEventListener("change", (event) => {
    state.showLines = event.target.checked;
    renderPage();
  });
  $("toggle-blocks").addEventListener("change", (event) => {
    state.showBlocks = event.target.checked;
    renderPage();
  });

  $("lang-ru").addEventListener("click", () => loadLocale("ru"));
  $("lang-en").addEventListener("click", () => loadLocale("en"));
  $("speak-selected").addEventListener("click", speakSelected);
  $("read-doc").addEventListener("click", toggleSequentialReading);

  document.addEventListener("copy", (event) => {
    if (!state.selected.size) return;
    event.clipboardData.setData("text/plain", pageSelectedText());
    event.preventDefault();
    updateStatus("Текст скопирован");
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") setPage(state.pageIndex - 1);
    if (event.key === "ArrowRight") setPage(state.pageIndex + 1);
    if (event.key === "Escape") clearSelection();
  });
}

async function init() {
  bindUi();
  state.data = await fetchJsonWithBrotliFallback("data/pages.word_select.delta.json");
  await loadLocale("ru");
  renderPage();
}

init().catch((error) => {
  console.error(error);
  $("status").textContent = `Ошибка загрузки: ${error.message}`;
});

// Глобальные данные
let pages = [];
let fonts = [];
let colors = [];
let sources = [];
let svgs = [];
let styles = [];
let pageSizes = [];
let translations = {};
let currentLang = 'ru';
let currentPage = 1;

// DOM-элементы
const container = document.getElementById('page-container');
const pageIndicator = document.getElementById('pageIndicator');
const btnPrev = document.getElementById('btnPrev');
const btnNext = document.getElementById('btnNext');
const pageInput = document.getElementById('pageInput');
const btnGo = document.getElementById('btnGo');
const btnLangRu = document.getElementById('btnLangRu');
const btnLangEn = document.getElementById('btnLangEn');

// --- Загрузка Brotli-данных ---
async function loadBrotliJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Не удалось загрузить ${path} (HTTP ${response.status})`);
  }
  if (response.headers.get('content-encoding') !== 'br') {
    throw new Error(`${path} отдан без Content-Encoding: br. Запустите: python server.py`);
  }
  return response.json();
}

async function loadData(lang) {
  try {
    if (!pages.length) {
      const documentData = await loadBrotliJson('data/pages.json.br');
      const [version, loadedFonts, loadedColors, loadedSources, loadedSvgs, loadedStyles, loadedPageSizes, loadedPages] = documentData;
      if (version !== 1) {
        throw new Error(`Неподдерживаемая версия pages.json.br: ${version}`);
      }
      fonts = loadedFonts;
      colors = loadedColors;
      sources = loadedSources;
      svgs = loadedSvgs;
      styles = loadedStyles;
      pageSizes = loadedPageSizes;
      pages = loadedPages;
    }

    if (!translations[lang]) {
      translations[lang] = await loadBrotliJson(`locales/${lang}.json.br`);
    }

    currentLang = lang;
    renderPage(currentPage);
  } catch (error) {
    alert('Ошибка загрузки: ' + error.message);
    console.error(error);
  }
}

// --- Рендер одной страницы ---
function renderPage(pageNum) {
  if (!pages.length || !translations[currentLang]) return;

  const pageData = pages[pageNum - 1];
  if (!pageData) return;

  const [pageSizeIdx, elements] = pageData;
  const [pageWidth, pageHeight] = pageSizes[pageSizeIdx];
  const transData = translations[currentLang][pageNum - 1];

  container.innerHTML = '';
  const pageDiv = document.createElement('div');
  pageDiv.className = 'page';
  pageDiv.style.width = pageWidth + 'px';
  pageDiv.style.height = pageHeight + 'px';

  elements.forEach(el => {
    const type = el[0];
    if (type === 0) {
      const [, textIdx, styleIdx, x, y, w, h] = el;
      const [fontIdx, size, flags, colorIdx] = styles[styleIdx];
      const span = document.createElement('span');
      span.className = 'text-element';
      span.style.left = x + 'px';
      span.style.top = y + 'px';
      span.style.fontFamily = fonts[fontIdx];
      span.style.fontSize = size + 'px';
      span.style.fontWeight = flags & 1 ? 'bold' : 'normal';
      span.style.fontStyle = flags & 2 ? 'italic' : 'normal';
      span.style.color = colors[colorIdx] || '#000';
      span.style.width = w + 'px';
      span.style.height = h + 'px';
      span.textContent = transData[textIdx] || '';
      pageDiv.appendChild(span);
    } else if (type === 1) {
      const [, srcIdx, x, y, w, h] = el;
      const img = document.createElement('img');
      img.src = 'data/' + sources[srcIdx];  // путь относительно корня, к data/images/...
      img.style.position = 'absolute';
      img.style.left = x + 'px';
      img.style.top = y + 'px';
      img.style.width = w + 'px';
      img.style.height = h + 'px';
      pageDiv.appendChild(img);
    } else if (type === 2) {
      const [, svgIdx, x, y, w, h] = el;
      const svgWrapper = document.createElement('div');
      svgWrapper.innerHTML = svgs[svgIdx];
      const svg = svgWrapper.firstChild;
      svg.style.position = 'absolute';
      svg.style.left = x + 'px';
      svg.style.top = y + 'px';
      svg.style.width = w + 'px';
      svg.style.height = h + 'px';
      pageDiv.appendChild(svg);
    }
  });

  container.appendChild(pageDiv);
  updateControls(pageNum);
}

// --- Навигация ---
function updateControls(pageNum) {
  pageIndicator.textContent = `Страница ${pageNum} из ${pages.length}`;
  pageInput.value = pageNum;
  pageInput.max = pages.length;
  btnPrev.disabled = pageNum <= 1;
  btnNext.disabled = pageNum >= pages.length;
}

function goToPage(pageNum) {
  if (pageNum < 1 || pageNum > pages.length || pageNum === currentPage) return;
  currentPage = pageNum;
  renderPage(currentPage);
}

// --- Обработчики ---
btnPrev.addEventListener('click', () => goToPage(currentPage - 1));
btnNext.addEventListener('click', () => goToPage(currentPage + 1));
btnGo.addEventListener('click', () => {
  const page = parseInt(pageInput.value, 10);
  if (!isNaN(page)) goToPage(page);
});
pageInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    const page = parseInt(pageInput.value, 10);
    if (!isNaN(page)) goToPage(page);
  }
});

btnLangRu.addEventListener('click', () => loadData('ru'));
btnLangEn.addEventListener('click', () => loadData('en'));

// --- Старт ---
if (window.location.protocol === 'file:') {
  alert('Открытие через file:// не поддерживается. Запустите: python server.py');
} else {
  loadData('ru');
}
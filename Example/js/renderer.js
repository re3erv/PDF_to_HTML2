// В HTML нужно добавить:
// <script src="https://cdn.jsdelivr.net/npm/@msgpack/msgpack@2.8.0/dist.es5+umd/msgpack.min.js"></script>
// или использовать import maps.

// В данном скрипте используем глобальный объект MessagePack из CDN

let pages = [];
let fontList = [];
let colorList = [];
let imageList = [];
let translations = {};
let currentLang = 'ru';
let currentPage = 1;

const container = document.getElementById('page-container');
const pageIndicator = document.getElementById('pageIndicator');
const btnPrev = document.getElementById('btnPrev');
const btnNext = document.getElementById('btnNext');
const pageInput = document.getElementById('pageInput');
const btnGo = document.getElementById('btnGo');
const btnLangRu = document.getElementById('btnLangRu');
const btnLangEn = document.getElementById('btnLangEn');

// --- Декомпрессия gzip ---
async function decompressGzip(buffer) {
  const ds = new DecompressionStream('gzip');
  const blob = new Blob([buffer]);
  const stream = blob.stream().pipeThrough(ds);
  const response = new Response(stream);
  return await response.arrayBuffer();
}

// --- Загрузка MessagePack из gzip ---
async function fetchMsgPackGz(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Не удалось загрузить ${url}`);
  const compressed = await resp.arrayBuffer();
  const decompressed = await decompressGzip(compressed);
  return MessagePack.decode(decompressed);
}

// --- Загрузка данных ---
async function loadData(lang) {
  try {
    // Загружаем pages.msgpack.gz один раз
    if (!pages.length) {
      const data = await fetchMsgPackGz('data/pages.msgpack.gz');
      fontList = data.fonts;
      colorList = data.colors;
      imageList = data.images;
      pages = data.pages;   // массив [width, height, elements]
    }

    // Загружаем локали для языка
    if (!translations[lang]) {
      const raw = await fetchMsgPackGz(`locales/${lang}.msgpack.gz`);
      // raw = [words, pagesOfIndexes]
      const words = raw[0];
      const pagesOfIndexes = raw[1];
      // Преобразуем в массив массивов строк
      translations[lang] = pagesOfIndexes.map(pageIdxs =>
        pageIdxs.map(idx => words[idx])
      );
    }

    currentLang = lang;
    renderPage(currentPage);
  } catch (error) {
    alert('Ошибка загрузки: ' + error.message);
    console.error(error);
  }
}

// --- Рендер страницы ---
function renderPage(pageNum) {
  if (!pages.length || !translations[currentLang]) return;

  const pageData = pages[pageNum - 1]; // [width, height, elements]
  if (!pageData) return;
  const [pageWidth, pageHeight, elements] = pageData;

  const transData = translations[currentLang][pageNum - 1];
  container.innerHTML = '';
  const pageDiv = document.createElement('div');
  pageDiv.className = 'page';
  pageDiv.style.width = pageWidth + 'px';
  pageDiv.style.height = pageHeight + 'px';

  elements.forEach(el => {
    const type = el[0];
    if (type === 0) {   // text
      const [_, textIdx, fontIdx, size, boldFlag, italicFlag, colorIdx, x, y, w, h] = el;
      const span = document.createElement('span');
      span.className = 'text-element';
      span.style.position = 'absolute';
      span.style.left = x + 'px';
      span.style.top = y + 'px';
      span.style.fontFamily = fontList[fontIdx];
      span.style.fontSize = size + 'px';
      span.style.fontWeight = boldFlag ? 'bold' : 'normal';
      span.style.fontStyle = italicFlag ? 'italic' : 'normal';
      span.style.color = (colorIdx >= 0 && colorIdx < colorList.length) ? colorList[colorIdx] : '#000';
      span.style.width = w + 'px';
      span.style.height = h + 'px';
      span.textContent = transData[textIdx] || '';
      pageDiv.appendChild(span);
    } else if (type === 1) {  // image
      const [_, srcIdx, x, y, w, h] = el;
      const img = document.createElement('img');
      img.src = 'data/' + imageList[srcIdx];
      img.style.position = 'absolute';
      img.style.left = x + 'px';
      img.style.top = y + 'px';
      img.style.width = w + 'px';
      img.style.height = h + 'px';
      pageDiv.appendChild(img);
    } else if (type === 2) {  // svg
      const [_, svgString, x, y, w, h] = el;
      const svgWrapper = document.createElement('div');
      svgWrapper.innerHTML = svgString;
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

// --- Навигация (без изменений) ---
function updateControls(pageNum) {
  pageIndicator.textContent = `Страница ${pageNum} из ${pages.length}`;
  pageInput.value = pageNum;
  btnPrev.disabled = pageNum <= 1;
  btnNext.disabled = pageNum >= pages.length;
}

function goToPage(pageNum) {
  if (pageNum < 1 || pageNum > pages.length || pageNum === currentPage) return;
  currentPage = pageNum;
  renderPage(currentPage);
}

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

// Старт
(async () => {
  await loadData('ru');
})();
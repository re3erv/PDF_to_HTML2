// Глобальные данные
let pages = [];
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

// --- Распаковка gzip ---
async function decompressGzip(buffer) {
  const ds = new DecompressionStream('gzip');
  const blob = new Blob([buffer]);
  const stream = blob.stream().pipeThrough(ds);
  const response = new Response(stream);
  return await response.arrayBuffer();
}

// --- Загрузка данных ---
async function loadData(lang) {
  try {
    // Загружаем pages.json.gz один раз
    if (!pages.length) {
      const pagesResp = await fetch('data/pages.json.gz');
      if (!pagesResp.ok) throw new Error('Не удалось загрузить pages.json.gz');
      const pagesBuf = await pagesResp.arrayBuffer();
      const decompressed = await decompressGzip(pagesBuf);
      pages = JSON.parse(new TextDecoder().decode(decompressed));
    }

    // Загружаем переводы для языка, если ещё не загружены
    if (!translations[lang]) {
      const transResp = await fetch(`locales/${lang}.json.gz`);
      if (!transResp.ok) throw new Error(`Не удалось загрузить ${lang}.json.gz`);
      const transBuf = await transResp.arrayBuffer();
      const decompressed = await decompressGzip(transBuf);
      translations[lang] = JSON.parse(new TextDecoder().decode(decompressed));
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

  const transData = translations[currentLang][pageNum - 1];
  
  container.innerHTML = '';
  const pageDiv = document.createElement('div');
  pageDiv.className = 'page';
  pageDiv.style.width = pageData.width + 'px';
  pageDiv.style.height = pageData.height + 'px';

  pageData.elements.forEach(el => {
    if (el.type === 'text') {
      const span = document.createElement('span');
      span.className = 'text-element';
      span.style.left = el.x + 'px';
      span.style.top = el.y + 'px';
      span.style.fontFamily = el.font;
      span.style.fontSize = el.size + 'px';
      span.style.fontWeight = el.bold ? 'bold' : 'normal';
      span.style.fontStyle = el.italic ? 'italic' : 'normal';
      span.style.color = el.color || '#000';
      span.style.width = el.w + 'px';
      span.style.height = el.h + 'px';
      span.textContent = transData[el.textIdx] || '';
      pageDiv.appendChild(span);
    } else if (el.type === 'image') {
      const img = document.createElement('img');
      img.src = 'data/' + el.src;  // путь относительно корня, к data/images/...
      img.style.position = 'absolute';
      img.style.left = el.x + 'px';
      img.style.top = el.y + 'px';
      img.style.width = el.w + 'px';
      img.style.height = el.h + 'px';
      pageDiv.appendChild(img);
    } else if (el.type === 'svg') {
      const svgWrapper = document.createElement('div');
      svgWrapper.innerHTML = el.svg;
      const svg = svgWrapper.firstChild;
      svg.style.position = 'absolute';
      svg.style.left = el.x + 'px';
      svg.style.top = el.y + 'px';
      svg.style.width = el.w + 'px';
      svg.style.height = el.h + 'px';
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
(async () => {
  await loadData('ru');
})();
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
      pages = await loadBrotliJson('data/pages.json.br');
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
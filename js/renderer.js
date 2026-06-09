let pages = [];
let svgs = [];
let pageSizes = [];
let currentPage = 1;

const container = document.getElementById('page-container');
const pageIndicator = document.getElementById('pageIndicator');
const btnPrev = document.getElementById('btnPrev');
const btnNext = document.getElementById('btnNext');
const pageInput = document.getElementById('pageInput');
const btnGo = document.getElementById('btnGo');

async function loadBrotliJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Не удалось загрузить ${path} (HTTP ${response.status})`);
  if (response.headers.get('content-encoding') !== 'br') {
    throw new Error(`${path} отдан без Content-Encoding: br. Запустите: python server.py`);
  }
  return response.json();
}

async function loadData() {
  try {
    const [version, loadedSvgs, loadedPageSizes, loadedPages] = await loadBrotliJson('data/pages.json.br');
    if (version !== 2) throw new Error(`Неподдерживаемая версия pages.json.br: ${version}`);
    svgs = loadedSvgs;
    pageSizes = loadedPageSizes;
    pages = loadedPages;
    renderPage(currentPage);
  } catch (error) {
    container.innerHTML = `<p class="error">Ошибка загрузки: ${error.message}</p>`;
    console.error(error);
  }
}

function renderPage(pageNum) {
  const pageData = pages[pageNum - 1];
  if (!pageData) return;
  const [pageSizeIdx, svgIdx] = pageData;
  const [pageWidth, pageHeight] = pageSizes[pageSizeIdx];
  container.innerHTML = svgs[svgIdx];
  const svg = container.firstElementChild;
  svg.style.aspectRatio = `${pageWidth} / ${pageHeight}`;
  svg.dataset.page = pageNum;
  updateControls(pageNum);
}

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
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

btnPrev.addEventListener('click', () => goToPage(currentPage - 1));
btnNext.addEventListener('click', () => goToPage(currentPage + 1));
btnGo.addEventListener('click', () => goToPage(Number.parseInt(pageInput.value, 10)));
pageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') goToPage(Number.parseInt(pageInput.value, 10));
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowLeft') goToPage(currentPage - 1);
  if (event.key === 'ArrowRight') goToPage(currentPage + 1);
});

if (window.location.protocol === 'file:') {
  container.innerHTML = '<p class="error">Открытие через file:// не поддерживается. Запустите: python server.py</p>';
} else {
  loadData();
}

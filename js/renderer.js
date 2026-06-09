let pages = [];
let texts = [];
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
    const [layoutData, textData] = await Promise.all([
      loadBrotliJson('data/pages/index.json.br'),
      loadBrotliJson('data/locales/source.json.br'),
    ]);
    if (layoutData[0] !== 2 || !Array.isArray(layoutData[1]) || textData[0] !== 2 || !Array.isArray(textData[2])) {
      throw new Error('Неподдерживаемый формат данных документа');
    }
    pages = layoutData[1];
    texts = textData[2];
    renderPage(currentPage);
  } catch (error) {
    container.innerHTML = `<p class="error">Ошибка загрузки: ${error.message}</p>`;
    console.error(error);
  }
}

function renderPage(pageNum) {
  const page = pages[pageNum - 1];
  const pageTexts = texts[pageNum - 1];
  if (!page || !pageTexts) return;

  const [width, height, textStyles, illustrations] = page;
  const sheet = document.createElement('article');
  sheet.className = 'page';
  sheet.style.aspectRatio = `${width} / ${height}`;

  illustrations.forEach(([path, x, y, imageWidth, imageHeight]) => {
    const image = new Image();
    image.src = `data/${path}`;
    image.alt = '';
    positionElement(image, x, y, imageWidth, imageHeight, width, height);
    sheet.append(image);
  });

  textStyles.forEach(([x, y, textWidth, textHeight, font, size, color, flags], index) => {
    const span = document.createElement('span');
    span.className = 'text-span';
    span.textContent = pageTexts[index];
    span.style.left = `${x / width * 100}%`;
    span.style.top = `${y / height * 100}%`;
    span.style.width = `${textWidth / width * 100}%`;
    span.style.height = `${textHeight / height * 100}%`;
    span.style.fontFamily = `"${font}", sans-serif`;
    span.style.fontSize = `${size / width * 100}cqw`;
    span.style.color = `#${color.toString(16).padStart(6, '0')}`;
    span.style.fontWeight = flags & 16 ? 'bold' : 'normal';
    span.style.fontStyle = flags & 2 ? 'italic' : 'normal';
    sheet.append(span);
  });

  container.replaceChildren(sheet);
  updateControls(pageNum);
}

function positionElement(element, x, y, width, height, pageWidth, pageHeight) {
  element.className = 'page-image';
  element.style.left = `${x / pageWidth * 100}%`;
  element.style.top = `${y / pageHeight * 100}%`;
  element.style.width = `${width / pageWidth * 100}%`;
  element.style.height = `${height / pageHeight * 100}%`;
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

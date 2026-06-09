(() => {
  'use strict';

  let pages = [];
  let wordsDict = [];
  let currentPage = 0;
  let zoom = Number(localStorage.getItem('wordSelectV24Zoom') || '0');

  let selectedWords = [];
  let dragState = null;
  let currentVisualWords = [];
  let currentVisualLines = [];

  const $ = (id) => document.getElementById(id);
  const pageContainer = $('page-container');
  const pageIndicator = $('pageIndicator');
  const pageInput = $('pageInput');
  const zoomLabel = $('zoomLabel');
  const toggleBoxes = $('toggleBoxes');
  const selectionInfo = $('selectionInfo');

  function assetUrl(src) {
    if (!src) return '';
    if (/^(https?:|data:|blob:|\/)/i.test(src)) return src;
    if (src.startsWith('data/')) return src;
    return `data/${src}`;
  }

  async function loadJson(url) {
    const response = await fetch(`${url}?v=${Date.now()}`);
    if (!response.ok) throw new Error(`Не удалось загрузить ${url}: HTTP ${response.status}`);
    return response.json();
  }

  function decodeWords(page) {
    const result = [];
    let prevX = 0;
    let prevY = 0;
    let sourceIndex = 0;

    for (const item of page.words || []) {
      const [wi, dx, dy, w, h, conf] = item;
      const x = prevX + dx;
      const y = prevY + dy;
      result.push({
        sourceIndex,
        visualIndex: -1,
        lineId: -1,
        t: wordsDict[wi] || '',
        x, y, w, h,
        c: conf,
      });
      prevX = x;
      prevY = y;
      sourceIndex += 1;
    }

    return assignVisualOrder(result);
  }

  function buildVisualLines(words) {
    const sorted = [...words].sort((a, b) => (a.y + a.h / 2) - (b.y + b.h / 2) || a.x - b.x);
    const lines = [];

    for (const word of sorted) {
      const cy = word.y + word.h / 2;
      let best = null;
      let bestScore = Infinity;

      for (const line of lines) {
        const lineTop = line.y;
        const lineBottom = line.y + line.h;
        const overlap = Math.max(0, Math.min(word.y + word.h, lineBottom) - Math.max(word.y, lineTop));
        const minH = Math.min(word.h, line.h);
        const dist = Math.abs(cy - line.cy);

        // Words of one line may have different top/bottom due to OCR. Use overlap/center.
        const sameLine = overlap >= minH * 0.25 || dist <= Math.max(8, minH * 0.95);
        if (sameLine && dist < bestScore) {
          best = line;
          bestScore = dist;
        }
      }

      if (!best) {
        lines.push({
          id: lines.length,
          y: word.y,
          h: word.h,
          cy,
          x0: word.x,
          x1: word.x + word.w,
          words: [word],
        });
      } else {
        best.words.push(word);
        best.y = Math.min(...best.words.map((w) => w.y));
        best.h = Math.max(...best.words.map((w) => w.y + w.h)) - best.y;
        best.cy = best.words.reduce((sum, w) => sum + w.y + w.h / 2, 0) / best.words.length;
        best.x0 = Math.min(...best.words.map((w) => w.x));
        best.x1 = Math.max(...best.words.map((w) => w.x + w.w));
      }
    }

    lines.sort((a, b) => a.cy - b.cy || a.x0 - b.x0);

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      line.id = i;
      line.words.sort((a, b) => a.x - b.x || a.sourceIndex - b.sourceIndex);
      line.firstX = line.words[0]?.x ?? 0;
      line.lastX = line.words.at(-1)?.x + line.words.at(-1)?.w || 0;
    }

    return lines;
  }

  function assignVisualOrder(words) {
    const lines = buildVisualLines(words);
    let visualIndex = 0;

    for (const line of lines) {
      line.firstVisual = visualIndex;

      for (const word of line.words) {
        word.lineId = line.id;
        word.visualIndex = visualIndex;
        visualIndex += 1;
      }

      line.lastVisual = visualIndex - 1;
    }

    currentVisualLines = lines;
    currentVisualWords = [...words].sort((a, b) => a.visualIndex - b.visualIndex);
    return words;
  }

  function effectiveScale() {
    const page = pages[currentPage];
    if (!page || !pageContainer) return 1;
    if (zoom > 0) return zoom;
    const availableW = Math.max(320, pageContainer.clientWidth - 32);
    return Math.min(1, availableW / Math.max(1, Number(page.w || 1)));
  }

  function updateControls(scale) {
    const total = pages.length;
    const pageNo = total ? currentPage + 1 : 0;
    pageIndicator.textContent = `Страница ${pageNo} из ${total}`;
    pageInput.min = '1';
    pageInput.max = String(Math.max(1, total));
    pageInput.value = String(Math.max(1, pageNo));
    zoomLabel.textContent = zoom === 0 ? `fit ${Math.round(scale * 100)}%` : `${Math.round(scale * 100)}%`;
    updateSelectionInfo();
  }

  function updateSelectionInfo() {
    if (!selectionInfo) return;
    if (!selectedWords.length) {
      selectionInfo.textContent = 'v24: visualIndex = строки сверху вниз, слова слева направо';
      return;
    }
    selectionInfo.textContent = `Выбрано слов: ${selectedWords.length}. Ctrl+C копирует текст`;
  }

  function pagePointFromEvent(event, pageNode) {
    const rect = pageNode.getBoundingClientRect();
    const scale = effectiveScale();
    return {
      x: (event.clientX - rect.left) / scale,
      y: (event.clientY - rect.top) / scale,
    };
  }

  function wordFromNode(node) {
    if (!node || !node.classList || !node.classList.contains('word-box')) return null;
    return {
      sourceIndex: Number(node.dataset.sourceIndex),
      visualIndex: Number(node.dataset.visualIndex),
      lineId: Number(node.dataset.lineId),
      t: node.dataset.text || '',
      x: Number(node.dataset.x),
      y: Number(node.dataset.y),
      w: Number(node.dataset.w),
      h: Number(node.dataset.h),
    };
  }

  function clearSelection() {
    selectedWords = [];
    document.querySelectorAll('.word-box.selected').forEach((node) => node.classList.remove('selected'));
    updateSelectionInfo();
  }

  function lineFromPoint(point) {
    if (!currentVisualLines.length) return null;

    for (const line of currentVisualLines) {
      const topBand = line.y - Math.max(5, line.h * 0.45);
      const bottomBand = line.y + line.h + Math.max(5, line.h * 0.45);
      if (point.y >= topBand && point.y <= bottomBand) {
        return line;
      }
    }

    const above = currentVisualLines.filter((line) => point.y >= line.y + line.h);
    if (above.length) return above.at(-1);

    return currentVisualLines[0];
  }

  function caretVisualIndexFromPoint(point) {
    const line = lineFromPoint(point);
    if (!line) return null;

    const words = line.words;

    // Cursor left of first word means "before this line":
    // do not include first word unless the actual drag reaches it.
    if (point.x < words[0].x) {
      const previousWord = currentVisualWords.find((w) => w.visualIndex === line.firstVisual - 1);
      return previousWord ? previousWord.visualIndex : line.firstVisual;
    }

    let focus = words[0];

    for (const word of words) {
      // If cursor is inside word, select it.
      if (point.x >= word.x && point.x <= word.x + word.w) {
        focus = word;
        break;
      }

      // If cursor moved past the middle/right part of word, include it.
      if (point.x >= word.x + word.w * 0.50) {
        focus = word;
      }

      // If cursor is before the next word, keep previous focus.
      if (point.x < word.x) {
        break;
      }
    }

    return focus.visualIndex;
  }

  function wordNodeByVisualIndex(visualIndex) {
    return document.querySelector(`.word-box[data-visual-index="${visualIndex}"]`);
  }

  function expandToLineStarts(selectedSet) {
    // User rule:
    // If any word in a line is selected, select all words to its left too.
    // Implementation: for every touched line, include from line start to
    // the rightmost selected word in that line.
    for (const line of currentVisualLines) {
      const selectedInLine = line.words.filter((w) => selectedSet.has(w.visualIndex));
      if (!selectedInLine.length) continue;

      const rightmostVisual = Math.max(...selectedInLine.map((w) => w.visualIndex));
      for (const word of line.words) {
        if (word.visualIndex <= rightmostVisual) {
          selectedSet.add(word.visualIndex);
        }
      }
    }

    return selectedSet;
  }

  function applyRangeSelection(anchorVisual, focusVisual, { append = false } = {}) {
    if (!Number.isFinite(anchorVisual) || !Number.isFinite(focusVisual)) return;

    if (!append) {
      selectedWords = [];
      document.querySelectorAll('.word-box.selected').forEach((node) => node.classList.remove('selected'));
    }

    const from = Math.min(anchorVisual, focusVisual);
    const to = Math.max(anchorVisual, focusVisual);

    let selectedSet = new Set(selectedWords.map((w) => w.visualIndex));

    for (let i = from; i <= to; i += 1) {
      selectedSet.add(i);
    }

    selectedSet = expandToLineStarts(selectedSet);

    const selected = [];

    document.querySelectorAll('.word-box').forEach((node) => {
      const word = wordFromNode(node);
      if (!word) return;

      if (selectedSet.has(word.visualIndex)) {
        node.classList.add('selected');
        selected.push(word);
      } else if (!append) {
        node.classList.remove('selected');
      }
    });

    selectedWords = selected.sort((a, b) => a.visualIndex - b.visualIndex);
    updateSelectionInfo();
  }

  function selectedText() {
    if (!selectedWords.length) return '';

    const words = [...selectedWords].sort((a, b) => a.visualIndex - b.visualIndex);
    const lines = [];
    let currentLineId = null;
    let current = [];

    for (const word of words) {
      if (currentLineId === null) {
        currentLineId = word.lineId;
        current.push(word);
        continue;
      }

      if (word.lineId !== currentLineId) {
        lines.push(current.map((w) => w.t).join(' '));
        current = [word];
        currentLineId = word.lineId;
      } else {
        current.push(word);
      }
    }

    if (current.length) lines.push(current.map((w) => w.t).join(' '));
    return lines.join('\n');
  }

  function setupSelection(pageNode) {
    pageNode.addEventListener('mousedown', (event) => {
      if (event.button !== 0) return;
      event.preventDefault();

      const startPoint = pagePointFromEvent(event, pageNode);
      const anchorVisual = caretVisualIndexFromPoint(startPoint);
      if (anchorVisual === null) return;

      dragState = {
        anchorVisual,
        focusVisual: anchorVisual,
        append: event.ctrlKey || event.metaKey || event.shiftKey,
      };

      applyRangeSelection(dragState.anchorVisual, dragState.focusVisual, { append: dragState.append });

      const onMove = (moveEvent) => {
        if (!dragState) return;
        const point = pagePointFromEvent(moveEvent, pageNode);
        const focusVisual = caretVisualIndexFromPoint(point);
        if (focusVisual === null) return;

        dragState.focusVisual = focusVisual;
        applyRangeSelection(dragState.anchorVisual, dragState.focusVisual, { append: dragState.append });
      };

      const onUp = () => {
        dragState = null;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
  }

  function renderPage(pageIndex) {
    pageContainer.innerHTML = '';
    selectedWords = [];
    currentPage = Math.max(0, Math.min(pageIndex, pages.length - 1));

    const page = pages[currentPage];
    const words = decodeWords(page);
    const scale = effectiveScale();

    const wrapper = document.createElement('div');
    wrapper.className = 'page-scale-wrapper';
    wrapper.style.width = `${page.w * scale}px`;
    wrapper.style.height = `${page.h * scale}px`;

    const pageNode = document.createElement('div');
    pageNode.className = 'page';
    pageNode.style.width = `${page.w}px`;
    pageNode.style.height = `${page.h}px`;
    pageNode.style.transform = `scale(${scale})`;
    pageNode.style.transformOrigin = 'top left';

    const img = document.createElement('img');
    img.className = 'page-image';
    img.src = assetUrl(page.img);
    img.alt = '';
    img.style.left = '0px';
    img.style.top = '0px';
    img.style.width = `${page.w}px`;
    img.style.height = `${page.h}px`;
    pageNode.appendChild(img);

    const wordLayer = document.createElement('div');
    wordLayer.className = 'word-layer';
    if (!toggleBoxes.checked) wordLayer.classList.add('hide-boxes');

    for (const word of words) {
      const span = document.createElement('span');
      span.className = 'word-box selectable-word';
      span.textContent = word.t;

      span.dataset.sourceIndex = String(word.sourceIndex);
      span.dataset.visualIndex = String(word.visualIndex);
      span.dataset.lineId = String(word.lineId);
      span.dataset.text = word.t;
      span.dataset.x = String(word.x);
      span.dataset.y = String(word.y);
      span.dataset.w = String(word.w);
      span.dataset.h = String(word.h);

      span.title = `${word.t}\nvisualIndex=${word.visualIndex}\nline=${word.lineId}\nsourceIndex=${word.sourceIndex}\nconf=${word.c}\nx=${word.x} y=${word.y} w=${word.w} h=${word.h}`;
      span.style.left = `${word.x}px`;
      span.style.top = `${word.y}px`;
      span.style.width = `${Math.max(1, word.w)}px`;
      span.style.height = `${Math.max(1, word.h)}px`;
      span.style.fontSize = `${Math.max(6, word.h)}px`;
      span.style.lineHeight = `${Math.max(6, word.h)}px`;

      wordLayer.appendChild(span);
    }

    pageNode.appendChild(wordLayer);
    setupSelection(pageNode);

    wrapper.appendChild(pageNode);
    pageContainer.appendChild(wrapper);
    updateControls(scale);
  }

  function goToPage(value) {
    const n = Math.max(1, Math.min(Number(value || 1), pages.length));
    renderPage(n - 1);
  }

  async function main() {
    const doc = await loadJson('data/pages.word_select_v24.delta.json');
    pages = doc.p || [];
    wordsDict = doc.d?.words || [];
    renderPage(0);
  }

  document.addEventListener('copy', (event) => {
    if (!selectedWords.length) return;
    event.preventDefault();
    event.clipboardData.setData('text/plain', selectedText());
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') clearSelection();
  });

  $('btnClearSelection').addEventListener('click', clearSelection);
  $('btnPrev').addEventListener('click', () => goToPage(currentPage));
  $('btnNext').addEventListener('click', () => goToPage(currentPage + 2));
  $('btnGo').addEventListener('click', () => goToPage(pageInput.value || 1));
  pageInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') goToPage(pageInput.value || 1);
  });
  $('btnFit').addEventListener('click', () => {
    zoom = 0;
    localStorage.setItem('wordSelectV24Zoom', String(zoom));
    renderPage(currentPage);
  });
  $('btnMinus').addEventListener('click', () => {
    zoom = Math.max(0.1, Math.round((effectiveScale() - 0.1) * 100) / 100);
    localStorage.setItem('wordSelectV24Zoom', String(zoom));
    renderPage(currentPage);
  });
  $('btnPlus').addEventListener('click', () => {
    zoom = Math.min(3, Math.round((effectiveScale() + 0.1) * 100) / 100);
    localStorage.setItem('wordSelectV24Zoom', String(zoom));
    renderPage(currentPage);
  });
  toggleBoxes.addEventListener('change', () => renderPage(currentPage));

  window.addEventListener('resize', () => {
    if (zoom === 0) renderPage(currentPage);
  });

  document.addEventListener('DOMContentLoaded', () => {
    main().catch((error) => {
      pageContainer.innerHTML = `<pre class="error">${String(error.stack || error.message || error)}</pre>`;
    });
  });
})();

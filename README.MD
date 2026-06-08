# PDF_to_HTML

Интерактивный HTML-просмотрщик документов с точным позиционированием элементов и многоязычными переводами.

## Запуск

`index.html` нельзя открывать двойным щелчком через `file://`: браузеры запрещают такой странице загружать данные через `fetch`. Запустите HTTP-сервер проекта, который правильно отдаёт готовые Brotli-файлы:

```bash
python server.py
```

Затем откройте <http://127.0.0.1:8000/index.html>.

Сервер добавляет к `*.json.br` обязательные заголовки:

```text
Content-Type: application/json; charset=utf-8
Content-Encoding: br
Vary: Accept-Encoding
```

Браузер автоматически распаковывает ответ. JavaScript не использует несжатые JSON, gzip или fallback на них.

## Генерация данных

Установите зависимости и запустите генератор:

```bash
python -m pip install -r requirements.txt
python generate.py
```

Генератор создаёт только готовые Brotli-файлы с quality 11:

- `data/pages.json.br` — геометрия и элементы всех страниц;
- `locales/ru.json.br` — русские переводы;
- `locales/en.json.br` — английские переводы;
- `data/images/*.avif` — изображения страниц.

Перед генерацией каталоги `data/` и `locales/` пересоздаются, поэтому старые несжатые JSON и gzip-файлы не сохраняются.

## Настройка production-сервера

Для любого сервера/CDN файлы `*.json.br` должны отдаваться без дополнительного сжатия и с `Content-Encoding: br`. Пример для Nginx:

```nginx
location ~ \.json\.br$ {
    default_type application/json;
    add_header Content-Encoding br always;
    add_header Vary Accept-Encoding always;
}
```

После настройки проверьте заголовки:

```bash
curl -I http://127.0.0.1:8000/data/pages.json.br
```

## Формат данных

`pages.json.br` после автоматической распаковки браузером содержит массив страниц. Текстовые элементы ссылаются на перевод через `textIdx`. Файл каждого языка содержит массив массивов строк, поэтому перевод выбирается как `translations[pageNumber - 1][textIdx]`.

Все страницы загружаются один раз. При смене языка загружается только соответствующий Brotli-файл переводов, если его ещё нет в памяти.

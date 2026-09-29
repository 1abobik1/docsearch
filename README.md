# docsearch

Сервис полнотекстового поиска по документам.

**Стек:** Python 3.13, FastAPI, PostgreSQL (SQLAlchemy async + asyncpg, Alembic), Elasticsearch 9, Docker.

## Запуск

Требуются Docker и Docker Compose.

```bash
docker compose up -d --build --wait
```

При первом запуске применяются миграции, загружается `data/posts.csv` и строится поисковый индекс.

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- OpenAPI-спецификация: [`docs.json`](docs.json)

Остановка с удалением данных: `docker compose down -v`.

## API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/v1/documents/search?query=<текст>` | Поиск: до 20 документов со всеми полями, отсортированные по дате создания (новые первыми) |
| `DELETE` | `/api/v1/documents/{id}` | Удаление документа из БД и индекса |
| `GET` | `/health/live`, `/health/ready` | Проверки работоспособности |

Примеры:

```bash
curl -G http://localhost:8000/api/v1/documents/search --data-urlencode "query=конкурс"
curl -X DELETE http://localhost:8000/api/v1/documents/1
```

Коды ответов: `404` — документ не найден, `422` — некорректный запрос, `503` — поисковый движок недоступен.

## Особенности реализации

- Elasticsearch выбирает 20 наиболее релевантных документов, PostgreSQL возвращает их со всеми полями, отсортированными по дате.
- Удаление выполняется в транзакции БД, коммит происходит только после успешного удаления из индекса.
- Анализатор индекса учитывает русскую и английскую морфологию.
- Индекс можно пересобрать без простоя: `docker compose exec app python -m app.cli reindex`.

## Тесты

```bash
docker compose --profile test run --rm --build tests
```

Функциональные тесты выполняются на реальных PostgreSQL и Elasticsearch с отдельной тестовой БД и отдельным индексом.

## Локальная разработка

```bash
uv sync
docker compose up -d postgres elasticsearch
uv run alembic upgrade head
uv run python -m app.cli seed data/posts.csv
uv run uvicorn app.main:create_app --factory --reload
```

Все команды: `make help`.

# Recommendation System

Content-based рекомендательная система на Python с использованием sentence embeddings для персонализированных рекомендаций постов.

## Возможности

- 🤖 **Content-based filtering** через sentence transformers
- 📊 **Персональные рекомендации** на основе реакций пользователя
- 💾 **PostgreSQL** для хранения данных
- ⚡ **Redis** для быстрого кеширования
- 🚀 **FastAPI** REST API

## Как работает

1. Посты хранятся с **text embeddings** (векторное представление текста)
2. Когда пользователь лайкает/дизлайкает посты → вычисляется **preference embedding**
3. Рекомендации = посты с **максимальной cosine similarity** к предпочтениям пользователя
4. Результат кешируется в Redis

## Технологии

- **Python 3.10+**
- **FastAPI** - Web framework
- **Sentence Transformers** - Text embeddings (all-MiniLM-L6-v2)
- **PostgreSQL** - База данных
- **Redis** - Кеширование
- **SQLAlchemy** - ORM

## Установка и запуск

### 1. Создать виртуальное окружение

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

Первый запуск скачает модель Sentence Transformer (~80MB).

### 3. Запустить PostgreSQL и Redis

```bash
docker-compose up -d
```

Это запустит:
- PostgreSQL на порту 5432
- Redis на порту 6379

### 4. Инициализировать БД с тестовыми данными

```bash
python seed_data.py
```

Это создаст:
- 12 постов на разные темы (AI, природа, кулинария)
- 9 реакций от пользователя `user123`
- Embeddings для всех постов

### 5. Запустить сервис

```bash
python -m app.main
```

Сервис будет доступен на **http://localhost:8001**

### 6. Тестирование

```bash
python test_api.py
```

Или открой в браузере:
```
http://localhost:8001/docs
```

## API Endpoints

### Получить рекомендации

```http
POST /recommendations/
Content-Type: application/json

{
  "userId": "user123",
  "limit": 10,
  "excludeAuthorPosts": true
}
```

**Ответ:**
```json
{
  "userId": "user123",
  "recommendations": [
    {
      "id": 1,
      "authorId": "alice",
      "text": "Post about AI...",
      "createdAt": "2024-01-15T10:00:00Z",
      "likesCount": 42,
      "dislikesCount": 2
    }
  ],
  "totalCount": 10
}
```

### Создать пост

```http
POST /recommendations/posts
Content-Type: application/json

{
  "id": 100,
  "authorId": "user456",
  "text": "My new post about machine learning",
  "createdAt": "2024-01-15T10:00:00Z"
}
```

### Создать реакцию

```http
POST /recommendations/reactions
Content-Type: application/json

{
  "id": 200,
  "targetType": "POST",
  "targetId": 1,
  "authorId": "user123",
  "type": "LIKE",
  "createdAt": "2024-01-15T10:00:00Z"
}
```

### Обновить рекомендации

```http
POST /recommendations/refresh/{userId}
```

## Структура проекта

```
recommendation-system/
├── app/
│   ├── api/                  # API endpoints
│   ├── database/             # Database models
│   ├── ml/                   # ML models (embeddings, recommender)
│   ├── models/               # Pydantic models
│   ├── services/             # Business logic
│   └── main.py               # FastAPI приложение
├── config.py                 # Конфигурация
├── requirements.txt          # Зависимости
├── docker-compose.yml        # PostgreSQL + Redis
├── seed_data.py              # Создание тестовых данных
└── test_api.py               # Тесты API
```

## Алгоритм рекомендаций

```python
# 1. Вычисление предпочтений пользователя
preference_embedding = (
    Σ liked_embeddings × like_weight - 
    Σ disliked_embeddings × dislike_weight
)

# 2. Расчет похожести
for post in all_posts:
    similarity = cosine_similarity(preference_embedding, post.embedding)

# 3. Возврат top-N
return posts.sort_by(similarity).top(N)
```

## Конфигурация

В `config.py` или `.env`:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `PORT` | Порт API | 8001 |
| `POSTGRES_HOST` | PostgreSQL хост | localhost |
| `REDIS_HOST` | Redis хост | localhost |
| `MODEL_NAME` | Sentence transformer модель | all-MiniLM-L6-v2 |
| `TOP_N_RECOMMENDATIONS` | Количество рекомендаций | 10 |
| `CACHE_TTL` | Время жизни кеша (сек) | 3600 |

## База данных

PostgreSQL схема:

### Таблица posts
- `id` - ID поста
- `author_id` - ID автора
- `text` - Текст поста
- `embedding` - Вектор (384 dimensions)
- `likes_count`, `dislikes_count`, `comments_count`

### Таблица reactions
- `id` - ID реакции
- `target_type` - POST или COMMENT
- `target_id` - ID поста/комментария
- `author_id` - ID пользователя
- `type` - LIKE или DISLIKE

### Таблица user_preferences
- `user_id` - ID пользователя
- `preference_embedding` - Вектор предпочтений
- `updated_at` - Время обновления

## Интеграция с Java Backend

Из Java вызывай REST API:

```java
// Получить рекомендации
RestTemplate restTemplate = new RestTemplate();
String url = "http://localhost:8001/recommendations/";

Map<String, Object> request = Map.of(
    "userId", userId,
    "limit", 10
);

ResponseEntity<RecommendationResponse> response = 
    restTemplate.postForEntity(url, request, RecommendationResponse.class);
```

```java
// Создать пост после сохранения в Pastach
PostCreate post = PostCreate.builder()
    .id(savedPost.getId())
    .authorId(savedPost.getAuthorId())
    .text(savedPost.getText())
    .createdAt(savedPost.getCreatedAt())
    .build();

restTemplate.postForEntity(
    "http://localhost:8001/recommendations/posts",
    post,
    PostResponse.class
);
```

## Производительность

- **Генерация embedding**: ~10ms на пост (CPU)
- **Запрос рекомендаций**: ~50-100ms (без кеша)
- **С кешем в Redis**: <5ms

## Следующие шаги

- [ ] Добавить Kafka для real-time интеграции
- [ ] Коллаборативную фильтрацию
- [ ] Метрики и мониторинг
- [ ] UI для отображения рекомендаций

## Тестовые данные

После `seed_data.py` user123 имеет следующие предпочтения:
- ✅ Лайки: посты про AI, data science, природу
- ❌ Дизлайки: посты про кулинарию

Попробуй получить рекомендации:
```bash
curl -X POST "http://localhost:8001/recommendations/" \
  -H "Content-Type: application/json" \
  -d '{"userId": "user123", "limit": 5}'
```

Система должна рекомендовать другие посты про технологии и природу!

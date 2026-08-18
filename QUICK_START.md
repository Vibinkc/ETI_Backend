# Quick Start Guide

## 1. Create .env File

Create a `.env` file in `eti_backend` directory:

```env
# Database (PostgreSQL)
DB_NAME=myapp
DB_USER=admin
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5433

# Redis (for Celery - optional for basic AI features)
REDIS_PASSWORD=hOW32#$@41u31Aq4
REDIS_PORT=6379

# OpenAI (REQUIRED for AI queries)
OPENAI_API_KEY=sk-your-actual-api-key-here
```

## 2. Start Services

### Option A: Minimal Setup (AI works, but synchronous processing)

```bash
# Start only PostgreSQL
docker-compose up -d postgres

# Start FastAPI
uvicorn app.main:app --reload
```

**✅ AI document upload and query will work!**
- Documents process synchronously (may take time for large files)
- No background processing

### Option B: Full Setup (Recommended for production)

```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Terminal 1: Start FastAPI
uvicorn app.main:app --reload

# Terminal 2: Start Celery Worker (for background processing)
celery -A app.core.celery.celery_app worker --loglevel=info

# Terminal 3: Start Celery Beat (for scheduled tasks - optional)
celery -A app.core.celery.celery_app beat --loglevel=info
```

## Why Redis and Celery?

### Redis
- **Message Queue**: Celery uses Redis to manage background tasks
- **Caching**: Stores frequently accessed data for faster responses

### Celery
- **Background Processing**: Process large documents without blocking the API
- **Better UX**: Users get immediate response, processing happens in background
- **Scheduled Tasks**: Run periodic jobs automatically

## Do You Need Them?

### For Basic AI Features: **NO**
- You can upload documents and query them without Redis/Celery
- Processing happens synchronously (user waits for completion)

### For Production: **YES**
- Better performance
- Non-blocking document processing
- Scalable architecture

## Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Create a new API key
4. Copy and paste into `.env` file

## Test It Works

1. Start FastAPI: `uvicorn app.main:app --reload`
2. Open browser: http://localhost:8000/api/docs
3. Try the `/api/documents/upload` endpoint
4. Upload a PDF or Word document
5. Query it using `/api/documents/query`


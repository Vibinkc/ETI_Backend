# Environment Variables Setup Guide

## .env File Configuration

Create a `.env` file in the `eti_backend` directory with the following variables:

```env
# Application Settings
DEBUG=false
APP_ENV=development

# Database Configuration (PostgreSQL)
DB_NAME=myapp
DB_USER=admin
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5433

# Redis Configuration (for Celery and caching)
REDIS_PASSWORD=hOW32#$@41u31Aq4
REDIS_PORT=6379

# OpenAI API Key (for AI document training)
OPENAI_API_KEY=your_openai_api_key_here
```

## Why Redis and Celery are Needed

### Redis
Redis is used for two main purposes:

1. **Celery Message Broker**: 
   - Celery uses Redis to queue and distribute background tasks
   - When you upload a document, it can be processed asynchronously
   - Tasks are stored in Redis queues before being picked up by Celery workers

2. **Caching Layer**:
   - The application uses Redis for caching frequently accessed data
   - Improves performance by reducing database queries

### Celery
Celery is used for:

1. **Background Task Processing**:
   - Document processing (text extraction, chunking, embedding generation) can be time-consuming
   - Celery allows these tasks to run in the background without blocking the API
   - Users get immediate response while processing happens asynchronously

2. **Scheduled Tasks**:
   - Periodic tasks (like syncing data, cleanup jobs, etc.)
   - Can run on a schedule without manual intervention

## Setup Steps

### 1. Start PostgreSQL and Redis using Docker

```bash
cd eti_backend
docker-compose up -d
```

This will start:
- PostgreSQL on port 5433
- Redis on port 6379

### 2. Create .env File

Copy the example and update with your values:

```bash
cp .env.example .env
```

Then edit `.env` and set:
- Database credentials (match docker-compose.yml)
- Redis password (match docker-compose.yml)
- OpenAI API key (get from https://platform.openai.com/api-keys)

### 3. Start Celery Worker (Optional but Recommended)

For background document processing:

```bash
# In a separate terminal
cd eti_backend
celery -A app.core.celery.celery_app worker --loglevel=info
```

### 4. Start Celery Beat (Optional - for scheduled tasks)

For periodic/scheduled tasks:

```bash
# In another separate terminal
cd eti_backend
celery -A app.core.celery.celery_app beat --loglevel=info
```

### 5. Start FastAPI Server

```bash
cd eti_backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## When Do You Need Redis and Celery?

### **For Basic AI Document Training (Current Implementation):**
- **Redis**: **NOT STRICTLY REQUIRED** - The current implementation processes documents synchronously
- **Celery**: **NOT STRICTLY REQUIRED** - Documents are processed immediately when uploaded

### **For Production/Background Processing:**
- **Redis**: **REQUIRED** - Needed for Celery to work
- **Celery**: **RECOMMENDED** - For better user experience with large documents

## Simplified Setup (Without Celery)

If you want to skip Redis and Celery for now:

1. **You can still use the AI features** - Documents will be processed synchronously
2. **Just set these in .env:**
   ```env
   # Database
   DB_NAME=myapp
   DB_USER=admin
   DB_PASSWORD=password
   DB_HOST=localhost
   DB_PORT=5433
   
   # OpenAI (required for AI queries)
   OPENAI_API_KEY=your_key_here
   ```

3. **Start only PostgreSQL:**
   ```bash
   docker-compose up -d postgres
   ```

4. **Start FastAPI:**
   ```bash
   uvicorn app.main:app --reload
   ```

## Production Setup

For production, you should:
1. ✅ Use Redis for caching
2. ✅ Use Celery for background processing
3. ✅ Use Celery Beat for scheduled tasks
4. ✅ Set proper security (strong passwords, environment-specific configs)

## Troubleshooting

### Redis Connection Error
- Make sure Redis is running: `docker-compose ps`
- Check Redis password matches in `.env` and `docker-compose.yml`
- Verify Redis is accessible: `redis-cli -a hOW32#$@41u31Aq4 ping`

### Celery Not Working
- Make sure Redis is running first
- Check Celery worker logs for errors
- Verify Redis password in `.env` matches `docker-compose.yml`

### Database Connection Error
- Make sure PostgreSQL is running: `docker-compose ps`
- Check database credentials in `.env` match `docker-compose.yml`
- Verify port 5433 is not in use by another service


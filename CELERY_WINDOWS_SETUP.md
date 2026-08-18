# Celery Setup for Windows

## Issues on Windows

1. **Redis Authentication**: Make sure Redis is running with the correct password
2. **Celery Pool**: Windows doesn't support "prefork" pool - use "solo" instead

## Quick Fix

### Option 1: Run Celery with Solo Pool (Recommended for Windows)

```bash
celery -A app.core.celery.celery_app worker --loglevel=info --pool=solo
```

### Option 2: Start Redis Without Password (Simpler for local dev)

If you want to run Redis without password for local development:

1. **Stop current Redis:**
   ```bash
   docker stop redis
   ```

2. **Start Redis without password:**
   ```bash
   docker run -d --name redis -p 6379:6379 redis:alpine
   ```

3. **Update .env file** - remove or comment out REDIS_PASSWORD:
   ```env
   # REDIS_PASSWORD=
   ```

4. **Run Celery:**
   ```bash
   celery -A app.core.celery.celery_app worker --loglevel=info --pool=solo
   ```

### Option 3: Use Docker Redis with Password

1. **Make sure Redis is running:**
   ```bash
   docker-compose up -d redis
   ```

2. **Verify Redis password in .env matches docker-compose.yml:**
   ```env
   REDIS_PASSWORD=hOW32#$@41u31Aq4
   ```

3. **Run Celery with solo pool:**
   ```bash
   celery -A app.core.celery.celery_app worker --loglevel=info --pool=solo
   ```

## Why Solo Pool?

- **prefork**: Uses fork() which doesn't exist on Windows
- **solo**: Single-threaded, works on Windows (good for development)
- **threads**: Multi-threaded, also works on Windows (better for production)

## For Production on Windows

Use threads pool for better performance:

```bash
celery -A app.core.celery.celery_app worker --loglevel=info --pool=threads --concurrency=4
```

## Testing Redis Connection

Test if Redis is accessible:

```bash
# Without password
redis-cli ping

# With password
redis-cli -a hOW32#$@41u31Aq4 ping
```

Should return: `PONG`

## Note

The code has been updated to automatically use "solo" pool on Windows, but you can still override it with the `--pool` flag.


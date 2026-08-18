# Local PostgreSQL Setup Guide

## Your .env File Should Have:

Since you're running PostgreSQL locally on port 5432, update your `.env` file:

```env
# Database Configuration (Local PostgreSQL)
DB_NAME=myapp
DB_USER=admin
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432

# OpenAI (for AI features)
OPENAI_API_KEY=your_openai_api_key_here
```

## Important Steps

### 1. Make sure PostgreSQL is running

Check if PostgreSQL is running:
```bash
# Windows
Get-Service -Name postgresql*

# Or check if port 5432 is in use
netstat -an | findstr 5432
```

### 2. Create the database (if it doesn't exist)

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE myapp;

-- Create user (if needed)
CREATE USER admin WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE myapp TO admin;

-- Connect to the new database
\c myapp

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO admin;
```

### 3. Run database migrations

The document tables need to be created:

```bash
cd eti_backend

# Create migration for document tables
alembic revision --autogenerate -m "add_document_tables"

# Apply migration
alembic upgrade head
```

### 4. Verify connection

Test the connection:
```bash
# Test from command line
psql -h localhost -p 5432 -U admin -d myapp
```

Or test the API:
```bash
curl http://localhost:8000/api/health
```

## Troubleshooting

### "Connection refused" error
- PostgreSQL not running
- Wrong port number
- Firewall blocking connection

### "Database does not exist"
- Create the database (see step 2)
- Check DB_NAME in .env matches the actual database name

### "Authentication failed"
- Check DB_USER and DB_PASSWORD in .env
- Make sure the user exists in PostgreSQL
- Check pg_hba.conf allows local connections

### "Table does not exist"
- Run migrations: `alembic upgrade head`
- Check if migrations were applied: `alembic current`


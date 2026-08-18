# Database Setup for Local PostgreSQL

## If you're running PostgreSQL locally (not Docker)

Update your `.env` file with these settings:

```env
# Database Configuration (Local PostgreSQL)
DB_NAME=myapp
DB_USER=admin
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
```

## Important Notes

- **Port 5432** is the default PostgreSQL port
- **Port 5433** is used when running PostgreSQL in Docker (to avoid conflicts)
- Make sure your local PostgreSQL is running
- Make sure the database `myapp` exists
- Make sure the user `admin` has access to the database

## Create Database (if needed)

If the database doesn't exist, create it:

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE myapp;

-- Create user (if needed)
CREATE USER admin WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE myapp TO admin;
```

## Run Migrations

After setting up the database, run migrations to create tables:

```bash
cd eti_backend
alembic upgrade head
```

This will create:
- `user` table
- `document` table
- `document_chunk` table

## Verify Connection

Test the connection:

```bash
# Test from command line
psql -h localhost -p 5432 -U admin -d myapp
```

Or check the backend health endpoint:
```bash
curl http://localhost:8000/api/health
```


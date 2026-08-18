# Fix Database Credentials Error

## Error: "password authentication failed for user 'user'"

This error means your `.env` file has incorrect database credentials.

## Quick Fix

Open your `.env` file in `eti_backend/` and make sure it has these variables:

```env
# Database Configuration
DB_NAME=eti_bot
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

## Common PostgreSQL Usernames

1. **`postgres`** - Default PostgreSQL superuser (most common)
2. **Your Windows username** - If you created a user with your Windows username
3. **`admin`** - If you created a custom admin user

## How to Find Your PostgreSQL Username

### Option 1: Check PostgreSQL directly
```bash
# Connect to PostgreSQL
psql -U postgres

# Then run:
\du
```

This will show all users. Use one of those usernames.

### Option 2: Try common defaults
Most PostgreSQL installations use:
- Username: `postgres`
- Password: (whatever you set during installation, or empty)

## Example .env Configurations

### If using default postgres user:
```env
DB_NAME=eti_bot
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

### If postgres user has no password:
```env
DB_NAME=eti_bot
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
```

### If using a custom user:
```env
DB_NAME=eti_bot
DB_USER=admin
DB_PASSWORD=password123
DB_HOST=localhost
DB_PORT=5432
```

## Test Your Connection

After updating `.env`, test the connection:

```bash
# Replace with your actual username and password
psql -U postgres -d eti_bot
```

If this works, use those same credentials in your `.env` file.

## Important Notes

1. **DB_NAME** must match an existing database (or create it first)
2. **DB_USER** must be a valid PostgreSQL user
3. **DB_PASSWORD** can be empty if the user has no password
4. **DB_PORT** should be 5432 for local PostgreSQL (not 5433)

## Create Database if Needed

If the database `eti_bot` doesn't exist:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create the database
CREATE DATABASE eti_bot;

# Exit
\q
```

## After Fixing

1. Restart your FastAPI server
2. The error should be resolved
3. Test the API: `GET http://localhost:8000/api/documents`


























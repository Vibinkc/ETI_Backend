# Database Configuration Check

## Error: "password authentication failed for user 'user'"

This means the database is trying to connect with user "user" but that's not the correct username.

## Fix Your .env File

Make sure your `.env` file in `eti_backend/` has the correct database credentials:

```env
# Database Configuration
DB_NAME=eti_bot
DB_USER=your_postgres_username_here
DB_PASSWORD=your_postgres_password_here
DB_HOST=localhost
DB_PORT=5432
```

## Common Issues

### 1. DB_USER is wrong
- Check what PostgreSQL username you're using
- Common usernames: `postgres`, `admin`, or your Windows username
- The error shows it's trying "user" - make sure DB_USER is set correctly

### 2. DB_PASSWORD is wrong
- Make sure the password matches your PostgreSQL user password
- If you don't have a password, leave it empty: `DB_PASSWORD=`

### 3. DB_NAME doesn't exist
- Make sure the database `eti_bot` exists
- Create it if needed: `CREATE DATABASE eti_bot;`

## Quick Test

Test your PostgreSQL connection:

```bash
# Replace with your actual username
psql -U postgres -d eti_bot
# or
psql -U admin -d eti_bot
```

If this works, use that username in your `.env` file.

## Example .env for Local PostgreSQL

```env
# If using default postgres user
DB_NAME=eti_bot
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# If using a custom user
DB_NAME=eti_bot
DB_USER=admin
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
```


























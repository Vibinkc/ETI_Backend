# Super Admin Setup Guide

This guide explains how to set up and use the super admin authentication system.

## Overview

The super admin system provides:
- Secure login with email and password
- JWT token-based authentication
- Protected routes for admin access
- Ability to create additional super admin users

## Backend Setup

### 1. Install Dependencies

The required packages are already in `requirements.txt`:
- `bcrypt` - Password hashing (direct bcrypt library)
- `python-jose[cryptography]` - JWT token handling

Install them:
```bash
cd eti_backend
pip install -r requirements.txt
```

### 2. Set Environment Variables

Add to your `.env` file:
```env
# JWT Secret Key (change this to a secure random string in production)
SECRET_KEY=your-secret-key-change-in-production-use-env-var

# Optional: Customize token expiration (default: 30 days)
ACCESS_TOKEN_EXPIRE_MINUTES=43200
```

**Important:** In production, use a strong, randomly generated secret key:
```python
import secrets
print(secrets.token_urlsafe(32))
```

### 3. Run Database Migration

Add the `is_superuser` column to the user table:
```bash
cd eti_backend
alembic upgrade head
```

### 4. Create First Super Admin

Use the provided script to create your first super admin:
```bash
cd eti_backend
python scripts/create_super_admin.py <email> <password> <first_name> <last_name>
```

Example:
```bash
python scripts/create_super_admin.py admin@example.com SecurePassword123 John Doe
```

**Note:** If a user with that email already exists, the script will update them to super admin status.

## Frontend Setup

The frontend is already configured. The login page is available at:
- `http://localhost:3000/login`

## Usage

### Login

1. Navigate to `http://localhost:3000/login`
2. Enter your super admin email and password
3. You'll be redirected to the dashboard upon successful login

### Creating Additional Super Admins

Once logged in, you can create additional super admins via the API:

```bash
curl -X POST "http://localhost:8000/api/admin/create" \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newadmin@example.com",
    "password": "SecurePassword123",
    "first_name": "Jane",
    "last_name": "Smith"
  }'
```

Or use the script:
```bash
python scripts/create_super_admin.py newadmin@example.com SecurePassword123 Jane Smith
```

### Logout

Click the logout button (power icon) in the header to log out.

## API Endpoints

### POST `/api/admin/login`
Login endpoint for super admin.

**Request:**
```json
{
  "email": "admin@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "admin@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "is_superuser": true
  }
}
```

### POST `/api/admin/create`
Create a new super admin (requires authentication).

**Headers:**
```
Authorization: Bearer <token>
```

**Request:**
```json
{
  "email": "newadmin@example.com",
  "password": "SecurePassword123",
  "first_name": "Jane",
  "last_name": "Smith"
}
```

### GET `/api/admin/me`
Get current authenticated admin information.

**Headers:**
```
Authorization: Bearer <token>
```

## Protected Routes

The following routes are protected and require authentication:
- `/` - Main dashboard
- All dashboard pages

Unauthenticated users are automatically redirected to `/login`.

## Security Notes

1. **Change the SECRET_KEY** in production to a strong, randomly generated value
2. **Use HTTPS** in production to protect tokens in transit
3. **Set appropriate token expiration** times based on your security requirements
4. **Implement rate limiting** on login endpoints to prevent brute force attacks
5. **Use strong passwords** for super admin accounts
6. **Regularly rotate** JWT secret keys in production

## Troubleshooting

### "Could not validate credentials"
- Check that your token is valid and not expired
- Ensure you're sending the token in the Authorization header: `Bearer <token>`

### "Access denied. Super admin privileges required."
- The user account exists but doesn't have `is_superuser=True`
- Run the create script to update the user: `python scripts/create_super_admin.py <email> <password> <first_name> <last_name>`

### Migration errors
- Ensure all previous migrations are applied: `alembic upgrade head`
- Check that the database connection is working: `curl http://localhost:8000/api/health`


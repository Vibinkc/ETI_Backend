# CORS Configuration Fixed

## Problem
Frontend requests were being blocked by CORS (Cross-Origin Resource Sharing) policy because the backend wasn't configured to accept requests from the frontend domain.

## Solution
Added CORS middleware to FastAPI backend in `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js default port
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)
```

## Testing

1. **Start Backend:**
   ```bash
   cd eti_backend
   uvicorn app.main:app --reload
   ```

2. **Start Frontend:**
   ```bash
   cd eti_frontend
   npm run dev
   ```

3. **Check Browser Console:**
   - Open browser DevTools (F12)
   - Go to Network tab
   - Try uploading a document
   - You should see requests to `http://localhost:8000/api/documents/...`
   - Check Console tab for any errors

## Troubleshooting

### Still Getting CORS Errors?

1. **Check backend is running:**
   - Visit http://localhost:8000/api/docs
   - Should see FastAPI docs

2. **Check frontend port:**
   - Next.js usually runs on port 3000
   - If different, add it to `allow_origins` in `app/main.py`

3. **Check API URL in frontend:**
   - Open browser console
   - Should see: `API URL: http://localhost:8000/api/documents`
   - If different, check `.env` file

4. **For Production:**
   - Update `allow_origins` with your production frontend URL
   - Example: `allow_origins=["https://yourdomain.com"]`

## Common Issues

### "Network Error" or "Failed to fetch"
- Backend not running
- Wrong API URL in frontend
- Firewall blocking connection

### "CORS policy" error
- Backend CORS not configured (should be fixed now)
- Frontend URL not in `allow_origins` list

### "404 Not Found"
- API endpoint doesn't exist
- Check backend routes are registered
- Check API URL is correct


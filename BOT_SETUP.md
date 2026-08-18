# Embeddable Bot Setup Guide

## Overview

The Dabang bot can be embedded on any website. All conversations are stored in MongoDB and can be viewed in the Messages section of the dashboard.

## Setup Steps

### 1. Install MongoDB

Make sure MongoDB is installed and running:

```bash
# Using Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Or install locally
# Windows: Download from https://www.mongodb.com/try/download/community
# macOS: brew install mongodb-community
# Linux: sudo apt-get install mongodb
```

### 2. Configure Environment Variables

Add to your `.env` file in `eti_backend/`:

```env
# MongoDB Configuration
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DB_NAME=eti_bot

# API URL (for embed script)
API_URL=http://localhost:8000
```

### 3. Install Dependencies

```bash
cd eti_backend
pip install -r requirements.txt
```

### 4. Start the Backend

```bash
uvicorn app.main:app --reload
```

### 5. Get the Embed Script

1. Go to: `http://localhost:3000/bot-script` (or add this page to your navigation)
2. Copy the embed code
3. Paste it before the `</body>` tag of your website

## API Endpoints

### Bot Chat
- **POST** `/api/bot/chat` - Chat endpoint for the embeddable widget
- **GET** `/api/bot/script` - Get the embeddable JavaScript code

### Conversations
- **GET** `/api/conversations` - List all conversations
- **GET** `/api/conversations/{id}` - Get a specific conversation
- **DELETE** `/api/conversations/{id}` - Delete a conversation

## Features

1. **Embeddable Widget**: Add the bot to any website with a simple script tag
2. **Session Management**: Each visitor gets a unique session ID
3. **MongoDB Storage**: All conversations are stored in MongoDB
4. **Message History**: View all conversations in the Messages UI
5. **Document Context**: Bot uses uploaded documents for context (if available)

## Usage

### For Website Owners

1. Upload documents in the AI Assistant section
2. Get the embed script from `/bot-script` page
3. Add the script to your website
4. View conversations in the Messages section

### For End Users

1. Visit a website with the bot embedded
2. Click the chat button (bottom-right corner)
3. Start chatting with the AI assistant
4. Conversations are automatically saved

## MongoDB Collections

- `conversations` - Stores all bot conversations with messages, session info, and metadata

## Production Considerations

1. **CORS**: Update CORS settings in `app/main.py` to restrict origins
2. **MongoDB**: Use MongoDB Atlas or a secure MongoDB instance
3. **API URL**: Update `API_URL` in `.env` to your production domain
4. **Rate Limiting**: Add rate limiting to prevent abuse
5. **Authentication**: Add API keys for bot endpoints if needed


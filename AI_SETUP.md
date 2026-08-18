# AI Document Training Setup Guide

This guide explains how to set up the AI document training functionality in the ETI project.

## Overview

The AI system uses RAG (Retrieval Augmented Generation) to train on uploaded documents:
1. Users upload documents (PDF, Word, Excel, PowerPoint, Text)
2. Documents are processed and split into chunks
3. Chunks are converted to embeddings using SentenceTransformers
4. Embeddings are stored in the database
5. Users can query documents using natural language
6. The system finds relevant chunks and uses OpenAI to generate answers

## Backend Setup

### 1. Install Dependencies

```bash
cd eti_backend
pip install -r requirements.txt
```

New packages added:
- `openai` - For LLM responses
- `sentence-transformers` - For generating embeddings
- `PyPDF2`, `pdfplumber` - For PDF processing
- `python-docx` - For Word document processing
- `openpyxl` - For Excel processing
- `python-pptx` - For PowerPoint processing
- `chardet` - For text encoding detection
- `numpy` - For vector operations

### 2. Set Environment Variables

Create or update `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Get your API key from: https://platform.openai.com/api-keys

### 3. Database Migration

Create the migration:

```bash
cd eti_backend
alembic revision --autogenerate -m "add_document_and_document_chunk_tables"
alembic upgrade head
```

Or manually create the migration file in `alembic/versions/`:

```python
"""add_document_and_document_chunk_tables

Revision ID: <generate_id>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

def upgrade():
    op.create_table(
        'document',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('processed', sa.Boolean(), nullable=False),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_id'), 'document', ['id'], unique=False)
    
    op.create_table(
        'document_chunk',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', ARRAY(sa.Float()), nullable=True),
        sa.Column('chunk_metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_chunk_id'), 'document_chunk', ['id'], unique=False)
    op.create_index(op.f('ix_document_chunk_document_id'), 'document_chunk', ['document_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_document_chunk_document_id'), table_name='document_chunk')
    op.drop_index(op.f('ix_document_chunk_id'), table_name='document_chunk')
    op.drop_table('document_chunk')
    op.drop_index(op.f('ix_document_id'), table_name='document')
    op.drop_table('document')
```

### 4. Create Upload Directory

```bash
mkdir -p data/uploads
```

### 5. Start Backend Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup

### 1. Install Dependencies (if needed)

The frontend should already have the necessary dependencies. If not:

```bash
cd eti_frontend
npm install
```

### 2. Update API URL (if needed)

The components use `http://localhost:8000` as the backend URL. Update if your backend runs on a different port.

### 3. Start Frontend

```bash
npm run dev
```

## Usage

1. Navigate to `/ai` page in the frontend
2. Upload documents using the upload interface
3. Wait for documents to be processed (you'll see "Processed" status)
4. Ask questions in the AI chat interface
5. The AI will answer based on the uploaded documents

## API Endpoints

### Upload Document
```
POST /api/documents/upload
Content-Type: multipart/form-data
Body: file (file upload)
```

### List Documents
```
GET /api/documents
```

### Delete Document
```
DELETE /api/documents/{document_id}
```

### Query Documents
```
POST /api/documents/query
Content-Type: application/json
Body: {
  "query": "your question",
  "model": "gpt-3.5-turbo",
  "max_results": 5,
  "threshold": 0.3
}
```

### List Available Models
```
GET /api/documents/models
```

## Architecture

### Services

1. **DocumentProcessor**: Extracts text from various file formats
2. **EmbeddingService**: Generates vector embeddings using SentenceTransformers
3. **VectorStore**: Stores and searches embeddings using cosine similarity
4. **LLMService**: Generates responses using OpenAI API

### Flow

1. User uploads document → File saved to disk
2. DocumentProcessor extracts text → Text stored in database
3. Text chunked into smaller pieces → Chunks created
4. EmbeddingService generates embeddings → Embeddings stored in database
5. User asks question → Query embedding generated
6. VectorStore searches for similar chunks → Relevant chunks found
7. LLMService generates answer → Answer returned to user

## Notes

- First time loading the embedding model may take a few seconds
- Large documents may take time to process
- OpenAI API key is required for querying
- Documents are stored locally in `data/uploads/`
- Embeddings are stored in PostgreSQL database


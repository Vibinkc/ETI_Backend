import logging
import os
import shutil
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.router.instruction import get_system_prompt
from app.schema.document import DocumentResponse, QueryRequest, QueryResponse, ScrapeUrlRequest
from app.services.activity_log import log_activity
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.usage_tracker import documents_above_threshold, record_document_hits
from app.services.vector_store import VectorStore
from app.services.web_scraper import WebScraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Initialize services (singleton)
_embedding_service = None
_llm_service = None
_document_processor = None

# Upload directory
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_document_processor() -> DocumentProcessor:
    global _document_processor
    if _document_processor is None:
        _document_processor = DocumentProcessor()
    return _document_processor


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: bool = False,
    current_user: User = Depends(get_current_admin),
) -> DocumentResponse:
    """Upload and process a document for AI training."""
    try:
        # Save file temporarily to extract text/check sensitive data
        file_path = UPLOAD_DIR / cast("str", file.filename)
        # Ensure we don't overwrite blindly without checking, but for now we follow simple flow
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 1. Extract text immediately to check for sensitive data
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            processor = get_document_processor()
            # We need mime_type early
            mime_type = file.content_type or "application/octet-stream"
            text_content = processor.extract_text(file_bytes, mime_type, cast("str", file.filename))

            if not text_content:
                # If we can't extract text, we might warn or just proceed (binary file?)
                # But typically we want text.
                pass
            else:
                # 2. Check for sensitive data if not forced
                if not force:
                    warnings = processor.detect_sensitive_data(text_content)
                    if warnings:
                        # Clean up file
                        os.remove(file_path)
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "message": "Sensitive information detected in document.",
                                "code": "SENSITIVE_DATA_DETECTED",
                                "warnings": warnings,
                            },
                        )
        except HTTPException:
            raise
        except Exception as e:
            # If extraction fails here, we might fail hard or let the main process logic handle it.
            # But since we are pre-processing for safety, let's log and continue to
            # main flow if it wasn't a safety block
            logger.warning(f"Pre-processing text extraction failed: {e}")
            pass

        # Create document record. Capture the actor before any commit expires it.
        upload_actor_email = current_user.email
        uploaded_by_id = current_user.id
        document = Document(
            name=file.filename,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            mime_type=file.content_type or "application/octet-stream",
            processed=False,
            uploaded_by=uploaded_by_id,
        )
        db.add(document)
        await db.flush()
        document_id = document.id

        # Process document in background (for now, we'll do it synchronously)
        # In production, use Celery task
        try:
            # Reuse text_content if we already extracted it successfully
            if "text_content" in locals() and text_content:
                pass
            else:
                # Read file bytes again if needed
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                text_content = processor.extract_text(file_bytes, document.mime_type, document.name)

            if not text_content:
                document.error_message = "Failed to extract text from document"
                await db.commit()
                # We already created the doc, so maybe we shouldn't raise 400 here
                # if we want to keep record relative to 201
                # But original code raised 400. Let's keep consistent.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Could not extract text from document"
                )

            document.text_content = text_content

            # Chunk text
            chunks_data = processor.chunk_text(text_content)

            # Generate embeddings
            embedding_service = get_embedding_service()
            chunk_texts = [chunk["text"] for chunk in chunks_data]
            embeddings = embedding_service.generate_embeddings_batch(chunk_texts)

            # Store chunks with embeddings
            vector_store = VectorStore()
            for _i, (chunk_data, embedding) in enumerate(zip(chunks_data, embeddings, strict=False)):
                await vector_store.store_chunk(
                    db=db,
                    document_id=document.id,
                    chunk_index=chunk_data["index"],
                    text=chunk_data["text"],
                    embedding=embedding,
                    metadata={"start_char": chunk_data["start_char"], "end_char": chunk_data["end_char"]},
                )

            document.processed = True
            document_name = document.name  # Capture before commit
            await db.commit()

            logger.info(f"Successfully processed document: {document_name} ({len(chunks_data)} chunks)")

            await log_activity(
                db,
                actor_email=upload_actor_email,
                user_id=uploaded_by_id or None,
                action="document.upload",
                entity_type="document",
                entity_id=document_id,
                detail=f"Uploaded {document_name} ({len(chunks_data)} chunks)",
            )

        except Exception as e:
            logger.error(f"Error processing document: {e}")
            document.error_message = str(e)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing document: {e!s}"
            ) from e

        # Reload document and uploader after commit to avoid session issues
        # Use document_id and uploaded_by_id captured before any commit
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        document = doc_result.scalar_one()

        uploader = None
        if uploaded_by_id:
            user_result = await db.execute(select(User).where(User.id == uploaded_by_id))
            uploader = user_result.scalar_one_or_none()

        # Construct response manually
        response_data = {
            "id": document.id,
            "name": document.name,
            "file_path": document.file_path,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "processed": document.processed,
            "uploaded_by": document.uploaded_by,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

        if uploader:
            response_data["uploader"] = {
                "id": uploader.id,
                "email": uploader.email,
                "first_name": uploader.first_name,
                "last_name": uploader.last_name,
            }

        return DocumentResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error uploading document: {e!s}"
        ) from e


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    skip: int = Query(0, ge=0, description="Rows to skip"),
    limit: int = Query(20, ge=1, le=100, description="Rows per page"),
) -> list[DocumentResponse]:
    """List uploaded documents, newest first.

    Paginated via skip/limit. The unpaginated total is returned in the
    X-Total-Count header so the response stays a plain list and existing
    callers keep working.
    """
    total = await db.scalar(select(func.count(Document.id))) or 0
    response.headers["X-Total-Count"] = str(total)

    result = await db.execute(
        select(Document, User)
        .outerjoin(User, Document.uploaded_by == User.id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    documents = []
    for row in rows:
        doc, user = row
        doc_dict = {
            "id": doc.id,
            "name": doc.name,
            "file_path": doc.file_path,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "processed": doc.processed,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
        if user:
            doc_dict["uploader"] = {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        documents.append(DocumentResponse(**doc_dict))

    return documents


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),  # noqa: ARG001  # auth dependency
) -> FileResponse:
    """Serve the original uploaded file so an admin can view it in the browser.

    Scraped pages have no file on disk - their file_path is the source URL, and
    the caller should open that directly instead.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if str(document.file_path).lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document was scraped from a website; open its source URL instead.",
        )

    # Resolve inside the upload directory - never trust a stored path to stay put
    stored = Path(document.file_path)
    candidate = stored if stored.is_absolute() else Path.cwd() / stored
    upload_root = (Path.cwd() / UPLOAD_DIR).resolve()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(upload_root)
    except (ValueError, OSError):
        # Fall back to the filename inside the upload dir
        resolved = (upload_root / Path(document.name).name).resolve()
        try:
            resolved.relative_to(upload_root)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document path"
            ) from None

    if not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The original file is no longer on the server."
        )

    return FileResponse(
        path=str(resolved),
        media_type=document.mime_type or "application/octet-stream",
        filename=document.name,
        content_disposition_type="inline",
    )


# Left deliberately unannotated: this route has no explicit response_model, and
# FastAPI would turn a return annotation into one, changing serialisation.
@router.get("/{document_id}/content")
async def get_document_content(  # type: ignore[no-untyped-def]  # noqa: ANN201
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),  # noqa: ARG001  # auth dependency
):
    """Return the extracted text the bot actually answers from.

    For a scraped site this is the readable content pulled from the pages -
    which is what an admin needs to see, rather than the live website.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunk_count = (
        await db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id))
        or 0
    )

    content = document.text_content or ""

    return {
        "id": document.id,
        "name": document.name,
        "source": document.file_path,
        "mime_type": document.mime_type,
        "chunk_count": chunk_count,
        "char_count": len(content),
        "content": content,
        "error_message": document.error_message,
    }


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),
) -> None:
    """Delete a document and its chunks. Requires an authenticated admin."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Capture what we need for the audit entry before the row is gone, and read
    # the actor before commit() expires it.
    doc_name, doc_path = document.name, document.file_path
    actor_email, actor_id = current_user.email, (current_user.id or None)

    # Delete file
    if os.path.exists(doc_path):
        os.remove(doc_path)

    await db.delete(document)
    await db.commit()

    await log_activity(
        db,
        actor_email=actor_email,
        user_id=actor_id,
        action="document.delete",
        entity_type="document",
        entity_id=document_id,
        detail=f"Deleted {doc_name}",
    )
    return


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> QueryResponse:
    """Query documents using RAG (Retrieval Augmented Generation)."""
    # Generate query embedding
    embedding_service = get_embedding_service()
    query_embedding = embedding_service.generate_embedding(request.query)

    # Search for similar chunks
    vector_store = VectorStore()
    similar_chunks = []

    try:
        search_threshold = request.threshold

        # First attempt with requested threshold
        similar_chunks = await vector_store.search_similar(
            db, query_embedding, limit=request.max_results * 2, threshold=search_threshold
        )

        logger.info(f"Found {len(similar_chunks)} similar chunks for query: '{request.query}'")

        # If no results, try progressively lower thresholds
        if not similar_chunks:
            for fallback_threshold in [0.25, 0.2, 0.15, 0.1]:
                logger.info(f"No results with threshold {search_threshold}, trying {fallback_threshold}")
                similar_chunks = await vector_store.search_similar(
                    db, query_embedding, limit=request.max_results * 2, threshold=fallback_threshold
                )
                if similar_chunks:
                    logger.info(f"Found {len(similar_chunks)} results with threshold {fallback_threshold}")
                    break

        # Limit to requested max_results
        if similar_chunks:
            similar_chunks = similar_chunks[: request.max_results]

    except Exception as e:
        logger.error(f"Error searching for similar chunks: {e}")
        llm_service = get_llm_service()
        return QueryResponse(
            answer="No documents have been uploaded yet. Please upload documents first before querying.",
            sources=[],
            model_used=llm_service.model,
        )

    if not similar_chunks:
        llm_service = get_llm_service()
        return QueryResponse(
            answer="I couldn't find any relevant information in the uploaded documents to answer your question. Try rephrasing your question or upload more relevant documents.",  # noqa: E501  # user-facing string, must not be reflowed
            sources=[],
            model_used=llm_service.model,
        )

    # Get document information for sources
    chunk_ids = [chunk.id for chunk, _ in similar_chunks]
    result = await db.execute(
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.id.in_(chunk_ids))
    )
    chunk_doc_pairs = result.all()

    # Build context chunks with source info
    context_chunks = []
    sources_map = {}

    for chunk, similarity in similar_chunks:
        # Find document for this chunk
        doc = next((doc for chunk_obj, doc in chunk_doc_pairs if chunk_obj.id == chunk.id), None)

        doc_name = doc.name if doc else "Unknown Document"

        context_chunks.append({"text": chunk.text, "similarity": similarity, "source": doc_name})

        if doc:
            sources_map[doc.id] = {
                "document_id": doc.id,
                "document_name": doc.name,
                "chunk_index": chunk.chunk_index,
            }

    # Generate LLM response
    llm_service = get_llm_service()

    # Use the admin-editable instruction so the dashboard assistant and the
    # public widget behave identically
    system_prompt = await get_system_prompt(db)

    answer = llm_service.generate_response(request.query, context_chunks, system_prompt=system_prompt)

    # Record which documents answered this question. Same similarity bar as the
    # widget, so a document that merely placed in the top five is not credited.
    await record_document_hits(db, documents_above_threshold(similar_chunks), source="assistant")

    # Prepare sources
    sources = list(sources_map.values())

    return QueryResponse(answer=answer, sources=sources, model_used=llm_service.model)


@router.post("/scrape-url", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def scrape_url(
    request: ScrapeUrlRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_admin),
) -> DocumentResponse:
    """Scrape content from a website URL and process it for AI training."""
    try:
        # Scrape the URL
        scraper = WebScraper()
        text_content = scraper.scrape_url(request.url)

        if not text_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not scrape content from the URL. Please check if the URL is accessible.",
            )

        # Extract domain name for document name (for full site scraping)
        from urllib.parse import urlparse

        parsed_url = urlparse(request.url)
        domain_name = parsed_url.netloc.replace("www.", "")
        document_name = f"{domain_name} - Full Site"

        # Create document record (similar to file upload but for URL)
        uploaded_by_id = current_user.id
        document = Document(
            name=document_name,
            file_path=request.url,  # Store URL as file_path for URL-based documents
            file_size=len(text_content.encode("utf-8")),
            mime_type="text/html",
            processed=False,
            uploaded_by=uploaded_by_id,  # Track which admin scraped the URL
        )
        db.add(document)
        await db.flush()
        document_id = document.id
        # Read the actor now: commit() below expires current_user
        scrape_actor_email, scrape_actor_id = current_user.email, (current_user.id or None)

        # Process the scraped content
        try:
            document.text_content = text_content

            # Chunk text
            processor = get_document_processor()
            chunks_data = processor.chunk_text(text_content)

            # Generate embeddings
            embedding_service = get_embedding_service()
            chunk_texts = [chunk["text"] for chunk in chunks_data]
            embeddings = embedding_service.generate_embeddings_batch(chunk_texts)

            # Store chunks with embeddings
            vector_store = VectorStore()
            for _i, (chunk_data, embedding) in enumerate(zip(chunks_data, embeddings, strict=False)):
                await vector_store.store_chunk(
                    db=db,
                    document_id=document.id,
                    chunk_index=chunk_data["index"],
                    text=chunk_data["text"],
                    embedding=embedding,
                    metadata={
                        "start_char": chunk_data["start_char"],
                        "end_char": chunk_data["end_char"],
                        "source_url": request.url,
                    },
                )

            document.processed = True
            document_name = document.name  # Capture before commit
            await db.commit()

            logger.info(f"Successfully processed scraped URL: {request.url} ({len(chunks_data)} chunks)")

            await log_activity(
                db,
                actor_email=scrape_actor_email,
                user_id=scrape_actor_id,
                action="document.scrape",
                entity_type="document",
                entity_id=document_id,
                detail=f"Scraped {request.url} ({len(chunks_data)} chunks)",
            )

        except Exception as e:
            logger.error(f"Error processing scraped URL: {e}")
            document.error_message = str(e)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing scraped content: {e!s}",
            ) from e

        # Reload document and uploader after commit to avoid session issues
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        document = doc_result.scalar_one()

        uploader = None
        if uploaded_by_id:
            user_result = await db.execute(select(User).where(User.id == uploaded_by_id))
            uploader = user_result.scalar_one_or_none()

        # Construct response manually
        response_data = {
            "id": document.id,
            "name": document.name,
            "file_path": document.file_path,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "processed": document.processed,
            "uploaded_by": document.uploaded_by,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

        if uploader:
            response_data["uploader"] = {
                "id": uploader.id,
                "email": uploader.email,
                "first_name": uploader.first_name,
                "last_name": uploader.last_name,
            }

        return DocumentResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scraping URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error scraping URL: {e!s}"
        ) from e


# Left deliberately unannotated: this route has no explicit response_model, and
# FastAPI would turn a return annotation into one, changing serialisation.
@router.get("/models")
async def list_available_models():  # type: ignore[no-untyped-def]  # noqa: ANN201
    """List available LLM models."""
    return {
        "models": [
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "OpenAI"},
            {"id": "gpt-4", "name": "GPT-4", "provider": "OpenAI"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "OpenAI"},
        ]
    }

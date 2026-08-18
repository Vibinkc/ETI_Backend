"""Bot API router for embeddable chat widget."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongodb import mongodb_settings
from app.core.timeutils import utcnow
from app.models.conversation import Conversation, Message
from app.router.instruction import get_system_prompt
from app.schema.conversation import BotChatRequest, BotChatResponse
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.usage_tracker import documents_above_threshold, record_document_hits
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api/bot", tags=["bot"])


def generate_session_id(request: Request) -> str:
    """Generate or get session ID from request."""
    # Try to get from header or cookie
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        # Generate a simple session ID (in production, use a proper session manager)
        import hashlib

        user_agent = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else "unknown"
        # Not a security hash - it only derives a stable per-visitor chat id.
        session_id = hashlib.md5(f"{ip}{user_agent}".encode(), usedforsecurity=False).hexdigest()[:16]
    return session_id


@router.post("/chat", response_model=BotChatResponse)
async def bot_chat(
    bot_request: BotChatRequest, http_request: Request, db: AsyncSession = Depends(get_db)
) -> BotChatResponse:
    """
    Chat endpoint for embeddable bot widget.
    This endpoint can be called from external websites.
    Only responds based on uploaded documents, not general knowledge.
    """
    try:
        db_mongo = mongodb_settings.get_database()
        conversations_collection = db_mongo["conversations"]

        # Get or create conversation
        session_id = bot_request.session_id or generate_session_id(http_request)

        # Find existing conversation
        conversation_doc = await conversations_collection.find_one({"session_id": session_id})

        # Add user message
        user_message = Message(role="user", content=bot_request.message, timestamp=utcnow())

        # Generate AI response using LLM service
        llm_service = LLMService()
        vector_store = VectorStore()
        embedding_service = EmbeddingService()

        # Check if message is a greeting or casual conversation
        message_lower = bot_request.message.lower().strip()
        greetings = [
            "hi",
            "hello",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "greetings",
            "hi there",
            "hello there",
        ]
        is_greeting = (
            any(greeting in message_lower for greeting in greetings) and len(message_lower.split()) <= 3
        )

        if is_greeting:
            # Handle greetings without requiring document context
            ai_response_text = (
                "Hello! 👋 I'm here to help you with any questions about ETI. What would you like to know?"
            )
        else:
            original_query = bot_request.message
            context_chunks = []

            try:
                # Try multiple query variations to improve matching
                query_variations = [original_query]

                # Add ETI context if not present
                query_lower = original_query.lower()
                if "eti" not in query_lower and "electrical training institute" not in query_lower:
                    query_variations.append(f"{original_query} ETI")
                    query_variations.append(f"ETI {original_query}")

                similar_chunks = []

                # Try each query variation with progressively lower thresholds
                for query_variant in query_variations:
                    query_embedding = embedding_service.generate_embedding(query_variant)

                    # Try with multiple thresholds, starting low for better recall
                    for threshold in [0.2, 0.15, 0.1, 0.05]:
                        logger.info(f"Searching with query: '{query_variant}', threshold: {threshold}")
                        chunks = await vector_store.search_similar(
                            db, query_embedding, limit=10, threshold=threshold
                        )

                        if chunks:
                            similar_chunks = chunks
                            logger.info(
                                f"Found {len(chunks)} chunks with query '{query_variant}' at threshold {threshold}"  # noqa: E501  # log message; wrapping would alter the emitted text
                            )
                            break

                    if similar_chunks:
                        break

                # If still no results, try with very low threshold (0.01) to get top results regardless
                if not similar_chunks:
                    logger.info("No results found, trying with very low threshold to get top matches")
                    query_embedding = embedding_service.generate_embedding(query_variations[0])
                similar_chunks = await vector_store.search_similar(
                    db,
                    query_embedding,
                    limit=10,
                    threshold=0.01,  # Very low to get top results
                )
                if similar_chunks:
                    logger.info(f"Found {len(similar_chunks)} chunks with very low threshold")

                # Take top 5 results
                if similar_chunks:
                    similar_chunks = similar_chunks[:5]
                    context_chunks = [
                        {
                            "text": chunk.text,
                            "source": f"Document {chunk.document_id}",
                            "similarity": similarity,
                        }
                        for chunk, similarity in similar_chunks
                    ]
                    logger.info(
                        f"Using {len(context_chunks)} chunks with similarity scores: {[f'{s:.3f}' for _, s in similar_chunks[:5]]}"  # noqa: E501  # log message; wrapping would alter the emitted text
                    )
                    # Record which documents actually answered this question
                    await record_document_hits(
                        db, documents_above_threshold(similar_chunks), session_id=session_id, source="widget"
                    )
                else:
                    logger.warning(f"No chunks found for query: '{original_query}'")

            except Exception as e:
                logger.error(f"Could not get document context: {e}", exc_info=True)

            # If no context found, return a friendly message suggesting ETI-related questions
            if not context_chunks:
                ai_response_text = "I'd be happy to help! 😊 For specific details about that, I'd recommend checking out our website - you'll find comprehensive information there! 🌐\n\nIn the meantime, here are some topics I can assist you with:\n\n• Our programs and apprenticeships (Inside Wireman, Intelligent Transportation Systems, Sound & Telecommunications)\n• Application process and requirements\n• Training schedules and curriculum\n• Career opportunities and job placement\n• Benefits and support services\n• Veterans programs and military benefits\n• Continuing education opportunities\n\nWhat would you like to know more about?"  # noqa: E501  # user-facing reply text; rewrapping would change what the visitor reads
            else:
                # Generate response only from the provided context, using the
                # admin-editable instruction (falls back to the built-in default)
                system_prompt = await get_system_prompt(db)
                ai_response_text = llm_service.generate_response(
                    original_query,  # Use original query for LLM, not enhanced
                    context_chunks,
                    system_prompt=system_prompt,
                )

        # Add assistant message
        assistant_message = Message(role="assistant", content=ai_response_text, timestamp=utcnow())

        # Log message content length for debugging
        logger.info(f"Saving bot response - content length: {len(ai_response_text)} chars")
        logger.info(f"Full content preview (first 200 chars): {ai_response_text[:200]}")
        logger.info(f"Full content preview (last 200 chars): {ai_response_text[-200:]}")

        # Check for bullet points in the response
        has_bullets = any(char in ai_response_text for char in ["•", "-", "*"])
        if has_bullets:
            logger.info(
                f"Bot response contains bullet points: {ai_response_text.count('•')} bullet chars, {ai_response_text.count('-')} dashes, {ai_response_text.count('*')} asterisks"  # noqa: E501  # log message; wrapping would alter the emitted text
            )
        else:
            logger.warning(
                f"Bot response does NOT contain bullet points! Content preview: {ai_response_text[:300]}"
            )

        # Verify content is not truncated before saving
        assistant_dump = assistant_message.model_dump()
        saved_content_length = len(assistant_dump.get("content", ""))
        if saved_content_length != len(ai_response_text):
            logger.error(
                f"CONTENT TRUNCATION DETECTED! Original: {len(ai_response_text)} chars, Serialized: {saved_content_length} chars"  # noqa: E501  # log message; wrapping would alter the emitted text
            )
        else:
            logger.info(f"Content verified - {saved_content_length} chars preserved in model_dump()")

        # Update or create conversation
        if conversation_doc:
            # Update existing conversation
            result = await conversations_collection.update_one(
                {"_id": ObjectId(conversation_doc["_id"])},
                {
                    "$push": {
                        "messages": {"$each": [user_message.model_dump(), assistant_message.model_dump()]}
                    },
                    "$set": {
                        "updated_at": utcnow(),
                        "website_url": bot_request.website_url or conversation_doc.get("website_url"),
                        "user_ip": bot_request.user_ip or conversation_doc.get("user_ip"),
                        "user_agent": bot_request.user_agent or conversation_doc.get("user_agent"),
                    },
                },
            )
            logger.info(
                f"MongoDB update result - matched: {result.matched_count}, modified: {result.modified_count}"
            )

            # Verify what was actually saved
            verify_doc = await conversations_collection.find_one({"_id": ObjectId(conversation_doc["_id"])})
            if verify_doc:
                saved_messages = verify_doc.get("messages", [])
                if saved_messages:
                    last_assistant = next(
                        (m for m in reversed(saved_messages) if m.get("role") == "assistant"), None
                    )
                    if last_assistant:
                        saved_content = str(last_assistant.get("content", ""))
                        saved_length = len(saved_content)
                        logger.info(
                            f"Verified saved message length: {saved_length} chars (expected: {len(ai_response_text)})"  # noqa: E501  # log message; wrapping would alter the emitted text
                        )
                        if saved_length != len(ai_response_text):
                            logger.error(
                                f"TRUNCATION IN MONGODB! Expected {len(ai_response_text)} chars, got {saved_length} chars"  # noqa: E501  # log message; wrapping would alter the emitted text
                            )

                        # Check if bullet points are preserved
                        original_bullets = sum(ai_response_text.count(char) for char in ["•", "-", "*"])
                        saved_bullets = sum(saved_content.count(char) for char in ["•", "-", "*"])
                        if original_bullets != saved_bullets:
                            logger.error(
                                f"BULLET POINTS LOST IN MONGODB! Original had {original_bullets} bullet chars, saved has {saved_bullets} bullet chars"  # noqa: E501  # log message; wrapping would alter the emitted text
                            )
                        elif original_bullets > 0:
                            logger.info(
                                f"Bullet points preserved: {saved_bullets} bullet characters in saved message"
                            )
        else:
            # Create new conversation
            new_conversation = Conversation(
                session_id=session_id,
                website_url=bot_request.website_url,
                user_ip=bot_request.user_ip or (http_request.client.host if http_request.client else None),
                user_agent=bot_request.user_agent or http_request.headers.get("user-agent"),
                messages=[user_message, assistant_message],
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            await conversations_collection.insert_one(new_conversation.model_dump())

        return BotChatResponse(response=ai_response_text, session_id=session_id)

    except Exception as e:
        logger.error(f"Error in bot chat: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing chat: {e!s}") from e


@router.get("/script")
async def get_embed_script() -> JSONResponse:
    """
    Generate embeddable JavaScript code for the bot widget.
    Returns JavaScript code that can be embedded in any website.
    """
    import os

    api_url = os.getenv("API_URL", "http://localhost:8000")

    script = f"""
(function() {{
    // ETI Bot Widget
    const API_URL = '{api_url}/api/bot';
    
    // Generate session ID
    function getSessionId() {{
        let sessionId = localStorage.getItem('eti_session_id');
        if (!sessionId) {{
            sessionId = 'sess_' + Math.random().toString(36).substr(2, 16);
            localStorage.setItem('eti_session_id', sessionId);
        }}
        return sessionId;
    }}
    
    // Create widget HTML
    function createWidget() {{
        const widget = document.createElement('div');
        widget.id = 'eti-bot-widget';
        widget.innerHTML = `
            <div style="position: fixed; bottom: 20px; right: 20px; z-index: 10000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div id="eti-bot-container" style="display: none; width: 350px; height: 500px; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); flex-direction: column; position: relative;">
                    <div style="background: linear-gradient(135deg, #002c5c 0%, #001a36 100%); color: white; padding: 16px; border-radius: 12px 12px 0 0; display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <img src="{api_url}/static/eti_logo.png" alt="ETI" style="width: 24px; height: 24px; object-fit: contain; background: rgba(255,255,255,0.2); border-radius: 4px; padding: 2px;" onerror="this.style.display='none';" />
                            <div>
                                <h3 style="margin: 0; font-size: 18px; font-weight: 600;">ETI Assistant</h3>
                                <p style="margin: 4px 0 0 0; font-size: 12px; opacity: 0.9;">How can I help you today?</p>
                            </div>
                        </div>
                        <button id="eti-close-btn" style="background: rgba(255,255,255,0.2); border: none; color: white; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; font-size: 20px; line-height: 1;">×</button>
                    </div>
                    <div id="eti-messages" style="flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px;">
                        <div style="background: white; padding: 12px; border-radius: 8px; max-width: 85%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <p style="margin: 0 0 8px 0; font-size: 14px; color: #374151; line-height: 1.5;">
                                ✨ <strong>Welcome to ETI!</strong> ✨<br/>
                                How can we assist you today? 🤖💬<br/>
                                We're here to help with any inquiries or support you need. Let us know how we can make your experience better! 😊✨
                            </p>
                            <p style="margin: 8px 0 0 0; font-size: 12px; color: #6b7280; text-align: right;">08:13 PM</p>
                        </div>
                        <div style="background: white; padding: 12px; border-radius: 8px; max-width: 85%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <p style="margin: 0; font-size: 14px; color: #374151;">Select one option to proceed further!</p>
                            <p style="margin: 8px 0 0 0; font-size: 12px; color: #6b7280; text-align: right;">08:13 PM</p>
                        </div>
                        <div id="eti-options" style="display: flex; flex-direction: column; gap: 10px; margin-top: 8px;">
                            <button id="eti-faq-btn" style="background: white; border: 2px solid #002c5c; color: #002c5c; padding: 12px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; text-align: center; transition: all 0.2s;" onmouseover="this.style.background='#002c5c'; this.style.color='white';" onmouseout="this.style.background='white'; this.style.color='#002c5c';">General FAQs</button>
                            <button id="eti-consultation-btn" style="background: white; border: 2px solid #002c5c; color: #002c5c; padding: 12px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; text-align: center; transition: all 0.2s;" onmouseover="this.style.background='#002c5c'; this.style.color='white';" onmouseout="this.style.background='white'; this.style.color='#002c5c';">Book a consultation with us</button>
                        </div>
                    </div>
                    <div style="border-top: 1px solid #e5e7eb; padding: 12px; background: white; border-radius: 0 0 12px 12px;">
                        <div style="display: flex; gap: 8px;">
                            <input id="eti-input" type="text" placeholder="Type your message..." style="flex: 1; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; outline: none;" />
                            <button id="eti-send-btn" style="background: #002c5c; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500;">Send</button>
                        </div>
                    </div>
                </div>
                <button id="eti-toggle-btn" style="width: 60px; height: 60px; border-radius: 50%; background: linear-gradient(135deg, #002c5c 0%, #001a36 100%); border: none; color: white; font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(0, 44, 92, 0.4); display: flex; align-items: center; justify-content: center;">💬</button>
            </div>
        `;
        document.body.appendChild(widget);
        return widget;
    }}
    
    // Initialize widget
    if (!document.getElementById('eti-bot-widget')) {{
        const widget = createWidget();
        const container = document.getElementById('eti-bot-container');
        const toggleBtn = document.getElementById('eti-toggle-btn');
        const closeBtn = document.getElementById('eti-close-btn');
        const sendBtn = document.getElementById('eti-send-btn');
        const input = document.getElementById('eti-input');
        const messagesDiv = document.getElementById('eti-messages');
        const faqBtn = document.getElementById('eti-faq-btn');
        const consultationBtn = document.getElementById('eti-consultation-btn');
        const optionsDiv = document.getElementById('eti-options');
        
        const sessionId = getSessionId();
        const websiteUrl = window.location.href;
        
        // Toggle chat
        toggleBtn.addEventListener('click', () => {{
            container.style.display = container.style.display === 'none' ? 'flex' : 'none';
            toggleBtn.style.display = container.style.display === 'flex' ? 'none' : 'flex';
        }});
        
        closeBtn.addEventListener('click', () => {{
            container.style.display = 'none';
            toggleBtn.style.display = 'flex';
        }});
        
        // Helper function to send message and get response
        async function sendMessageAndGetResponse(messageText) {{
            // Hide options after selection
            if (optionsDiv) optionsDiv.style.display = 'none';
            
            // Add user message
            const userMsg = document.createElement('div');
            userMsg.style.cssText = 'background: #002c5c; color: white; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-end;';
            userMsg.innerHTML = `<p style="margin: 0; font-size: 14px;">${{messageText}}</p>`;
            messagesDiv.appendChild(userMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            // Show loading indicator
            const loadingMsg = document.createElement('div');
            loadingMsg.style.cssText = 'background: #f3f4f6; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;';
            loadingMsg.innerHTML = `<p style="margin: 0; font-size: 14px; color: #374151;">Thinking...</p>`;
            messagesDiv.appendChild(loadingMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            try {{
                const response = await fetch(API_URL + '/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        message: messageText,
                        session_id: sessionId,
                        website_url: websiteUrl,
                        user_ip: null,
                        user_agent: navigator.userAgent
                    }})
                }});
                
                const data = await response.json();
                
                // Remove loading message
                loadingMsg.remove();
                
                // Add bot response
                const botMsg = document.createElement('div');
                botMsg.style.cssText = 'background: #f3f4f6; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;';
                botMsg.innerHTML = `<p style="margin: 0; font-size: 14px; color: #374151;">${{data.response}}</p>`;
                messagesDiv.appendChild(botMsg);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }} catch (error) {{
                console.error('Error sending message:', error);
                loadingMsg.remove();
                const errorMsg = document.createElement('div');
                errorMsg.style.cssText = 'background: #fee2e2; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;';
                errorMsg.innerHTML = `<p style="margin: 0; font-size: 14px; color: #991b1b;">Sorry, there was an error. Please try again.</p>`;
                messagesDiv.appendChild(errorMsg);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }}
        }}
        
        // FAQ button handler
        faqBtn.addEventListener('click', () => {{
            sendMessageAndGetResponse('General FAQs');
        }});
        
        // Consultation button handler
        consultationBtn.addEventListener('click', () => {{
            sendMessageAndGetResponse('Book a consultation with us');
        }});
        
        // Send message
        async function sendMessage() {{
            const message = input.value.trim();
            if (!message) return;
            
            // Hide options if visible
            if (optionsDiv) optionsDiv.style.display = 'none';
            
            // Add user message
            const userMsg = document.createElement('div');
            userMsg.style.cssText = 'background: #002c5c; color: white; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-end;';
            userMsg.innerHTML = `<p style="margin: 0; font-size: 14px;">${{message}}</p>`;
            messagesDiv.appendChild(userMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            input.value = '';
            sendBtn.disabled = true;
            sendBtn.textContent = '...';
            
            try {{
                const response = await fetch(API_URL + '/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        message: message,
                        session_id: sessionId,
                        website_url: websiteUrl,
                        user_ip: null,
                        user_agent: navigator.userAgent
                    }})
                }});
                
                const data = await response.json();
                
                // Add bot response
                const botMsg = document.createElement('div');
                botMsg.style.cssText = 'background: #f3f4f6; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;';
                botMsg.innerHTML = `<p style="margin: 0; font-size: 14px; color: #374151;">${{data.response}}</p>`;
                messagesDiv.appendChild(botMsg);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }} catch (error) {{
                console.error('Error sending message:', error);
                const errorMsg = document.createElement('div');
                errorMsg.style.cssText = 'background: #fee2e2; padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;';
                errorMsg.innerHTML = `<p style="margin: 0; font-size: 14px; color: #991b1b;">Sorry, there was an error. Please try again.</p>`;
                messagesDiv.appendChild(errorMsg);
            }} finally {{
                sendBtn.disabled = false;
                sendBtn.textContent = 'Send';
            }}
        }}
        
        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keypress', (e) => {{
            if (e.key === 'Enter') sendMessage();
        }});
    }}
}})();
"""  # noqa: E501, W293, RUF001  # embedded JS/CSS asset: close glyph is rendered in the UI

    return JSONResponse(content={"script": script.strip()}, headers={"Content-Type": "application/json"})

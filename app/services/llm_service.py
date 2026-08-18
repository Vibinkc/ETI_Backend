import logging
import os
from typing import Any

from openai import OpenAI

from app.core.prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions using OpenAI GPT."""

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        """
        Initialize LLM service with GPT.
        Defaults to OpenAI GPT-4o-mini, but can be configured.
        """
        # Get model from env or use default
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_key = api_key or os.getenv("OPENAI_API_KEY")

        # Debug: Log if key is found (without showing the actual key)
        if api_key:
            logger.info(f"OpenAI API key found (length: {len(api_key)})")
        else:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            logger.warning("Please set OPENAI_API_KEY in your .env file")

        if not api_key:
            self.client = None
        else:
            try:
                # Initialize OpenAI client with api_key
                # httpx 0.27.2+ should support proxies parameter
                self.client = OpenAI(api_key=api_key)

                logger.info(f"LLM Service initialized with model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                logger.error(f"Error type: {type(e).__name__}, Error details: {e!s}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")
                self.client = None

    def generate_response(
        self, query: str, context_chunks: list[dict[str, Any]], system_prompt: str | None = None
    ) -> str:
        """
        Generate LLM response using RAG context.

        Args:
            query: User's question
            context_chunks: List of dicts with 'text' and optionally 'source' keys
            system_prompt: Optional system prompt

        Returns:
            Generated response string

        """
        if not self.client:
            return "LLM service is not configured. Please set OPENAI_API_KEY environment variable."

        # Build context from chunks (without document names)
        context_text = "\n\n".join([chunk.get("text", "") for chunk in context_chunks])

        # Fall back to the built-in default when the caller passes nothing.
        # The editable instruction lives in the bot_instruction table and is
        # resolved by app/router/instruction.py::get_system_prompt.
        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        # Build messages
        messages: list[Any] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Information about ETI (from documents and scraped content):
{context_text}

Question: {query}""",
            },
        ]

        try:
            # OpenAI 1.12.0 uses chat.completions.create
            response = self.client.chat.completions.create(
                model=self.model,  # type: ignore[arg-type]  # env default keeps this a str
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )

            return response.choices[0].message.content  # type: ignore[return-value]  # API contract
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            return f"Error generating response: {e!s}"

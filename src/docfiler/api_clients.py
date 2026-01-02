"""API client implementations for different VLM providers.

This module provides a unified interface to Claude, OpenAI, and Gemini APIs.
"""

import base64
import json
import logging
from abc import ABC, abstractmethod

import anthropic
from google import genai
from openai import OpenAI

logger = logging.getLogger(__name__)


class VLMClient(ABC):
    """Abstract base class for VLM API clients."""

    @abstractmethod
    def analyze_document(self, prompt: str, images: list[bytes], max_tokens: int = 1024) -> dict:
        """Analyze document images with a prompt.

        Args:
            prompt: The prompt text to send to the model.
            images: List of image data as bytes.

        Returns:
            Dictionary with 'filename', 'destination', 'confidence', and 'reasoning'.

        Raises:
            Exception: If the API call fails or response is invalid.
        """
        pass


class ClaudeClient(VLMClient):
    """Client for Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key.
            model: Model name (e.g., 'claude-3-5-sonnet-20241022').
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze_document(self, prompt: str, images: list[bytes], max_tokens: int = 1024) -> dict:
        """Analyze document images with Claude.

        Args:
            prompt: The prompt text.
            images: List of image data as bytes.

        Returns:
            Parsed JSON response from Claude.
        """
        logger.info(f"Sending request to Claude ({self.model})")

        # Build content array with images and prompt
        content = []

        for _idx, img_bytes in enumerate(images):
            # Encode image as base64
            img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64,
                },
            })

        # Add the text prompt
        content.append({
            "type": "text",
            "text": prompt,
        })

        # Make API call
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )

        # Extract text response
        response_text = response.content[0].text
        logger.debug(f"Claude response: {response_text}")

        # Parse JSON from response
        return self._parse_json_response(response_text)

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from model response.

        Args:
            response_text: Raw text response from the model.

        Returns:
            Parsed JSON dictionary.

        Raises:
            ValueError: If response cannot be parsed as JSON.
        """
        # Try to extract JSON from markdown code blocks if present
        text = response_text.strip()

        if text.startswith("```json"):
            # Remove markdown code block
            text = text[7:]  # Remove ```json
            if text.endswith("```"):
                text = text[:-3]  # Remove ```
            text = text.strip()
        elif text.startswith("```"):
            # Generic code block
            text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            result = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {text}")
            raise ValueError(f"Invalid JSON response: {e}") from e


class OpenAIClient(VLMClient):
    """Client for OpenAI's GPT-4 Vision API."""

    def __init__(self, api_key: str, model: str):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model name (e.g., 'gpt-4o').
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def analyze_document(self, prompt: str, images: list[bytes], max_tokens: int = 1024) -> dict:
        """Analyze document images with GPT-4 Vision.

        Args:
            prompt: The prompt text.
            images: List of image data as bytes.

        Returns:
            Parsed JSON response from GPT-4.
        """
        logger.info(f"Sending request to OpenAI ({self.model})")

        # Build content array
        content = []

        for img_bytes in images:
            img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                },
            })

        # Add text prompt
        content.append({
            "type": "text",
            "text": prompt,
        })

        # Prepare parameters for the API call
        params = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }

        # Newer models (like o1 series or newer GPT versions) use max_completion_tokens
        # instead of max_tokens.
        if self.model.startswith(("o1-", "gpt-5")):
            params["max_completion_tokens"] = max_tokens
        else:
            params["max_tokens"] = max_tokens

        # Make API call
        response = self.client.chat.completions.create(**params)

        # Extract response text
        response_text = response.choices[0].message.content
        logger.debug(f"OpenAI response: {response_text}")

        # Parse JSON
        return self._parse_json_response(response_text)

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from model response."""
        # Reuse Claude's JSON parsing logic
        return ClaudeClient._parse_json_response(None, response_text)


class GeminiClient(VLMClient):
    """Client for Google's Gemini API."""

    def __init__(self, api_key: str, model: str):
        """Initialize Gemini client.

        Args:
            api_key: Google API key.
            model: Model name (e.g., 'gemini-2.0-flash-exp').
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def analyze_document(self, prompt: str, images: list[bytes], max_tokens: int = 1024) -> dict:
        """Analyze document images with Gemini.

        Args:
            prompt: The prompt text.
            images: List of image data as bytes.

        Returns:
            Parsed JSON response from Gemini.
        """
        logger.info(f"Sending request to Gemini ({self.model_name})")

        # Build content list with parts
        parts = []

        for img_bytes in images:
            parts.append(genai.types.Part.from_bytes(
                data=img_bytes,
                mime_type="image/png"
            ))

        # Add prompt text as a part
        parts.append(genai.types.Part.from_text(text=prompt))

        # Make API call
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=parts,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            )
        )
        response_text = response.text
        logger.debug(f"Gemini response: {response_text}")

        # Parse JSON
        return self._parse_json_response(response_text)

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from model response."""
        # Reuse Claude's JSON parsing logic
        return ClaudeClient._parse_json_response(None, response_text)


def create_client(provider: str, api_key: str, model: str) -> VLMClient:
    """Factory function to create the appropriate VLM client.

    Args:
        provider: Provider name ('claude', 'openai', or 'gemini').
        api_key: API key for the provider.
        model: Model name to use.

    Returns:
        VLMClient instance.

    Raises:
        ValueError: If provider is not supported.
    """
    providers = {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
        "gemini": GeminiClient,
    }

    client_class = providers.get(provider.lower())
    if not client_class:
        msg = f"Unsupported provider: {provider}"
        raise ValueError(msg)

    return client_class(api_key, model)

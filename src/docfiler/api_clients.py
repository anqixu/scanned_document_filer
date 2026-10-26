"""Unified client interface for VLM providers.

API providers (Claude, OpenAI, Gemini SDKs) need an API key. CLI providers
(`claude -p`, `codex exec`) shell out to locally installed, logged-in CLIs so a
Claude or ChatGPT subscription can be used instead of an API key.
"""

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import anthropic
from google import genai
from openai import OpenAI

from .config import API_KEY_ENV

logger = logging.getLogger(__name__)

CLI_TIMEOUT_S = 600


def classify_api_error(provider: str, exc: Exception) -> str:
    """Return a short, actionable error message for a provider exception."""
    s = str(exc)
    low = s.lower()

    if provider in API_KEY_ENV and any(
        x in s for x in ("401", "403", "invalid_api_key", "Unauthorized", "PERMISSION_DENIED", "API key not valid")
    ):
        return f"{provider}: invalid API key — check {API_KEY_ENV[provider]} in .env"

    if "not logged in" in low or "please run /login" in low or "codex login" in low:
        return f"{provider}: CLI is not logged in — run it once interactively to log in"

    if "400" in s and "usage limit" in low:
        m = re.search(r"regain access on ([^.'\"]+)", s)
        suffix = f" (access resumes {m.group(1).strip()})" if m else ""
        return f"{provider}: account spending limit reached{suffix}"

    if "429" in s or "quota" in low or "RESOURCE_EXHAUSTED" in s or "rate limit" in low:
        m = re.search(r"retry[^\d]*(\d+)\s*s", s, re.IGNORECASE)
        suffix = f" — retry in {m.group(1)}s" if m else ""
        return f"{provider}: quota/rate limit exceeded{suffix}"

    if any(x in low for x in ("connection", "timeout", "timed out", "network", "resolve", "unreachable")):
        return f"{provider}: network error or timeout — check internet connection"

    first_line = s.splitlines()[0] if s else type(exc).__name__
    return f"{provider}: {first_line[:150]}"


def parse_json_response(text: str | None) -> dict:
    """Extract a JSON object from a model response.

    Accepts bare JSON, JSON in a ``` fence, or JSON surrounded by prose.

    Raises:
        ValueError: If no JSON object can be parsed.
    """
    if not text or not text.strip():
        raise ValueError("Invalid JSON response: empty response")
    text = text.strip()

    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result

    logger.error(f"Failed to parse JSON response: {text}")
    raise ValueError(f"Invalid JSON response: {text[:200]}")


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


class VLMClient(ABC):
    """Base class: subclasses implement generate(); everything else builds on it."""

    name = "base"

    def __init__(self, api_key: str | None, model: str):
        self.model = model

    @abstractmethod
    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        """Send a prompt plus optional PNG images and return the text response."""

    def analyze_document(self, prompt: str, images: list[bytes], max_tokens: int = 4096) -> dict:
        """Send document images with a prompt and parse the JSON reply."""
        logger.info(f"Sending request to {self.name} ({self.model or 'default model'})")
        text = self.generate(prompt, images, max_tokens)
        logger.debug(f"{self.name} response: {text}")
        return parse_json_response(text)


class ClaudeClient(VLMClient):
    """Anthropic Messages API."""

    name = "claude"

    def __init__(self, api_key: str | None, model: str):
        super().__init__(api_key, model)
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(img)}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        # Thinking models may return thinking blocks before the text block.
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text:
            raise ValueError(f"claude: no text in response (stop_reason={response.stop_reason})")
        return text


class OpenAIClient(VLMClient):
    """OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, api_key: str | None, model: str):
        super().__init__(api_key, model)
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(img)}"}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            # max_tokens is deprecated and rejected by reasoning models (o-series, gpt-5).
            max_completion_tokens=max_tokens,
        )
        choice = response.choices[0]
        if not choice.message.content:
            raise ValueError(f"openai: empty response (finish_reason={choice.finish_reason})")
        return choice.message.content


class GeminiClient(VLMClient):
    """Google Gemini API."""

    name = "gemini"

    def __init__(self, api_key: str | None, model: str):
        super().__init__(api_key, model)
        self.client = genai.Client(api_key=api_key)

    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        parts = [genai.types.Part.from_bytes(data=img, mime_type="image/png") for img in images]
        parts.append(genai.types.Part.from_text(text=prompt))
        response = self.client.models.generate_content(
            model=self.model,
            contents=parts,
            config=genai.types.GenerateContentConfig(max_output_tokens=max_tokens),
        )
        # Thinking models can spend the whole token budget and return no text.
        if not response.text:
            raise ValueError("gemini: empty response (try raising VLM_MAX_TOKENS)")
        return response.text


class _CLIClient(VLMClient):
    """Runs a local CLI non-interactively, using the CLI's own login."""

    executable = ""
    # Removed from the child environment so the CLI uses its subscription login
    # instead of silently billing an API key loaded from .env.
    strip_env: tuple[str, ...] = ()

    def __init__(self, api_key: str | None, model: str):
        super().__init__(api_key, model)
        path = shutil.which(self.executable)
        if not path:
            raise ValueError(f"{self.name}: `{self.executable}` CLI not found on PATH")
        self.path = path

    def _run(self, args: list[str], stdin: str, cwd: str) -> str:
        env = {k: v for k, v in os.environ.items() if k not in self.strip_env}
        try:
            proc = subprocess.run(
                [self.path, *args],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=cwd,
                env=env,
                timeout=CLI_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"{self.name}: timed out after {CLI_TIMEOUT_S}s") from e
        if proc.returncode != 0:
            detail = (proc.stderr.strip() or proc.stdout.strip())[-500:]
            raise RuntimeError(f"{self.name} exited with code {proc.returncode}: {detail}")
        return proc.stdout


class ClaudeCLIClient(_CLIClient):
    """`claude -p` (Claude Code) with images sent inline via stream-json input.

    Tools are disabled, so this is a single model turn. max_tokens is not
    configurable through the CLI and is ignored.
    """

    name = "claude-cli"
    executable = "claude"
    strip_env = ("ANTHROPIC_API_KEY",)

    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(img)}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        message = {"type": "user", "message": {"role": "user", "content": content}}
        args = [
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--tools", "",
            "--no-session-persistence",
            "--strict-mcp-config",
        ]
        if self.model:
            args += ["--model", self.model]

        with tempfile.TemporaryDirectory(prefix="docfiler_") as tmp:
            stdout = self._run(args, json.dumps(message) + "\n", cwd=tmp)

        for line in reversed(stdout.splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                if event.get("is_error"):
                    raise RuntimeError(f"claude-cli: {event.get('result') or event.get('subtype')}")
                return event.get("result") or ""
        raise RuntimeError(f"claude-cli: no result in output: {stdout[-300:]}")


class CodexCLIClient(_CLIClient):
    """`codex exec` in a read-only sandbox, with images attached via --image."""

    name = "codex-cli"
    executable = "codex"
    strip_env = ("OPENAI_API_KEY", "CODEX_API_KEY")

    def generate(self, prompt: str, images: list[bytes], max_tokens: int) -> str:
        with tempfile.TemporaryDirectory(prefix="docfiler_") as tmp:
            tmp_dir = Path(tmp)
            out_file = tmp_dir / "last_message.txt"
            args = [
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--color", "never",
                "-s", "read-only",
                "-C", tmp,
                "-o", str(out_file),
            ]
            for i, img in enumerate(images):
                img_path = tmp_dir / f"page{i}.png"
                img_path.write_bytes(img)
                args.append(f"--image={img_path}")  # '=' form: one value per flag
            if self.model:
                args += ["-m", self.model]

            # No positional prompt: codex reads the prompt from stdin.
            stdout = self._run(args, prompt, cwd=tmp)
            return out_file.read_text(encoding="utf-8") if out_file.exists() else stdout


CLIENTS: dict[str, type[VLMClient]] = {
    "claude": ClaudeClient,
    "openai": OpenAIClient,
    "gemini": GeminiClient,
    "claude-cli": ClaudeCLIClient,
    "codex-cli": CodexCLIClient,
}


def create_client(provider: str, api_key: str | None, model: str) -> VLMClient:
    """Create the client for a provider.

    Raises:
        ValueError: If the provider is unsupported or its CLI is missing.
    """
    client_class = CLIENTS.get(provider.lower())
    if not client_class:
        raise ValueError(f"Unsupported provider: {provider}")
    return client_class(api_key, model)


def create_client_from_config(config) -> VLMClient:
    """Create the client for the config's active provider."""
    return create_client(config.vlm_provider, config.active_api_key, config.active_model)


def smoke_test(client: VLMClient) -> None:
    """Make a minimal call to verify credentials and connectivity.

    Raises:
        RuntimeError: With an actionable message if the call fails.
    """
    logger.info(f"Smoke-testing provider: {client.name} ({client.model or 'default model'})")
    try:
        client.generate("Reply with the single word OK.", [], 1024)
    except Exception as e:
        raise RuntimeError(classify_api_error(client.name, e)) from e
    logger.info("Provider smoke test passed.")

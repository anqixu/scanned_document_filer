"""Unit tests for API client module (no network, no real CLIs)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from docfiler.api_clients import (
    ClaudeCLIClient,
    ClaudeClient,
    CodexCLIClient,
    GeminiClient,
    OpenAIClient,
    classify_api_error,
    create_client,
    parse_json_response,
    smoke_test,
)

SUGGESTION = {"filename": "test.pdf", "destination": "docs", "confidence": 0.9, "reasoning": "r"}


class TestParseJsonResponse:
    @pytest.mark.parametrize(
        "text",
        [
            '{"filename": "test.pdf"}',
            '```json\n{"filename": "test.pdf"}\n```',
            '```JSON\n{"filename": "test.pdf"}```',
            'Here you go:\n```\n{"filename": "test.pdf"}\n```\nThanks',
            'Sure! {"filename": "test.pdf"} hope that helps',
        ],
    )
    def test_extracts_object(self, text):
        assert parse_json_response(text) == {"filename": "test.pdf"}

    @pytest.mark.parametrize("text", ["This is not JSON", "", None, "[1, 2]"])
    def test_invalid(self, text):
        with pytest.raises(ValueError, match="Invalid JSON response"):
            parse_json_response(text)


class TestApiClients:
    @patch("docfiler.api_clients.anthropic.Anthropic")
    def test_claude_skips_thinking_blocks(self, mock_anthropic):
        response = Mock(stop_reason="end_turn")
        response.content = [Mock(type="thinking"), Mock(type="text", text=json.dumps(SUGGESTION))]
        mock_anthropic.return_value.messages.create.return_value = response

        result = ClaudeClient("k", "claude-opus-5-5").analyze_document("prompt", [b"img"])

        assert result == SUGGESTION
        content = mock_anthropic.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
        assert [c["type"] for c in content] == ["image", "text"]

    @patch("docfiler.api_clients.anthropic.Anthropic")
    def test_claude_no_text_raises(self, mock_anthropic):
        response = Mock(stop_reason="max_tokens", content=[Mock(type="thinking")])
        mock_anthropic.return_value.messages.create.return_value = response
        with pytest.raises(ValueError, match="max_tokens"):
            ClaudeClient("k", "m").generate("p", [], 10)

    @patch("docfiler.api_clients.OpenAI")
    def test_openai_uses_max_completion_tokens(self, mock_openai):
        create = mock_openai.return_value.chat.completions.create
        create.return_value = Mock(choices=[Mock(message=Mock(content=json.dumps(SUGGESTION)))])

        assert OpenAIClient("k", "gpt-5").analyze_document("p", [b"img"], max_tokens=77) == SUGGESTION
        assert create.call_args.kwargs["max_completion_tokens"] == 77
        assert "max_tokens" not in create.call_args.kwargs

    @patch("docfiler.api_clients.genai")
    def test_gemini(self, mock_genai):
        mock_genai.Client.return_value.models.generate_content.return_value = Mock(text=json.dumps(SUGGESTION))
        assert GeminiClient("k", "gemini").analyze_document("p", [b"img"]) == SUGGESTION

    @patch("docfiler.api_clients.genai")
    def test_gemini_empty_raises(self, mock_genai):
        mock_genai.Client.return_value.models.generate_content.return_value = Mock(text=None)
        with pytest.raises(ValueError, match="empty response"):
            GeminiClient("k", "gemini").generate("p", [], 10)


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def cli_on_path():
    with patch("docfiler.api_clients.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
        yield


class TestClaudeCLIClient:
    def test_sends_images_inline_and_strips_api_key(self, cli_on_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
        stdout = "\n".join([
            json.dumps({"type": "system"}),
            json.dumps({"type": "result", "is_error": False, "result": json.dumps(SUGGESTION)}),
        ])
        with patch("docfiler.api_clients.subprocess.run", return_value=_completed(stdout)) as run:
            result = ClaudeCLIClient(None, "claude-sonnet-5-5").analyze_document("prompt", [b"img"])

        assert result == SUGGESTION
        args, kwargs = run.call_args
        cmd = args[0]
        assert cmd[0] == "/usr/bin/claude" and "-p" in cmd
        assert cmd[cmd.index("--tools") + 1] == ""
        assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
        assert "ANTHROPIC_API_KEY" not in kwargs["env"]
        message = json.loads(kwargs["input"])
        content = message["message"]["content"]
        assert content[0]["type"] == "image" and content[-1] == {"type": "text", "text": "prompt"}

    def test_no_model_flag_when_unset(self, cli_on_path):
        stdout = json.dumps({"type": "result", "is_error": False, "result": "OK"})
        with patch("docfiler.api_clients.subprocess.run", return_value=_completed(stdout)) as run:
            assert ClaudeCLIClient(None, "").generate("p", [], 10) == "OK"
        assert "--model" not in run.call_args.args[0]

    def test_error_result(self, cli_on_path):
        stdout = json.dumps({"type": "result", "is_error": True, "result": "Not logged in"})
        with patch("docfiler.api_clients.subprocess.run", return_value=_completed(stdout)):
            with pytest.raises(RuntimeError, match="Not logged in"):
                ClaudeCLIClient(None, "").generate("p", [], 10)

    def test_nonzero_exit(self, cli_on_path):
        with patch("docfiler.api_clients.subprocess.run", return_value=_completed(returncode=1, stderr="boom")):
            with pytest.raises(RuntimeError, match="code 1: boom"):
                ClaudeCLIClient(None, "").generate("p", [], 10)

    def test_missing_cli(self):
        with patch("docfiler.api_clients.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="not found on PATH"):
                ClaudeCLIClient(None, "")


class TestCodexCLIClient:
    def test_attaches_images_and_reads_last_message(self, cli_on_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "secret")
        seen = {}

        def fake_run(cmd, **kwargs):
            out = Path(cmd[cmd.index("-o") + 1])
            images = [Path(a.split("=", 1)[1]) for a in cmd if a.startswith("--image=")]
            seen.update(cmd=cmd, kwargs=kwargs, images=[p.read_bytes() for p in images])
            out.write_text(json.dumps(SUGGESTION))
            return _completed("noise")

        with patch("docfiler.api_clients.subprocess.run", side_effect=fake_run):
            result = CodexCLIClient(None, "gpt-5").analyze_document("prompt", [b"a", b"b"])

        assert result == SUGGESTION
        assert seen["images"] == [b"a", b"b"]
        cmd = seen["cmd"]
        assert cmd[:2] == ["/usr/bin/codex", "exec"]
        assert cmd[cmd.index("-s") + 1] == "read-only"
        assert cmd[cmd.index("-m") + 1] == "gpt-5"
        assert seen["kwargs"]["input"] == "prompt"
        assert "OPENAI_API_KEY" not in seen["kwargs"]["env"]

    def test_timeout(self, cli_on_path):
        with patch("docfiler.api_clients.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 1)):
            with pytest.raises(RuntimeError, match="timed out"):
                CodexCLIClient(None, "").generate("p", [], 10)


class TestFactoryAndErrors:
    @pytest.mark.parametrize(
        ("provider", "cls"),
        [("claude", ClaudeClient), ("openai", OpenAIClient), ("gemini", GeminiClient),
         ("claude-cli", ClaudeCLIClient), ("codex-cli", CodexCLIClient)],
    )
    def test_create_client(self, provider, cls, cli_on_path):
        assert isinstance(create_client(provider, "k", "m"), cls)

    def test_create_invalid_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_client("invalid", "k", "m")

    def test_classify_invalid_key_names_env_var(self):
        assert "ANTHROPIC_API_KEY" in classify_api_error("claude", Exception("Error code: 401"))

    def test_classify_cli_login(self):
        assert "log in" in classify_api_error("claude-cli", Exception("Not logged in · Please run /login"))

    def test_classify_fallback(self):
        assert classify_api_error("gemini", Exception("weird\nsecond")) == "gemini: weird"

    def test_smoke_test_wraps_errors(self):
        client = Mock(name="c", model="m")
        client.name = "claude-cli"
        client.generate.side_effect = RuntimeError("Not logged in")
        with pytest.raises(RuntimeError, match="not logged in"):
            smoke_test(client)

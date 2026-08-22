"""Tests for agent adapters with mocked HTTP endpoints."""
from __future__ import annotations

import pytest
import respx
from httpx import Response
from uuid import uuid4

from lead_hunter.adapters.openai_adapter import OpenAIAdapter
from lead_hunter.adapters.google_adapter import GoogleAdapter
from lead_hunter.adapters.moonshot_adapter import MoonshotAdapter
from lead_hunter.adapters.anthropic_adapter import AnthropicAdapter
from lead_hunter.adapters.factory import AgentAdapterFactory
from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import AgentResponseError, RetryExhaustedError
from lead_hunter.orchestrator.interfaces import AgentRequest, HealthStatus


def _make_request() -> AgentRequest:
    return AgentRequest(
        request_id=uuid4(),
        run_id=uuid4(),
        correlation_id=uuid4(),
        stage_id=uuid4(),
        agent_name="test",
        prompt="Research this company",
        context={},
    )


@pytest.mark.asyncio
class TestOpenAIAdapter:
    async def test_send_request_success(self) -> None:
        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=Response(200, json={
                    "choices": [{"message": {"content": '{"result": "ok"}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                })
            )
            adapter = OpenAIAdapter(AgentConfig(api_endpoint="https://api.openai.com/v1/chat/completions"))
            req = _make_request()
            resp = await adapter.send_request(req)
            assert resp.agent_name == "chatgpt"
            assert resp.content == '{"result": "ok"}'
            assert resp.usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            assert route.called

    async def test_parse_invalid_response(self) -> None:
        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=Response(200, json={"invalid": "structure"})
            )
            adapter = OpenAIAdapter(AgentConfig(api_endpoint="https://api.openai.com/v1/chat/completions"))
            with pytest.raises(AgentResponseError):
                await adapter.send_request(_make_request())

    async def test_health_check_healthy(self) -> None:
        import os
        os.environ["OPENAI_API_KEY"] = "test-key"
        with respx.mock:
            respx.get("https://api.openai.com/v1/models").mock(return_value=Response(200, json={}))
            adapter = OpenAIAdapter()
            status = await adapter.health_check()
            assert status == HealthStatus.HEALTHY

    async def test_health_check_no_key(self) -> None:
        import os
        key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            adapter = OpenAIAdapter()
            status = await adapter.health_check()
            assert status == HealthStatus.UNHEALTHY
        finally:
            if key:
                os.environ["OPENAI_API_KEY"] = key

    async def test_retry_on_500(self) -> None:
        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                side_effect=[
                    Response(500, text="Internal Server Error"),
                    Response(200, json={
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {},
                    }),
                ]
            )
            adapter = OpenAIAdapter(AgentConfig(
                api_endpoint="https://api.openai.com/v1/chat/completions",
                max_retries=2,
            ))
            resp = await adapter.send_request(_make_request())
            assert resp.content == "ok"
            assert route.call_count == 2

    async def test_max_retries_exhausted(self) -> None:
        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=Response(500, text="Error")
            )
            adapter = OpenAIAdapter(AgentConfig(
                api_endpoint="https://api.openai.com/v1/chat/completions",
                max_retries=1,
            ))
            with pytest.raises(RetryExhaustedError):
                await adapter.send_request(_make_request())


@pytest.mark.asyncio
class TestGoogleAdapter:
    async def test_send_request_success(self) -> None:
        with respx.mock:
            route = respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent").mock(
                return_value=Response(200, json={
                    "candidates": [{"content": {"parts": [{"text": '{"result": "ok"}' }]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30},
                })
            )
            adapter = GoogleAdapter()
            req = _make_request()
            resp = await adapter.send_request(req)
            assert resp.agent_name == "gemini"
            assert resp.content == '{"result": "ok"}'
            assert route.called

    async def test_no_candidates(self) -> None:
        with respx.mock:
            respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent").mock(
                return_value=Response(200, json={"candidates": []})
            )
            adapter = GoogleAdapter()
            with pytest.raises(AgentResponseError, match="No candidates"):
                await adapter.send_request(_make_request())


@pytest.mark.asyncio
class TestMoonshotAdapter:
    async def test_send_request_success(self) -> None:
        with respx.mock:
            route = respx.post("https://api.moonshot.cn/v1/chat/completions").mock(
                return_value=Response(200, json={
                    "choices": [{"message": {"content": "Moonshot result"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
                })
            )
            adapter = MoonshotAdapter()
            req = _make_request()
            resp = await adapter.send_request(req)
            assert resp.agent_name == "kimi"
            assert resp.content == "Moonshot result"
            assert route.called


@pytest.mark.asyncio
class TestAnthropicAdapter:
    async def test_send_request_success(self) -> None:
        with respx.mock:
            route = respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=Response(200, json={
                    "content": [{"text": "Claude result"}],
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                })
            )
            adapter = AnthropicAdapter()
            req = _make_request()
            resp = await adapter.send_request(req)
            assert resp.agent_name == "claude"
            assert resp.content == "Claude result"
            assert resp.usage["prompt_tokens"] == 10
            assert resp.usage["completion_tokens"] == 20
            assert route.called

    async def test_no_content_blocks(self) -> None:
        with respx.mock:
            respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=Response(200, json={"content": []})
            )
            adapter = AnthropicAdapter()
            with pytest.raises(AgentResponseError, match="No content blocks"):
                await adapter.send_request(_make_request())


class TestAgentAdapterFactory:
    def test_create_openai(self) -> None:
        adapter = AgentAdapterFactory.create("chatgpt")
        assert adapter.get_name() == "chatgpt"

    def test_create_google(self) -> None:
        adapter = AgentAdapterFactory.create("gemini")
        assert adapter.get_name() == "gemini"

    def test_create_moonshot(self) -> None:
        adapter = AgentAdapterFactory.create("kimi")
        assert adapter.get_name() == "kimi"

    def test_create_anthropic(self) -> None:
        adapter = AgentAdapterFactory.create("claude")
        assert adapter.get_name() == "claude"

    def test_create_unknown_raises(self) -> None:
        from lead_hunter.exceptions import ConfigurationError
        with pytest.raises(ConfigurationError, match="Unknown agent adapter"):
            AgentAdapterFactory.create("unknown")

    def test_list_adapters(self) -> None:
        names = AgentAdapterFactory.list_adapters()
        assert "chatgpt" in names
        assert "gemini" in names
        assert "kimi" in names
        assert "claude" in names

    def test_register_custom(self) -> None:
        class CustomAdapter(OpenAIAdapter):
            def get_name(self) -> str:
                return "custom"
        AgentAdapterFactory.register("custom", CustomAdapter)
        adapter = AgentAdapterFactory.create("custom")
        assert adapter.get_name() == "custom"

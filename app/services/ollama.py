import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings

HEADERS = {"Authorization": f"Bearer {settings.ollama_api_key}"}


async def get_models() -> dict:
    url = f"{settings.ollama_endpoint.rstrip('/')}/api/tags"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def generate(body: dict) -> dict:
    url = f"{settings.ollama_endpoint.rstrip('/')}/api/generate"
    body = {**body, "stream": False}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=HEADERS, timeout=300)
        resp.raise_for_status()
        # Ollama may still return NDJSON for some models; parse accordingly
        text = resp.text.strip()
        if "\n" in text:
            # NDJSON — concatenate response tokens and return final object
            full_response = ""
            final_obj = {}
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                full_response += obj.get("response", "")
                if obj.get("done"):
                    final_obj = obj
            if final_obj:
                final_obj["response"] = full_response
                return final_obj
        return resp.json()


async def stream_generate(body: dict) -> AsyncIterator[bytes]:
    url = f"{settings.ollama_endpoint.rstrip('/')}/api/generate"
    body = {**body, "stream": True}
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, json=body, headers=HEADERS, timeout=300) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                yield chunk


async def stream_chat(
    messages: list[dict], model: str | None = None
) -> AsyncIterator[str]:
    """Stream chat responses from Ollama /api/chat, yielding text tokens."""
    url = f"{settings.ollama_endpoint.rstrip('/')}/api/chat"
    body = {"model": model or settings.ollama_chat_model, "messages": messages, "stream": True}
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, json=body, headers=HEADERS, timeout=300) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                content = obj.get("message", {}).get("content", "")
                if content:
                    yield content


async def chat(messages: list[dict], model: str | None = None) -> str:
    """Non-streaming chat completion. Returns the full assistant message."""
    url = f"{settings.ollama_endpoint.rstrip('/')}/api/chat"
    body = {
        "model": model or settings.ollama_chat_model,
        "messages": messages,
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=HEADERS, timeout=300)
        resp.raise_for_status()
        text = resp.text.strip()
        if "\n" in text:
            full_content = ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                msg = obj.get("message", {}).get("content", "")
                full_content += msg
                if obj.get("done"):
                    return full_content
            return full_content
        data = resp.json()
        return data.get("message", {}).get("content", "")


async def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    base_url = settings.ollama_embedding_endpoint or settings.ollama_endpoint
    url = f"{base_url.rstrip('/')}/api/embed"
    body = {"model": model or settings.ollama_embedding_model, "input": texts}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        return resp.json()["embeddings"]
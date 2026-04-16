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
import asyncio

import cachecontrol
import google.auth.transport.requests
import google.oauth2.id_token
import requests

from app.config import settings

_session = cachecontrol.CacheControl(requests.Session())
_request = google.auth.transport.requests.Request(session=_session)


async def verify_google_token(token: str) -> dict:
    def _verify():
        return google.oauth2.id_token.verify_oauth2_token(
            token,
            _request,
            settings.google_client_id,
        )

    return await asyncio.to_thread(_verify)
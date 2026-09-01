import asyncio
import logging
import time
from typing import Any

import aiohttp


logger = logging.getLogger(__name__)

_ALLOWED_DAY_OFFSETS = (0, 1, 2)
_DAILY_FIELDS = (
    "date",
    "week",
    "war",
    "battle",
    "orecar",
    "rescue",
    "card",
    "school",
    "lucky",
    "weekly",
)


class JX3APIServiceError(RuntimeError):
    """A controlled JX3API failure safe to expose through an LLM tool."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JX3APIService:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        base_url: str,
        token: str = "",
        ticket: str = "",
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._ticket = ticket

    async def get_daily(self, day_offset: int) -> dict[str, Any]:
        if type(day_offset) is not int or day_offset not in _ALLOWED_DAY_OFFSETS:
            raise JX3APIServiceError("invalid_day_offset")

        payload: dict[str, Any] = {"num": day_offset, "mode": "day"}

        started_at = time.perf_counter()
        try:
            async with self._session.post(
                f"{self._base_url}/active/calendar", json=payload
            ) as response:
                self._raise_for_http_status(response.status)
                try:
                    body = await response.json()
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise JX3APIServiceError("jx3api_invalid_json") from exc
        except asyncio.TimeoutError as exc:
            logger.warning("tool=jx3_daily status=timeout")
            raise JX3APIServiceError("jx3api_timeout") from exc
        except aiohttp.ClientConnectionError as exc:
            logger.warning("tool=jx3_daily status=connection_error")
            raise JX3APIServiceError("jx3api_connection_error") from exc
        except aiohttp.ClientError as exc:
            logger.warning("tool=jx3_daily status=connection_error")
            raise JX3APIServiceError("jx3api_connection_error") from exc

        data = self._extract_daily_data(body)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        logger.info("tool=jx3_daily status=success latency_ms=%d", latency_ms)
        return data

    @staticmethod
    def _raise_for_http_status(status: int) -> None:
        if status == 429:
            raise JX3APIServiceError("jx3api_rate_limited")
        if 400 <= status < 500:
            raise JX3APIServiceError("jx3api_http_4xx")
        if status >= 500:
            raise JX3APIServiceError("jx3api_upstream_error")

    @staticmethod
    def _extract_daily_data(body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise JX3APIServiceError("jx3api_invalid_response")
        if body.get("code") != 200:
            raise JX3APIServiceError("jx3api_api_error")

        data = body.get("data")
        if not data:
            raise JX3APIServiceError("jx3api_empty_data")
        if not isinstance(data, dict):
            raise JX3APIServiceError("jx3api_invalid_response")

        for field_name in ("date", "war"):
            if not isinstance(data.get(field_name), str) or not data[field_name]:
                raise JX3APIServiceError("jx3api_invalid_response")

        return {field: data[field] for field in _DAILY_FIELDS if field in data}

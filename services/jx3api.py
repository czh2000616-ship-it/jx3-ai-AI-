import asyncio
import logging
import time
from collections.abc import Callable
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
_ROLE_FIELDS = {
    "server": "serverName",
    "zone": "zoneName",
    "role_name": "roleName",
    "role_id": "roleId",
    "global_id": "globalId",
    "force_name": "forceName",
    "body_name": "bodyName",
    "tong_name": "tongName",
    "camp_name": "campName",
}
_CONNECTION_RETRY_DELAY_SECONDS = 0.3
_ARENA_MODES = ("33", "22", "55")
_ARENA_PERFORMANCE_KEYS = {"33": "3v3", "22": "2v2", "55": "5v5"}


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

    async def get_role(self, server: str, role_name: str) -> dict[str, Any]:
        if not isinstance(server, str) or not server.strip():
            raise JX3APIServiceError("missing_server")
        if not isinstance(role_name, str) or not role_name.strip():
            raise JX3APIServiceError("invalid_role_name")
        if not isinstance(self._token, str) or not self._token.strip():
            raise JX3APIServiceError("jx3api_token_missing")

        params: dict[str, Any] = {
            "server": server.strip(),
            "name": role_name.strip(),
            "history": 1,
            "token": self._token.strip(),
        }

        started_at = time.perf_counter()
        body = await self._request_get_json(
            "/role/detail",
            params,
            tool="jx3_role",
            status_handler=self._raise_for_http_status,
        )

        data = self._extract_role_data(body)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        logger.info("tool=jx3_role status=success latency_ms=%d", latency_ms)
        return data

    async def get_arena(self, server: str, role_name: str) -> dict[str, Any]:
        if not isinstance(server, str) or not server.strip():
            raise JX3APIServiceError("missing_server")
        if not isinstance(role_name, str) or not role_name.strip():
            raise JX3APIServiceError("invalid_role_name")
        if not isinstance(self._token, str) or not self._token.strip():
            raise JX3APIServiceError("jx3api_token_missing")
        if not isinstance(self._ticket, str) or not self._ticket.strip():
            raise JX3APIServiceError("jx3api_ticket_missing")

        normalized_server = server.strip()
        normalized_role_name = role_name.strip()
        started_at = time.perf_counter()

        mode_results = await asyncio.gather(
            *(
                self._get_arena_mode(
                    normalized_server,
                    normalized_role_name,
                    mode,
                )
                for mode in _ARENA_MODES
            )
        )
        modes = {
            _ARENA_PERFORMANCE_KEYS[mode]: result
            for mode, result in zip(_ARENA_MODES, mode_results)
        }

        if all(
            result.get("error") == "jx3api_auth_error" for result in mode_results
        ):
            raise JX3APIServiceError("jx3api_auth_error")

        latency_ms = round((time.perf_counter() - started_at) * 1000)
        successful_modes = sum(result["ok"] for result in mode_results)
        status = "success" if successful_modes == len(_ARENA_MODES) else "partial"
        logger.info(
            "tool=jx3_arena status=%s succeeded=%d failed=%d latency_ms=%d",
            status,
            successful_modes,
            len(_ARENA_MODES) - successful_modes,
            latency_ms,
        )
        return {
            "server": normalized_server,
            "role_name": normalized_role_name,
            "modes": modes,
        }

    async def _get_arena_mode(
        self,
        server: str,
        role_name: str,
        mode: str,
    ) -> dict[str, Any]:
        params = {
            "server": server,
            "name": role_name,
            "mode": mode,
            "token": self._token.strip(),
            "ticket": self._ticket.strip(),
        }

        try:
            body = await self._request_get_json(
                "/arena/recent",
                params,
                tool="jx3_arena",
                mode=mode,
                status_handler=self._raise_for_arena_http_status,
            )
            data = self._extract_arena_mode(body, mode)
        except JX3APIServiceError as exc:
            logger.warning(
                "tool=jx3_arena status=mode_error mode=%s error=%s",
                mode,
                exc.code,
            )
            return {"ok": False, "error": exc.code}

        return {"ok": True, **data}

    async def _request_get_json(
        self,
        path: str,
        params: dict[str, Any],
        *,
        tool: str,
        status_handler: Callable[[int], None],
        mode: str | None = None,
    ) -> Any:
        mode_log = "" if mode is None else f" mode={mode}"
        for attempt in range(2):
            try:
                async with self._session.get(
                    f"{self._base_url}{path}", params=params
                ) as response:
                    status_handler(response.status)
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        raise JX3APIServiceError("jx3api_invalid_json") from None
            except asyncio.TimeoutError:
                logger.warning("tool=%s status=timeout%s", tool, mode_log)
                raise JX3APIServiceError("jx3api_timeout") from None
            except aiohttp.ClientConnectionError:
                if attempt == 0:
                    logger.warning(
                        "tool=%s status=connection_retry%s attempt=1",
                        tool,
                        mode_log,
                    )
                    await asyncio.sleep(_CONNECTION_RETRY_DELAY_SECONDS)
                    continue
                logger.warning("tool=%s status=connection_error%s", tool, mode_log)
                raise JX3APIServiceError("jx3api_connection_error") from None
            except aiohttp.ClientError:
                logger.warning("tool=%s status=connection_error%s", tool, mode_log)
                raise JX3APIServiceError("jx3api_connection_error") from None

        raise AssertionError("unreachable")

    @staticmethod
    def _raise_for_http_status(status: int) -> None:
        if status == 429:
            raise JX3APIServiceError("jx3api_rate_limited")
        if 400 <= status < 500:
            raise JX3APIServiceError("jx3api_http_4xx")
        if status >= 500:
            raise JX3APIServiceError("jx3api_upstream_error")

    @staticmethod
    def _raise_for_arena_http_status(status: int) -> None:
        if status in (401, 403):
            raise JX3APIServiceError("jx3api_auth_error")
        JX3APIService._raise_for_http_status(status)

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

    @staticmethod
    def _extract_role_data(body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise JX3APIServiceError("jx3api_invalid_response")
        if body.get("code") != 200:
            raise JX3APIServiceError("jx3api_api_error")

        data = body.get("data")
        if not data:
            raise JX3APIServiceError("jx3api_empty_data")
        if not isinstance(data, dict):
            raise JX3APIServiceError("jx3api_invalid_response")

        for field_name in ("serverName", "roleName"):
            if not isinstance(data.get(field_name), str) or not data[field_name]:
                raise JX3APIServiceError("jx3api_invalid_response")

        result = {
            result_field: data[api_field]
            for result_field, api_field in _ROLE_FIELDS.items()
            if api_field in data
        }

        if "roleHistory" in data:
            role_history = data.get("roleHistory") or {}
            if not isinstance(role_history, dict):
                raise JX3APIServiceError("jx3api_invalid_response")
            result["role_history"] = JX3APIService._extract_history_items(
                role_history.get("roleNames"), name_field="role_name"
            )
            result["tong_history"] = JX3APIService._extract_history_items(
                role_history.get("TongNames"), name_field="tong_name"
            )

        return result

    @staticmethod
    def _extract_arena_mode(body: Any, mode: str) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise JX3APIServiceError("jx3api_invalid_response")
        if body.get("code") in (401, 403):
            raise JX3APIServiceError("jx3api_auth_error")
        if body.get("code") != 200:
            raise JX3APIServiceError("jx3api_api_error")

        data = body.get("data")
        if not data:
            raise JX3APIServiceError("jx3api_empty_data")
        if not isinstance(data, dict):
            raise JX3APIServiceError("jx3api_invalid_response")

        performance = data.get("performance")
        if not isinstance(performance, dict):
            raise JX3APIServiceError("jx3api_invalid_response")
        mode_performance = performance.get(_ARENA_PERFORMANCE_KEYS[mode])
        if not isinstance(mode_performance, (dict, list)):
            raise JX3APIServiceError("jx3api_invalid_response")

        history = data.get("history")
        if history is None:
            history = []
        if not isinstance(history, list):
            raise JX3APIServiceError("jx3api_invalid_response")

        return {"performance": mode_performance, "history": history}

    @staticmethod
    def _extract_history_items(items: Any, *, name_field: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue

            normalized: dict[str, Any] = {name_field: name}
            if isinstance(item.get("server"), str) and item["server"]:
                normalized["server"] = item["server"]
            if "time" in item:
                normalized["time"] = item["time"]
            result.append(normalized)

        return result

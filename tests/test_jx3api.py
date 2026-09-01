import asyncio
import json
import sys
import types
import unittest


try:
    import aiohttp  # type: ignore[import-not-found]
except ModuleNotFoundError:
    aiohttp = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientConnectionError(ClientError):
        pass

    class ContentTypeError(ClientError):
        pass

    aiohttp.ClientError = ClientError
    aiohttp.ClientConnectionError = ClientConnectionError
    aiohttp.ContentTypeError = ContentTypeError
    aiohttp.ClientSession = object
    sys.modules["aiohttp"] = aiohttp

from services.jx3api import JX3APIService, JX3APIServiceError


VALID_DATA = {
    "date": "2026-09-02",
    "week": "三",
    "war": "大战！英雄不染窟",
    "battle": "雪域关城",
    "orecar": "跨服·河西瀚漠",
    "rescue": "七秀·乱世",
    "card": ["英雄灵霄峡", "英雄天工坊", "英雄无盐岛"],
    "school": "明教·漫漫朝圣路",
    "lucky": ["沉溪", "蟹负", "蟹胜"],
    "weekly": {
        "conn": ["经首道源·越海珠贝"],
        "raid": ["阆风悬城"],
    },
}


class FakeResponse:
    def __init__(self, *, status=200, payload=None, json_error=None):
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeRequestContext:
    def __init__(self, *, response=None, error=None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._response

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self, *, response=None, error=None):
        self._response = response
        self._error = error
        self.requests = []

    def post(self, url, *, json):
        self.requests.append({"url": url, "json": json})
        return FakeRequestContext(response=self._response, error=self._error)


class JX3APIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_daily_returns_normalized_data_and_sends_expected_request(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": VALID_DATA}
            )
        )
        service = JX3APIService(session, base_url="https://example.invalid/")

        result = await service.get_daily(1)

        self.assertEqual(result, VALID_DATA)
        self.assertEqual(
            session.requests,
            [
                {
                    "url": "https://example.invalid/active/calendar",
                    "json": {"num": 1, "mode": "day"},
                }
            ],
        )

    async def test_get_daily_accepts_offsets_zero_one_and_two(self):
        for day_offset in (0, 1, 2):
            with self.subTest(day_offset=day_offset):
                session = FakeSession(
                    response=FakeResponse(
                        payload={"code": 200, "msg": "success", "data": VALID_DATA}
                    )
                )
                service = JX3APIService(session, base_url="https://example.invalid")

                await service.get_daily(day_offset)

                self.assertEqual(session.requests[0]["json"]["num"], day_offset)

    async def test_get_daily_rejects_invalid_offsets(self):
        invalid_offsets = (-1, 3, "1", True, None)
        session = FakeSession()
        service = JX3APIService(session, base_url="https://example.invalid")

        for day_offset in invalid_offsets:
            with self.subTest(day_offset=day_offset):
                with self.assertRaisesRegex(
                    JX3APIServiceError, "invalid_day_offset"
                ):
                    await service.get_daily(day_offset)

        self.assertEqual(session.requests, [])

    async def test_get_daily_maps_timeout(self):
        service = JX3APIService(
            FakeSession(error=asyncio.TimeoutError()),
            base_url="https://example.invalid",
        )

        await self._assert_error(service, "jx3api_timeout")

    async def test_get_daily_maps_connection_error(self):
        service = JX3APIService(
            FakeSession(error=aiohttp.ClientConnectionError()),
            base_url="https://example.invalid",
        )

        await self._assert_error(service, "jx3api_connection_error")

    async def test_get_daily_maps_http_4xx(self):
        service = self._service_for_response(FakeResponse(status=400))

        await self._assert_error(service, "jx3api_http_4xx")

    async def test_get_daily_maps_http_429(self):
        service = self._service_for_response(FakeResponse(status=429))

        await self._assert_error(service, "jx3api_rate_limited")

    async def test_get_daily_maps_http_5xx(self):
        service = self._service_for_response(FakeResponse(status=503))

        await self._assert_error(service, "jx3api_upstream_error")

    async def test_get_daily_rejects_non_json_response(self):
        service = self._service_for_response(FakeResponse(json_error=ValueError()))

        await self._assert_error(service, "jx3api_invalid_json")

    async def test_get_daily_rejects_api_defined_failure(self):
        service = self._service_for_response(
            FakeResponse(payload={"code": 500, "msg": "failed", "data": {}})
        )

        await self._assert_error(service, "jx3api_api_error")

    async def test_get_daily_rejects_empty_data(self):
        service = self._service_for_response(
            FakeResponse(payload={"code": 200, "msg": "success", "data": {}})
        )

        await self._assert_error(service, "jx3api_empty_data")

    async def test_get_daily_rejects_missing_required_fields(self):
        for missing_field in ("date", "war"):
            with self.subTest(missing_field=missing_field):
                data = dict(VALID_DATA)
                data.pop(missing_field)
                service = self._service_for_response(
                    FakeResponse(
                        payload={"code": 200, "msg": "success", "data": data}
                    )
                )

                await self._assert_error(service, "jx3api_invalid_response")

    async def test_get_daily_rejects_json_with_wrong_root_type(self):
        service = self._service_for_response(FakeResponse(payload=[]))

        await self._assert_error(service, "jx3api_invalid_response")

    async def test_get_daily_omits_configured_credentials(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": VALID_DATA}
            )
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="configured-token",
            ticket="configured-ticket",
        )

        with self.assertLogs("services.jx3api", level="INFO") as captured:
            await service.get_daily(0)

        self.assertEqual(
            session.requests[0]["json"],
            {"num": 0, "mode": "day"},
        )
        logs = "\n".join(captured.output)
        self.assertNotIn("configured-token", logs)
        self.assertNotIn("configured-ticket", logs)

    @staticmethod
    def _service_for_response(response):
        return JX3APIService(
            FakeSession(response=response), base_url="https://example.invalid"
        )

    async def _assert_error(self, service, expected_code):
        with self.assertRaises(JX3APIServiceError) as raised:
            await service.get_daily(0)
        self.assertEqual(raised.exception.code, expected_code)


if __name__ == "__main__":
    unittest.main()

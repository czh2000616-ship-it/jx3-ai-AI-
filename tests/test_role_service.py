import asyncio
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


VALID_ROLE_DATA = {
    "zoneName": "电信五区",
    "serverName": "梦江南",
    "roleName": "张三",
    "roleId": "123456",
    "globalId": "987654",
    "forceName": "万花",
    "bodyName": "成年男性",
    "tongName": "测试帮会",
    "campName": "浩气盟",
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
    def __init__(self, *, response=None, error=None, outcomes=None):
        self._response = response
        self._error = error
        self._outcomes = list(outcomes) if outcomes is not None else None
        self.requests = []

    def get(self, url, *, params):
        self.requests.append({"url": url, "params": params})
        if self._outcomes is not None:
            if not self._outcomes:
                raise AssertionError("unexpected extra HTTP request")
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, BaseException):
                return FakeRequestContext(error=outcome)
            return FakeRequestContext(response=outcome)
        return FakeRequestContext(response=self._response, error=self._error)


class JX3APIRoleServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_role_returns_normalized_data_and_sends_expected_request(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": VALID_ROLE_DATA}
            )
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid/",
            token="unit-test-token",
            ticket="unit-test-ticket",
        )

        with self.assertLogs("services.jx3api", level="INFO") as captured:
            result = await service.get_role("梦江南", "张三")

        self.assertEqual(
            result,
            {
                "server": "梦江南",
                "zone": "电信五区",
                "role_name": "张三",
                "role_id": "123456",
                "global_id": "987654",
                "force_name": "万花",
                "body_name": "成年男性",
                "tong_name": "测试帮会",
                "camp_name": "浩气盟",
            },
        )
        self.assertEqual(
            session.requests,
            [
                {
                    "url": "https://example.invalid/role/detail",
                    "params": {
                        "server": "梦江南",
                        "name": "张三",
                        "history": 1,
                        "token": "unit-test-token",
                    },
                }
            ],
        )
        logs = "\n".join(captured.output)
        self.assertNotIn("unit-test-token", logs)
        self.assertNotIn("unit-test-ticket", logs)

    async def test_get_role_strips_inputs_without_rewriting_role_name(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": VALID_ROLE_DATA}
            )
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

        await service.get_role("  梦江南  ", "  张三·测试  ")

        self.assertEqual(session.requests[0]["params"]["server"], "梦江南")
        self.assertEqual(session.requests[0]["params"]["name"], "张三·测试")

    async def test_get_role_rejects_invalid_server_without_request(self):
        for server in ("", "   ", None, 123, True):
            with self.subTest(server=server):
                session = FakeSession()
                service = JX3APIService(
                    session,
                    base_url="https://example.invalid",
                    token="unit-test-token",
                )

                await self._assert_error(
                    service.get_role(server, "张三"), "missing_server"
                )

                self.assertEqual(session.requests, [])

    async def test_get_role_rejects_invalid_role_name_without_request(self):
        for role_name in ("", "   ", None, 123, True):
            with self.subTest(role_name=role_name):
                session = FakeSession()
                service = JX3APIService(
                    session,
                    base_url="https://example.invalid",
                    token="unit-test-token",
                )

                await self._assert_error(
                    service.get_role("梦江南", role_name), "invalid_role_name"
                )

                self.assertEqual(session.requests, [])

    async def test_get_role_rejects_missing_token_without_request(self):
        for token in ("", "   ", None, 123, True):
            with self.subTest(token=token):
                session = FakeSession()
                service = JX3APIService(
                    session,
                    base_url="https://example.invalid",
                    token=token,
                )

                await self._assert_error(
                    service.get_role("梦江南", "张三"), "jx3api_token_missing"
                )

                self.assertEqual(session.requests, [])

    async def test_get_role_maps_timeout(self):
        session = FakeSession(error=asyncio.TimeoutError())
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_timeout"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_maps_two_connection_errors_without_third_request(self):
        session = FakeSession(
            outcomes=[
                aiohttp.ClientConnectionError(),
                aiohttp.ClientConnectionError(),
            ]
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_connection_error"
        )
        self.assertEqual(len(session.requests), 2)

    async def test_get_role_retries_one_connection_error_then_returns_success(self):
        session = FakeSession(
            outcomes=[
                aiohttp.ClientConnectionError(),
                FakeResponse(
                    payload={"code": 200, "msg": "success", "data": VALID_ROLE_DATA}
                ),
            ]
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

        with self.assertLogs("services.jx3api", level="INFO") as captured:
            result = await service.get_role("梦江南", "张三")

        self.assertEqual(result["role_name"], "张三")
        self.assertEqual(len(session.requests), 2)
        logs = "\n".join(captured.output)
        self.assertIn("tool=jx3_role status=connection_retry attempt=1", logs)
        self.assertNotIn("unit-test-token", logs)

    async def test_get_role_does_not_retry_other_client_errors(self):
        class NonConnectionClientError(aiohttp.ClientError):
            pass

        session = FakeSession(outcomes=[NonConnectionClientError()])
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_connection_error"
        )

        self.assertEqual(len(session.requests), 1)

    async def test_get_role_maps_http_429(self):
        session = FakeSession(response=FakeResponse(status=429))
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_rate_limited"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_maps_http_4xx(self):
        session = FakeSession(response=FakeResponse(status=400))
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_http_4xx"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_maps_http_5xx(self):
        session = FakeSession(response=FakeResponse(status=503))
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_upstream_error"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_rejects_non_json_response(self):
        session = FakeSession(response=FakeResponse(json_error=ValueError()))
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_invalid_json"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_rejects_api_defined_failure(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 500, "msg": "failed", "data": {}}
            )
        )
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_api_error"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_rejects_empty_data(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": {}}
            )
        )
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_empty_data"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_rejects_data_with_wrong_type(self):
        session = FakeSession(
            response=FakeResponse(
                payload={"code": 200, "msg": "success", "data": ["unexpected"]}
            )
        )
        service = self._service_for_session(session)

        await self._assert_error(
            service.get_role("梦江南", "张三"), "jx3api_invalid_response"
        )
        self.assertEqual(len(session.requests), 1)

    async def test_get_role_rejects_missing_required_fields(self):
        for missing_field in ("serverName", "roleName"):
            with self.subTest(missing_field=missing_field):
                data = dict(VALID_ROLE_DATA)
                data.pop(missing_field)
                session = FakeSession(
                    response=FakeResponse(
                        payload={"code": 200, "msg": "success", "data": data}
                    )
                )
                service = self._service_for_session(session)

                await self._assert_error(
                    service.get_role("梦江南", "张三"),
                    "jx3api_invalid_response",
                )
                self.assertEqual(len(session.requests), 1)

    async def test_get_role_parses_role_and_tong_history(self):
        data = {
            **VALID_ROLE_DATA,
            "roleHistory": {
                "roleNames": [
                    {"server": "梦江南", "name": "旧角色名", "time": 1720000000},
                    {"server": "梦江南", "name": "", "time": 1710000000},
                ],
                "TongNames": [
                    {"server": "梦江南", "name": "旧帮会", "time": 1700000000}
                ],
            },
        }
        service = self._service_for_response(
            FakeResponse(payload={"code": 200, "msg": "success", "data": data})
        )

        result = await service.get_role("梦江南", "张三")

        self.assertEqual(
            result["role_history"],
            [
                {
                    "server": "梦江南",
                    "role_name": "旧角色名",
                    "time": 1720000000,
                }
            ],
        )
        self.assertEqual(
            result["tong_history"],
            [
                {
                    "server": "梦江南",
                    "tong_name": "旧帮会",
                    "time": 1700000000,
                }
            ],
        )

    @staticmethod
    def _service_for_response(response):
        return JX3APIRoleServiceTests._service_for_session(
            FakeSession(response=response)
        )

    @staticmethod
    def _service_for_session(session):
        return JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
        )

    async def _assert_error(self, operation, expected_code):
        with self.assertRaises(JX3APIServiceError) as raised:
            await operation
        self.assertEqual(raised.exception.code, expected_code)


if __name__ == "__main__":
    unittest.main()

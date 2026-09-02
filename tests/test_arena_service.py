import asyncio
import sys
import types
import unittest
from unittest.mock import patch


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
    def __init__(self, outcome):
        self.outcome = outcome

    async def __aenter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = (
            {mode: list(mode_outcomes) for mode, mode_outcomes in outcomes.items()}
            if isinstance(outcomes, dict)
            else list(outcomes)
        )
        self.requests = []

    def get(self, url, *, params):
        self.requests.append({"url": url, "params": params})
        if isinstance(self.outcomes, dict):
            mode_outcomes = self.outcomes.get(params["mode"], [])
            if not mode_outcomes:
                raise AssertionError("unexpected extra HTTP request")
            outcome = mode_outcomes.pop(0)
        else:
            if not self.outcomes:
                raise AssertionError("unexpected extra HTTP request")
            outcome = self.outcomes.pop(0)
        return FakeRequestContext(outcome)


class ConcurrentRequestContext(FakeRequestContext):
    def __init__(self, outcome, mode, started_modes, all_started):
        super().__init__(outcome)
        self.mode = mode
        self.started_modes = started_modes
        self.all_started = all_started

    async def __aenter__(self):
        self.started_modes.add(self.mode)
        if len(self.started_modes) == 3:
            self.all_started.set()
        await self.all_started.wait()
        return await super().__aenter__()


class ConcurrentFakeSession(FakeSession):
    def __init__(self, outcomes):
        super().__init__(outcomes)
        self.started_modes = set()
        self.all_started = asyncio.Event()

    def get(self, url, *, params):
        context = super().get(url, params=params)
        return ConcurrentRequestContext(
            context.outcome,
            params["mode"],
            self.started_modes,
            self.all_started,
        )


def arena_response(mode):
    mode_key = {"33": "3v3", "22": "2v2", "55": "5v5"}[mode]
    return FakeResponse(
        payload={
            "code": 200,
            "msg": "success",
            "data": {
                "zoneName": "电信五区",
                "serverName": "梦江南",
                "roleName": "哇偶",
                "forceName": "万花",
                "performance": {
                    mode_key: {
                        "mmr": 2300,
                        "grade": 12,
                        "ranking": "100",
                        "winCount": 10,
                        "totalCount": 20,
                        "mvpCount": 3,
                        "pvpType": mode_key,
                        "winRate": 0.5,
                    }
                },
                "history": [
                    {
                        "server": "梦江南",
                        "mmr": 2300,
                        "kungfu": "花间游",
                        "pvpType": int(mode[0]),
                        "won": True,
                        "mvp": False,
                        "startTime": 1788319000,
                        "endTime": 1788319300,
                    }
                ],
            },
        }
    )


class JX3APIArenaServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_arena_queries_three_modes_concurrently_and_aggregates(self):
        session = ConcurrentFakeSession(
            {
                "33": [arena_response("33")],
                "22": [arena_response("22")],
                "55": [arena_response("55")],
            }
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid/",
            token="unit-test-token",
            ticket="unit-test-ticket",
        )

        with self.assertLogs("services.jx3api", level="INFO") as captured:
            result = await asyncio.wait_for(
                service.get_arena("梦江南", "哇偶"), timeout=1
            )

        self.assertEqual(session.started_modes, {"33", "22", "55"})
        self.assertEqual(result["server"], "梦江南")
        self.assertEqual(result["role_name"], "哇偶")
        self.assertEqual(list(result["modes"]), ["3v3", "2v2", "5v5"])
        self.assertTrue(result["modes"]["3v3"]["ok"])
        self.assertEqual(result["modes"]["3v3"]["performance"]["mmr"], 2300)
        self.assertEqual(
            [request["params"]["mode"] for request in session.requests],
            ["33", "22", "55"],
        )
        for request in session.requests:
            self.assertEqual(request["url"], "https://example.invalid/arena/recent")
            self.assertEqual(
                request["params"],
                {
                    "server": "梦江南",
                    "name": "哇偶",
                    "mode": request["params"]["mode"],
                    "token": "unit-test-token",
                    "ticket": "unit-test-ticket",
                },
            )
        logs = "\n".join(captured.output)
        self.assertNotIn("unit-test-token", logs)
        self.assertNotIn("unit-test-ticket", logs)
        self.assertNotIn("?", logs)

    async def test_get_arena_rejects_missing_credentials_without_request(self):
        for token, ticket, expected in (
            ("", "ticket", "jx3api_token_missing"),
            ("token", "", "jx3api_ticket_missing"),
        ):
            with self.subTest(expected=expected):
                session = FakeSession([])
                service = JX3APIService(
                    session,
                    base_url="https://example.invalid",
                    token=token,
                    ticket=ticket,
                )
                await self._assert_error(
                    service.get_arena("梦江南", "哇偶"), expected
                )
                self.assertEqual(session.requests, [])

    async def test_get_arena_rejects_invalid_parameters_without_request(self):
        for server, role_name, expected in (
            ("", "哇偶", "missing_server"),
            ("梦江南", "", "invalid_role_name"),
        ):
            with self.subTest(expected=expected):
                session = FakeSession([])
                service = JX3APIService(
                    session,
                    base_url="https://example.invalid",
                    token="token",
                    ticket="ticket",
                )
                await self._assert_error(service.get_arena(server, role_name), expected)
                self.assertEqual(session.requests, [])

    async def test_get_arena_preserves_successful_modes_when_one_times_out(self):
        session = FakeSession(
            {
                "33": [arena_response("33")],
                "22": [asyncio.TimeoutError()],
                "55": [arena_response("55")],
            }
        )
        service = self._service_for_session(session)

        result = await service.get_arena("梦江南", "哇偶")

        self.assertTrue(result["modes"]["3v3"]["ok"])
        self.assertEqual(
            result["modes"]["2v2"],
            {"ok": False, "error": "jx3api_timeout"},
        )
        self.assertTrue(result["modes"]["5v5"]["ok"])
        self.assertEqual(len(session.requests), 3)

    async def test_get_arena_retries_one_connection_error_after_point_three_seconds(self):
        session = FakeSession(
            {
                "33": [aiohttp.ClientConnectionError(), arena_response("33")],
                "22": [arena_response("22")],
                "55": [arena_response("55")],
            }
        )
        service = self._service_for_session(session)
        sleep_delays = []

        async def record_sleep(delay):
            sleep_delays.append(delay)

        with (
            patch("services.jx3api.asyncio.sleep", new=record_sleep),
            self.assertLogs("services.jx3api", level="WARNING") as captured,
        ):
            result = await service.get_arena("梦江南", "哇偶")

        self.assertTrue(result["modes"]["3v3"]["ok"])
        self.assertEqual(sleep_delays, [0.3])
        self.assertEqual(len(session.requests), 4)
        self.assertEqual(
            sum(request["params"]["mode"] == "33" for request in session.requests),
            2,
        )
        logs = "\n".join(captured.output)
        self.assertIn("status=connection_retry", logs)
        self.assertNotIn("unit-test-token", logs)
        self.assertNotIn("unit-test-ticket", logs)
        self.assertNotIn("?", logs)

    async def test_get_arena_stops_after_two_connection_errors_for_one_mode(self):
        session = FakeSession(
            {
                "33": [aiohttp.ClientConnectionError(), aiohttp.ClientConnectionError()],
                "22": [arena_response("22")],
                "55": [arena_response("55")],
            }
        )
        service = self._service_for_session(session)

        with patch("services.jx3api.asyncio.sleep", new=self._no_op_sleep):
            result = await service.get_arena("梦江南", "哇偶")

        self.assertEqual(
            result["modes"]["3v3"],
            {"ok": False, "error": "jx3api_connection_error"},
        )
        self.assertTrue(result["modes"]["2v2"]["ok"])
        self.assertTrue(result["modes"]["5v5"]["ok"])
        self.assertEqual(len(session.requests), 4)
        self.assertEqual(
            sum(request["params"]["mode"] == "33" for request in session.requests),
            2,
        )

    async def test_get_arena_maps_uniform_auth_failures_to_auth_error(self):
        for outcome_factory in (
            lambda: FakeResponse(status=401),
            lambda: FakeResponse(
                payload={"code": 403, "msg": "认证失败", "data": None}
            ),
        ):
            with self.subTest(outcome=outcome_factory()):
                session = FakeSession(
                    {
                        "33": [outcome_factory()],
                        "22": [outcome_factory()],
                        "55": [outcome_factory()],
                    }
                )
                service = self._service_for_session(session)

                await self._assert_error(
                    service.get_arena("梦江南", "哇偶"), "jx3api_auth_error"
                )
                self.assertEqual(len(session.requests), 3)

    async def test_get_arena_preserves_other_modes_for_one_auth_failure(self):
        session = FakeSession(
            {
                "33": [FakeResponse(status=403)],
                "22": [arena_response("22")],
                "55": [arena_response("55")],
            }
        )
        service = self._service_for_session(session)

        result = await service.get_arena("梦江南", "哇偶")

        self.assertEqual(
            result["modes"]["3v3"],
            {"ok": False, "error": "jx3api_auth_error"},
        )
        self.assertTrue(result["modes"]["2v2"]["ok"])
        self.assertTrue(result["modes"]["5v5"]["ok"])

    async def test_get_arena_does_not_retry_non_connection_failures(self):
        class NonConnectionClientError(aiohttp.ClientError):
            pass

        cases = (
            (FakeResponse(status=400), "jx3api_http_4xx"),
            (FakeResponse(status=429), "jx3api_rate_limited"),
            (FakeResponse(status=503), "jx3api_upstream_error"),
            (FakeResponse(json_error=ValueError()), "jx3api_invalid_json"),
            (
                FakeResponse(payload={"code": 500, "msg": "failed", "data": None}),
                "jx3api_api_error",
            ),
            (
                FakeResponse(payload={"code": 200, "msg": "success", "data": {}}),
                "jx3api_empty_data",
            ),
            (FakeResponse(payload=[]), "jx3api_invalid_response"),
            (NonConnectionClientError(), "jx3api_connection_error"),
        )
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                session = FakeSession(
                    {
                        "33": [outcome],
                        "22": [arena_response("22")],
                        "55": [arena_response("55")],
                    }
                )
                service = self._service_for_session(session)
                result = await service.get_arena("梦江南", "哇偶")
                self.assertEqual(
                    result["modes"]["3v3"],
                    {"ok": False, "error": expected},
                )
                self.assertTrue(result["modes"]["2v2"]["ok"])
                self.assertTrue(result["modes"]["5v5"]["ok"])
                self.assertEqual(len(session.requests), 3)
                self.assertEqual(
                    sum(
                        request["params"]["mode"] == "33"
                        for request in session.requests
                    ),
                    1,
                )

    async def test_get_arena_does_not_leak_credentials_from_client_errors(self):
        secret_token = "sensitive-token-value"
        secret_ticket = "sensitive-ticket-value"
        secret_url = (
            "https://example.invalid/arena/recent?"
            f"token={secret_token}&ticket={secret_ticket}"
        )
        session = FakeSession(
            {
                "33": [FakeResponse(json_error=ValueError(secret_url))],
                "22": [arena_response("22")],
                "55": [arena_response("55")],
            }
        )
        service = JX3APIService(
            session,
            base_url="https://example.invalid",
            token=secret_token,
            ticket=secret_ticket,
        )

        with self.assertLogs("services.jx3api", level="WARNING") as captured:
            result = await service.get_arena("梦江南", "哇偶")

        self.assertEqual(
            result["modes"]["3v3"],
            {"ok": False, "error": "jx3api_invalid_json"},
        )
        rendered_result = repr(result)
        logs = "\n".join(captured.output)
        for rendered in (rendered_result, logs):
            self.assertNotIn(secret_token, rendered)
            self.assertNotIn(secret_ticket, rendered)
            self.assertNotIn(secret_url, rendered)

    @staticmethod
    async def _no_op_sleep(_delay):
        return None

    @staticmethod
    def _service_for_session(session):
        return JX3APIService(
            session,
            base_url="https://example.invalid",
            token="unit-test-token",
            ticket="unit-test-ticket",
        )

    async def _assert_error(self, operation, expected_code):
        with self.assertRaises(JX3APIServiceError) as raised:
            await operation
        self.assertEqual(raised.exception.code, expected_code)
        self.assertEqual(str(raised.exception), expected_code)


if __name__ == "__main__":
    unittest.main()

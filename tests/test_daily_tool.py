import dataclasses
import importlib
import json
from pathlib import Path
import sys
import types
import unittest


def _install_test_stubs():
    try:
        import aiohttp  # noqa: F401
    except ModuleNotFoundError:
        aiohttp_module = types.ModuleType("aiohttp")

        class ClientError(Exception):
            pass

        class ClientConnectionError(ClientError):
            pass

        class ContentTypeError(ClientError):
            pass

        aiohttp_module.ClientError = ClientError
        aiohttp_module.ClientConnectionError = ClientConnectionError
        aiohttp_module.ContentTypeError = ContentTypeError
        aiohttp_module.ClientSession = object
        sys.modules["aiohttp"] = aiohttp_module

    try:
        import pydantic  # noqa: F401
    except ModuleNotFoundError:
        pydantic_module = types.ModuleType("pydantic")
        pydantic_dataclasses_module = types.ModuleType("pydantic.dataclasses")

        def field(*, default=dataclasses.MISSING, default_factory=dataclasses.MISSING, **_):
            kwargs = {}
            if default is not dataclasses.MISSING:
                kwargs["default"] = default
            if default_factory is not dataclasses.MISSING:
                kwargs["default_factory"] = default_factory
            return dataclasses.field(**kwargs)

        pydantic_module.Field = field
        pydantic_dataclasses_module.dataclass = dataclasses.dataclass
        sys.modules["pydantic"] = pydantic_module
        sys.modules["pydantic.dataclasses"] = pydantic_dataclasses_module

    if "astrbot.core.agent.tool" not in sys.modules:
        modules = {
            name: types.ModuleType(name)
            for name in (
                "astrbot",
                "astrbot.core",
                "astrbot.core.agent",
                "astrbot.core.agent.run_context",
                "astrbot.core.agent.tool",
                "astrbot.core.astr_agent_context",
            )
        }

        class FunctionTool:
            @classmethod
            def __class_getitem__(cls, _item):
                return cls

        class ContextWrapper:
            @classmethod
            def __class_getitem__(cls, _item):
                return cls

        class AstrAgentContext:
            pass

        modules["astrbot.core.agent.tool"].FunctionTool = FunctionTool
        modules["astrbot.core.agent.tool"].ToolExecResult = str
        modules["astrbot.core.agent.run_context"].ContextWrapper = ContextWrapper
        modules["astrbot.core.astr_agent_context"].AstrAgentContext = AstrAgentContext
        sys.modules.update(modules)


_install_test_stubs()

plugin_package = types.ModuleType("test_jx3_plugin")
plugin_package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules["test_jx3_plugin"] = plugin_package

JX3APIServiceError = importlib.import_module(
    "test_jx3_plugin.services.jx3api"
).JX3APIServiceError
JX3DailyTool = importlib.import_module("test_jx3_plugin.tools.daily").JX3DailyTool


DAILY_DATA = {
    "date": "2026-09-02",
    "week": "三",
    "war": "大战！英雄不染窟",
}


class FakeDailyService:
    def __init__(self, *, result=None, error=None):
        self.result = DAILY_DATA if result is None else result
        self.error = error
        self.offsets = []

    async def get_daily(self, day_offset):
        self.offsets.append(day_offset)
        if self.error is not None:
            raise self.error
        return self.result


class JX3DailyToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_defaults_day_offset_to_zero(self):
        service = FakeDailyService()
        tool = JX3DailyTool(service=service)

        result = json.loads(await tool.call(None))

        self.assertEqual(service.offsets, [0])
        self.assertEqual(result, {"ok": True, "source": "JX3API", "data": DAILY_DATA})

    async def test_call_passes_offsets_zero_one_and_two(self):
        for day_offset in (0, 1, 2):
            with self.subTest(day_offset=day_offset):
                service = FakeDailyService()
                tool = JX3DailyTool(service=service)

                result = json.loads(await tool.call(None, day_offset=day_offset))

                self.assertEqual(service.offsets, [day_offset])
                self.assertTrue(result["ok"])

    async def test_call_returns_controlled_error_for_invalid_offset(self):
        for day_offset in (-1, 3, "1", True, None):
            with self.subTest(day_offset=day_offset):
                service = FakeDailyService()
                tool = JX3DailyTool(service=service)

                result = json.loads(await tool.call(None, day_offset=day_offset))

                self.assertEqual(result, {"ok": False, "error": "invalid_day_offset"})
                self.assertEqual(service.offsets, [])

    async def test_call_returns_controlled_service_error(self):
        service = FakeDailyService(
            error=JX3APIServiceError("jx3api_timeout")
        )
        tool = JX3DailyTool(service=service)

        result = json.loads(await tool.call(None, day_offset=0))

        self.assertEqual(result, {"ok": False, "error": "jx3api_timeout"})

    def test_schema_is_explicit_and_bounded(self):
        tool = JX3DailyTool(service=FakeDailyService())

        self.assertEqual(tool.name, "jx3_daily")
        self.assertEqual(
            tool.parameters,
            {
                "type": "object",
                "properties": {
                    "day_offset": {
                        "type": "integer",
                        "description": "0 表示今天，1 表示明天，2 表示后天。",
                        "enum": [0, 1, 2],
                        "default": 0,
                    }
                },
                "additionalProperties": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

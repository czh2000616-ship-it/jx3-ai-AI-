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
JX3ArenaTool = importlib.import_module("test_jx3_plugin.tools.arena").JX3ArenaTool


ARENA_DATA = {
    "server": "梦江南",
    "role_name": "哇偶",
    "modes": {"3v3": {}, "2v2": {}, "5v5": {}},
}


class FakeArenaService:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def get_arena(self, server, role_name):
        self.calls.append({"server": server, "role_name": role_name})
        if self.error is not None:
            raise self.error
        return ARENA_DATA


class JX3ArenaToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_tool_call_delegates_once_and_returns_all_modes(self):
        service = FakeArenaService()
        tool = JX3ArenaTool(service=service, default_server="梦江南")

        result = json.loads(await tool.call(None, role_name="哇偶"))

        self.assertEqual(service.calls, [{"server": "梦江南", "role_name": "哇偶"}])
        self.assertEqual(result, {"ok": True, "source": "JX3API", "data": ARENA_DATA})
        self.assertEqual(list(result["data"]["modes"]), ["3v3", "2v2", "5v5"])

    async def test_explicit_server_overrides_default(self):
        service = FakeArenaService()
        tool = JX3ArenaTool(service=service, default_server="唯我独尊")

        await tool.call(None, server=" 梦江南 ", role_name=" 哇偶 ")

        self.assertEqual(service.calls, [{"server": "梦江南", "role_name": "哇偶"}])

    async def test_invalid_input_does_not_call_service(self):
        cases = (
            ({"role_name": ""}, "invalid_role_name"),
            ({"role_name": "哇偶"}, "missing_server"),
        )
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                service = FakeArenaService()
                tool = JX3ArenaTool(service=service, default_server="")
                result = json.loads(await tool.call(None, **kwargs))
                self.assertEqual(result, {"ok": False, "error": expected})
                self.assertEqual(service.calls, [])

    async def test_missing_service_returns_controlled_error(self):
        tool = JX3ArenaTool(service=None, default_server="梦江南")

        result = json.loads(await tool.call(None, role_name="哇偶"))

        self.assertEqual(result, {"ok": False, "error": "jx3api_unavailable"})

    async def test_controlled_service_error_is_returned(self):
        service = FakeArenaService(error=JX3APIServiceError("jx3api_timeout"))
        tool = JX3ArenaTool(service=service, default_server="梦江南")

        result = json.loads(await tool.call(None, role_name="哇偶"))

        self.assertEqual(result, {"ok": False, "error": "jx3api_timeout"})

    def test_schema_requires_role_name_and_does_not_expose_mode(self):
        tool = JX3ArenaTool(service=FakeArenaService())

        self.assertEqual(tool.name, "jx3_arena")
        self.assertEqual(set(tool.parameters["properties"]), {"role_name", "server"})
        self.assertEqual(tool.parameters["required"], ["role_name"])
        self.assertFalse(tool.parameters["additionalProperties"])
        self.assertNotIn("mode", tool.parameters["properties"])
        self.assertIn("一次", tool.description)
        self.assertIn("33、22、55", tool.description)


if __name__ == "__main__":
    unittest.main()

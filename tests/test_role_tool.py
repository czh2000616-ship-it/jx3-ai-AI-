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
JX3RoleTool = importlib.import_module("test_jx3_plugin.tools.role").JX3RoleTool


ROLE_DATA = {
    "server": "梦江南",
    "role_name": "张三",
    "force_name": "万花",
}


class FakeRoleService:
    def __init__(self, *, result=None, error=None):
        self.result = ROLE_DATA if result is None else result
        self.error = error
        self.calls = []

    async def get_role(self, server, role_name):
        self.calls.append({"server": server, "role_name": role_name})
        if self.error is not None:
            raise self.error
        return self.result


class JX3RoleToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_passes_explicit_server_and_role_name(self):
        service = FakeRoleService()
        tool = JX3RoleTool(service=service, default_server="唯我独尊")

        result = json.loads(
            await tool.call(None, server="梦江南", role_name="张三")
        )

        self.assertEqual(
            service.calls,
            [{"server": "梦江南", "role_name": "张三"}],
        )
        self.assertEqual(result, {"ok": True, "source": "JX3API", "data": ROLE_DATA})

    async def test_call_uses_default_server_when_server_is_omitted(self):
        service = FakeRoleService()
        tool = JX3RoleTool(service=service, default_server="梦江南")

        result = json.loads(await tool.call(None, role_name="张三"))

        self.assertEqual(
            service.calls,
            [{"server": "梦江南", "role_name": "张三"}],
        )
        self.assertTrue(result["ok"])

    async def test_call_prefers_explicit_server_over_default_server(self):
        service = FakeRoleService()
        tool = JX3RoleTool(service=service, default_server="梦江南")

        await tool.call(None, server="唯我独尊", role_name="张三")

        self.assertEqual(service.calls[0]["server"], "唯我独尊")

    async def test_call_returns_missing_server_when_no_server_is_available(self):
        for server in (None, "", "   ", 123, True):
            with self.subTest(server=server):
                service = FakeRoleService()
                tool = JX3RoleTool(service=service, default_server="   ")
                kwargs = {"role_name": "张三"}
                if server is not None:
                    kwargs["server"] = server

                result = json.loads(await tool.call(None, **kwargs))

                self.assertEqual(result, {"ok": False, "error": "missing_server"})
                self.assertEqual(service.calls, [])

    async def test_call_returns_invalid_role_name_for_invalid_values(self):
        for role_name in (None, "", "   ", 123, True):
            with self.subTest(role_name=role_name):
                service = FakeRoleService()
                tool = JX3RoleTool(service=service, default_server="梦江南")

                result = json.loads(await tool.call(None, role_name=role_name))

                self.assertEqual(
                    result, {"ok": False, "error": "invalid_role_name"}
                )
                self.assertEqual(service.calls, [])

    async def test_call_strips_surrounding_whitespace_only(self):
        service = FakeRoleService()
        tool = JX3RoleTool(service=service, default_server="唯我独尊")

        await tool.call(None, server="  梦江南  ", role_name="  张三·测试  ")

        self.assertEqual(
            service.calls,
            [{"server": "梦江南", "role_name": "张三·测试"}],
        )

    async def test_call_returns_controlled_service_error(self):
        service = FakeRoleService(error=JX3APIServiceError("jx3api_timeout"))
        tool = JX3RoleTool(service=service, default_server="梦江南")

        result = json.loads(await tool.call(None, role_name="张三"))

        self.assertEqual(result, {"ok": False, "error": "jx3api_timeout"})

    def test_schema_requires_role_name_and_does_not_expose_history(self):
        tool = JX3RoleTool(service=FakeRoleService())

        self.assertEqual(tool.name, "jx3_role")
        self.assertEqual(tool.parameters["required"], ["role_name"])
        self.assertEqual(set(tool.parameters["properties"]), {"role_name", "server"})
        self.assertFalse(tool.parameters["additionalProperties"])
        self.assertNotIn("history", tool.parameters["properties"])
        self.assertIn("具体剑网3角色", tool.description)
        self.assertIn("不要用于战绩、奇遇、金价或日常", tool.description)
        self.assertIn("不要猜测", tool.description)


if __name__ == "__main__":
    unittest.main()

import json
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from pydantic import Field
from pydantic.dataclasses import dataclass

from ..services.jx3api import JX3APIServiceError


_ROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "role_name": {
            "type": "string",
            "description": "剑网3角色名称，保持用户提供的名称，不要自行改写。",
        },
        "server": {
            "type": "string",
            "description": "可选的剑网3服务器，例如“梦江南”；未说明时省略以使用默认服务器。",
        },
    },
    "required": ["role_name"],
    "additionalProperties": False,
}


@dataclass
class JX3RoleTool(FunctionTool[AstrAgentContext]):
    name: str = "jx3_role"
    description: str = (
        "用户询问某个具体剑网3角色的角色资料、门派、阵营、帮会、体型或基础信息时使用。"
        "从自然语言中识别必需的 role_name 和可选的 server；未说明 server 时可省略，"
        "由工具使用默认服务器。不要用于战绩、奇遇、金价或日常查询，"
        "也不要猜测不存在的服务器或角色名。"
    )
    parameters: dict[str, Any] = Field(default_factory=lambda: _ROLE_SCHEMA)
    service: Any = Field(default=None, repr=False, exclude=True)
    default_server: Any = Field(default="", repr=False, exclude=True)

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        role_name = kwargs.get("role_name")
        if not isinstance(role_name, str) or not role_name.strip():
            return self._json_result({"ok": False, "error": "invalid_role_name"})

        server = kwargs.get("server")
        if server is None or (isinstance(server, str) and not server.strip()):
            server = self.default_server
        if not isinstance(server, str) or not server.strip():
            return self._json_result({"ok": False, "error": "missing_server"})
        if self.service is None:
            return self._json_result({"ok": False, "error": "jx3api_unavailable"})

        try:
            data = await self.service.get_role(server.strip(), role_name.strip())
        except JX3APIServiceError as exc:
            return self._json_result({"ok": False, "error": exc.code})

        return self._json_result({"ok": True, "source": "JX3API", "data": data})

    @staticmethod
    def _json_result(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

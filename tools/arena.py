import json
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from pydantic import Field
from pydantic.dataclasses import dataclass

from ..services.jx3api import JX3APIServiceError


_ARENA_SCHEMA = {
    "type": "object",
    "properties": {
        "role_name": {
            "type": "string",
            "description": "要查询名剑战绩的剑网3角色名，保持用户提供的名称。",
        },
        "server": {
            "type": "string",
            "description": "可选的剑网3服务器；未说明时省略以使用默认服务器。",
        },
    },
    "required": ["role_name"],
    "additionalProperties": False,
}


@dataclass
class JX3ArenaTool(FunctionTool[AstrAgentContext]):
    name: str = "jx3_arena"
    description: str = (
        "用户查询某个剑网3角色的名剑大会战绩时调用一次。"
        "工具内部会查询并聚合 33、22、55 三种模式，LLM 不要按模式重复调用。"
        "需要 role_name，可选 server；不要用于角色资料、日常、奇遇、金价或交易查询。"
    )
    parameters: dict[str, Any] = Field(default_factory=lambda: _ARENA_SCHEMA)
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
            data = await self.service.get_arena(server.strip(), role_name.strip())
        except JX3APIServiceError as exc:
            return self._json_result({"ok": False, "error": exc.code})

        return self._json_result({"ok": True, "source": "JX3API", "data": data})

    @staticmethod
    def _json_result(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

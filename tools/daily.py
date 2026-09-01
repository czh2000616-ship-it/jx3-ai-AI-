import json
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from pydantic import Field
from pydantic.dataclasses import dataclass

from ..services.jx3api import JX3APIServiceError


_DAY_OFFSET_SCHEMA = {
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
}


@dataclass
class JX3DailyTool(FunctionTool[AstrAgentContext]):
    name: str = "jx3_daily"
    description: str = (
        "查询剑网3今天、明天或后天的日常数据，包括大战、战场和阵营日常。"
        "用户询问这些实时日常信息时使用此工具。"
    )
    parameters: dict[str, Any] = Field(default_factory=lambda: _DAY_OFFSET_SCHEMA)
    service: Any = Field(default=None, repr=False, exclude=True)

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        day_offset = kwargs.get("day_offset", 0)
        if type(day_offset) is not int or day_offset not in (0, 1, 2):
            return self._json_result({"ok": False, "error": "invalid_day_offset"})
        if self.service is None:
            return self._json_result({"ok": False, "error": "jx3api_unavailable"})

        try:
            data = await self.service.get_daily(day_offset)
        except JX3APIServiceError as exc:
            return self._json_result({"ok": False, "error": exc.code})

        return self._json_result({"ok": True, "source": "JX3API", "data": data})

    @staticmethod
    def _json_result(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

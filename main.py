import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import Context, Star

from .services import JX3APIService
from .tools import JX3DailyTool


class JX3AgentPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self._config = config

        timeout_seconds = config.get("http_timeout_seconds", 10)
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
            timeout_seconds = 10

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        )
        self._service = JX3APIService(
            self._session,
            base_url=config.get("jx3api_base_url", "https://www.jx3api.com"),
            token=config.get("jx3api_token", ""),
            ticket=config.get("jx3api_ticket", ""),
        )
        self._daily_tool = JX3DailyTool(service=self._service)
        self.context.add_llm_tools(self._daily_tool)
        logger.info("JX3 AI Agent loaded: tool=jx3_daily")

    async def terminate(self) -> None:
        if not self._session.closed:
            await self._session.close()

# JX3 AI Agent

JX3 AI Agent 是一个 AstrBot 插件。V0.1 只提供 `jx3_daily` LLM Tool，让用户可以用自然语言查询剑网3今天、明天或后天的日常数据。

## 架构

```text
QQ 用户
→ AstrBot / LLM
→ jx3_daily
→ JX3APIService.get_daily()
→ POST {base_url}/active/calendar
→ JX3API
```

Tool 只校验参数、调用 Service，并返回结构化 JSON；HTTP 请求、上游响应校验和错误映射全部由 Service 负责。

## 安装与配置

将本目录放入 AstrBot 的 `data/plugins/astrbot_plugin_jx3_agent`，然后在 AstrBot 管理面板中配置并启用插件。

可配置项：

- `jx3api_base_url`：JX3API Base URL，默认 `https://www.jx3api.com`；
- `jx3api_token`：可选 Token，只应填写在 AstrBot 插件配置中；
- `jx3api_ticket`：可选 Ticket，只应填写在 AstrBot 插件配置中；
- `default_server`：V0.1 暂未使用；
- `http_timeout_seconds`：HTTP 总超时，默认 10 秒，有效范围 1 到 60 秒。

插件使用 AstrBot 环境已有的 `aiohttp`，不额外声明依赖。

## Tool schema

```json
{
  "type": "object",
  "properties": {
    "day_offset": {
      "type": "integer",
      "description": "0 表示今天，1 表示明天，2 表示后天。",
      "enum": [0, 1, 2],
      "default": 0
    }
  },
  "additionalProperties": false
}
```

成功时返回：

```json
{
  "ok": true,
  "source": "JX3API",
  "data": {
    "date": "API 返回的日期",
    "war": "大战内容"
  }
}
```

失败时返回稳定错误码，例如：

```json
{"ok": false, "error": "jx3api_timeout"}
```

## 测试

自动测试只使用模拟 HTTP 响应，不访问真实 JX3API：

```powershell
python -m unittest discover -s tests -v
```

## AstrBot 手工验证

1. 使用支持 Tool Calling 的 LLM 提供商，并启用本插件。
2. 在当前人格或会话可用工具中确认 `jx3_daily` 已启用。
3. 分别询问“今天大战是什么？”、“明天大战是什么？”和“后天阵营日常是什么？”。
4. 在 AstrBot 日志中确认 `jx3_daily` 被调用，且没有 Token 或 Ticket；检查回答使用的是 Tool 返回的真实数据。
5. 对照返回 JSON 的 `data.date` 判断数据日期。插件不会用系统日期覆盖这个字段。

## 当前范围

- 只支持 `day_offset` 为 `0`、`1`、`2`。
- 只实现 `jx3_daily`，不包含角色、奇遇、名剑、金价、交易行或用户绑定。
- 依赖上游 `/active/calendar` 的现有响应结构，至少要求 `data.date` 和 `data.war` 存在。

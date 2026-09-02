# JX3 AI Agent

JX3 AI Agent 是一个 AstrBot 插件。V0.3 提供三个 LLM Tool：

- `jx3_daily`：查询今天、明天或后天的剑网3日常；
- `jx3_role`：查询指定服务器上的角色资料、门派、阵营、帮会、体型等基础信息；
- `jx3_arena`：一次查询并汇总指定角色的 3v3、2v2、5v5 名剑战绩。

## 架构

```text
QQ 用户
→ AstrBot / LLM
→ jx3_daily、jx3_role 或 jx3_arena
→ JX3APIService
→ JX3API
```

Tool 只校验参数、调用 Service，并返回结构化 JSON；HTTP 请求、三模式聚合、上游响应校验和错误映射由 Service 负责。三个 Tool 复用同一个异步 `aiohttp.ClientSession`。

## 安装与配置

将本目录放入 AstrBot 的 `data/plugins/astrbot_plugin_jx3_agent`，然后在 AstrBot 管理面板中配置并启用插件。开发环境也可使用 Junction 指向本源码目录，无需复制插件文件。

可配置项：

- `jx3api_base_url`：JX3API Base URL，默认 `https://www.jx3api.com`；
- `jx3api_token`：`jx3_role` 和 `jx3_arena` 必需，只应填写在 AstrBot 插件配置中；
- `jx3api_ticket`：`jx3_arena` 必需，只允许填写在 AstrBot 插件配置中；`jx3_daily` 和 `jx3_role` 均不发送；
- `default_server`：用户未向 `jx3_role` 或 `jx3_arena` 提供服务器时使用；为空且用户也未提供服务器时返回 `missing_server`；
- `http_timeout_seconds`：HTTP 总超时，默认 10 秒，有效范围 1 到 60 秒。

插件使用 AstrBot 环境已有的 `aiohttp`，不额外声明依赖。

## Tool schema

### jx3_daily

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

### jx3_role

```json
{
  "type": "object",
  "properties": {
    "role_name": {
      "type": "string",
      "description": "剑网3角色名称，保持用户提供的名称，不要自行改写。"
    },
    "server": {
      "type": "string",
      "description": "可选的剑网3服务器，例如‘梦江南’；未说明时省略以使用默认服务器。"
    }
  },
  "required": ["role_name"],
  "additionalProperties": false
}
```

### jx3_arena

```json
{
  "type": "object",
  "properties": {
    "role_name": {
      "type": "string",
      "description": "要查询名剑战绩的剑网3角色名，保持用户提供的名称。"
    },
    "server": {
      "type": "string",
      "description": "可选的剑网3服务器；未说明时省略以使用默认服务器。"
    }
  },
  "required": ["role_name"],
  "additionalProperties": false
}
```

`jx3_arena` 成功时按模式返回上游已有的 `performance` 和 `history` 字段；某个模式失败时，该模式返回独立错误，其他成功模式仍然保留：

```json
{
  "ok": true,
  "source": "JX3API",
  "data": {
    "server": "梦江南",
    "role_name": "哇偶",
    "modes": {
      "3v3": {"ok": true, "performance": {}, "history": []},
      "2v2": {"ok": false, "error": "jx3api_timeout"},
      "5v5": {"ok": true, "performance": {}, "history": []}
    }
  }
}
```

`jx3_role` 成功时返回经过筛选的结构化数据，例如：

```json
{
  "ok": true,
  "source": "JX3API",
  "data": {
    "server": "梦江南",
    "zone": "电信五区",
    "role_name": "张三",
    "force_name": "万花",
    "camp_name": "浩气盟"
  }
}
```

失败时返回稳定错误码，例如：

```json
{"ok": false, "error": "jx3api_timeout"}
```

## 请求行为

- `jx3_daily`：`POST {base_url}/active/calendar`，JSON 参数为 `num` 与 `mode="day"`，不发送 Token 或 Ticket；
- `jx3_role`：`GET {base_url}/role/detail`，查询参数为 `server`、`name`、内部固定的 `history=1` 与 Token，不发送 Ticket；Token 缺失时不会发起网络请求；
- `jx3_arena`：一次 Tool 调用由 Service 并发执行三次 `GET {base_url}/arena/recent`，分别使用 `mode=33`、`22`、`55`，并发送 `server`、`name`、Token、Ticket；缺少任一凭据时不会发起网络请求。

## 测试

自动测试只使用模拟 HTTP 响应，不访问真实 JX3API：

```powershell
py -V:Astral/CPython3.12.13 -m unittest discover -s tests -v
```

## AstrBot 手工验证

1. 在 AstrBot 插件配置中填写自己的 JX3API Token 和 Ticket；如需省略口语中的服务器，再填写 `default_server`。
2. 重载或重启插件，在当前人格或会话可用工具中确认 `jx3_daily`、`jx3_role`、`jx3_arena` 各出现一次。
3. 询问“帮我看看梦江南的张三”，确认 LLM 调用 `jx3_role(server="梦江南", role_name="张三")`。
4. 配置 `default_server=梦江南` 后询问“帮我看看张三”，确认最终查询仍使用梦江南和原角色名。
5. 临时清空 Token 后重复角色查询，确认返回受控的 `jx3api_token_missing` 且没有发起角色 HTTP 请求。
6. 询问“查一下哇偶的名剑战绩”，确认 LLM 只调用一次 `jx3_arena(role_name="哇偶")`，结果同时包含 `3v3`、`2v2`、`5v5`。
7. 临时清空 Ticket 后重复名剑查询，确认返回受控的 `jx3api_ticket_missing` 且没有发起竞技场 HTTP 请求。
8. 再询问“今天大战是什么？”，确认 `jx3_daily` 仍正常工作且不会发送 Token 或 Ticket。

## 当前范围

- `jx3_daily` 只支持 `day_offset` 为 `0`、`1`、`2`。
- `jx3_role` 不缓存数据，每次成功调用只请求一次 JX3API。
- `jx3_arena` 每次 Tool 调用固定查询 3v3、2v2、5v5；只对明确的连接错误为对应模式额外重试一次，不重试 timeout、HTTP、JSON 或 API 业务错误。
- 三个名剑模式允许部分成功；只有三个模式都返回认证错误时，Tool 才返回顶层 `jx3api_auth_error`。
- 尚未实现角色绑定；默认服务器只来自插件级 `default_server` 配置。
- 角色不存在若没有稳定的独立上游错误码，会统一表现为 `jx3api_api_error`。
- 不包含奇遇、金价、交易行或其他 Tool。

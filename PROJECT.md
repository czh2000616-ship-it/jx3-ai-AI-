# JX3 AI Agent

## 1. 项目简介

JX3 AI Agent 是一个基于 AstrBot 的《剑网3》自然语言智能群助手。

项目的核心目标不是重新开发一个传统剑网3查询机器人，而是在现有 AstrBot、JX3API、JX3BOX 等生态基础上增加一层 AI Agent，使用户无需记忆固定指令，可以直接使用自然语言查询剑网3数据。

例如：

用户：

> 今天大战是什么？

系统应自动判断需要调用“日常查询工具”。

用户：

> 帮我看看梦江南张三最近33打得怎么样。

系统应自动：

1. 判断用户希望查询名剑大会战绩；
2. 提取服务器：梦江南；
3. 提取角色名：张三；
4. 提取模式：33；
5. 调用对应剑网3数据接口；
6. 获取真实数据；
7. 将数据交给 LLM；
8. 由 LLM 生成自然语言回答。

---

# 2. 项目定位

本项目不是：

- 剑网3游戏外挂；
- 游戏自动操作工具；
- 客户端插件；
- 单纯的关键词指令机器人；
- 一个重新实现全部 JX3API 的项目。

本项目是：

> 一个允许 LLM 自动调用剑网3数据工具的 AstrBot AI Agent 插件。

核心技术方向：

- AstrBot
- Python
- LLM
- Function Calling / Tool Calling
- Agent
- JX3API
- JX3BOX
- QQ / NapCat
- SQLite
- Async HTTP

---

# 3. 最终目标

最终用户应该能够直接在 QQ 群中发送：

```text
今天大战啥？
```

```text
梦江南现在金价怎么样？
```

```text
帮我看看张三出了哪些奇遇。
```

```text
看看张三最近33是不是又掉分了。
```

```text
我今晚只有一个小时，上线干点什么？
```

机器人能够根据自然语言自动决定是否调用一个或多个剑网3 Tool。

---

# 4. 系统架构

整体架构：

```text
QQ
│
▼
NapCat
│
▼
AstrBot
│
├── LLM
│     │
│     ├── 意图理解
│     ├── 参数提取
│     ├── Tool Selection
│     └── 最终回答
│
▼
JX3 AI Agent Plugin
│
├── Tool Layer
│     ├── jx3_daily
│     ├── jx3_role
│     ├── jx3_adventure
│     ├── jx3_arena
│     ├── jx3_gold
│     └── jx3_trade
│
├── Service Layer
│     ├── JX3API
│     └── JX3BOX
│
├── User Context
│     ├── QQ用户
│     ├── 默认服务器
│     └── 绑定角色
│
└── Storage
      └── SQLite
```

---

# 5. 设计原则

## 5.1 LLM 负责理解语言

不要大量编写：

```python
if "战绩" in message:
```

或：

```python
if "33" in message:
```

来判断用户意图。

自然语言理解应优先交给 LLM 和 Tool Calling。

---

## 5.2 Tool 负责获取事实

LLM 不应自行生成剑网3实时数据。

例如：

- 战绩；
- 日常；
- 奇遇；
- 金价；
- 交易行；
- 角色信息；

必须来自真实数据源。

流程：

```text
LLM
↓
Tool
↓
JX3API
↓
真实数据
↓
LLM
```

---

## 5.3 Tool 不负责写长篇回答

Tool 应尽量返回清晰、结构化的数据。

错误：

```text
哎呀少侠！经过本助手仔细查看，您今天的大战乃是……
```

正确：

```json
{
  "date": "2026-09-02",
  "daily": "xxxx",
  "battlefield": "xxxx"
}
```

最终自然语言表达由上层 LLM 完成。

---

## 5.4 API 与 Tool 解耦

不要：

```python
@llm_tool
async def jx3_daily():
    async with aiohttp...
```

把所有 HTTP 请求逻辑全部写在 Tool 函数里。

推荐：

```text
Tool
↓
Service
↓
API Client
```

例如：

```python
async def jx3_daily():
    return await jx3api.get_daily()
```

---

# 6. MVP 范围

第一阶段只实现以下 6 个工具。

不要一开始实现全部剑网3功能。

## P0

### jx3_daily

用途：

查询剑网3当天或指定日期的日常内容。

自然语言示例：

- 今天大战是什么？
- 今天有什么日常？
- 明天大战啥？
- 后天阵营日常是什么？

---

### jx3_role

用途：

查询角色基础信息。

参数：

```text
server
role_name
```

自然语言示例：

- 查查梦江南张三。
- 看看张三的角色信息。
- 张三现在什么装分？

---

### jx3_adventure

用途：

查询角色奇遇信息。

参数：

```text
server
role_name
```

自然语言示例：

- 张三出过哪些奇遇？
- 看看张三还有什么奇遇没出。
- 梦江南张三奇遇怎么样？

---

### jx3_arena

用途：

查询名剑大会战绩。

参数：

```text
server
role_name
mode
```

mode 示例：

```text
22
33
55
```

自然语言示例：

- 看看张三最近33怎么样。
- 张三竞技场最近是不是掉分了？
- 查一下张三33战绩。

---

## P1

### jx3_gold

用途：

查询服务器金价。

参数：

```text
server
```

自然语言示例：

- 梦江南金价多少？
- 现在金价怎么样？
- 查一下唯我独尊金价。

---

### jx3_trade

用途：

查询交易行商品价格。

参数：

```text
server
item_name
```

自然语言示例：

- 五行石现在多少钱？
- 梦江南五行石什么价？
- 帮我看看这个材料交易行价格。

---

# 7. 项目目录建议

```text
astrbot_plugin_jx3_agent/
│
├── main.py
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
├── README.md
├── PROJECT.md
├── AGENTS.md
│
├── tools/
│   ├── __init__.py
│   ├── daily.py
│   ├── role.py
│   ├── adventure.py
│   ├── arena.py
│   ├── gold.py
│   └── trade.py
│
├── services/
│   ├── __init__.py
│   ├── jx3api.py
│   └── jx3box.py
│
├── models/
│   ├── __init__.py
│   └── schemas.py
│
├── storage/
│   ├── __init__.py
│   └── user_binding.py
│
├── utils/
│   ├── __init__.py
│   ├── errors.py
│   └── server.py
│
└── tests/
    ├── test_daily.py
    ├── test_role.py
    ├── test_adventure.py
    ├── test_arena.py
    ├── test_gold.py
    └── test_trade.py
```

该目录只是推荐架构。

如果 AstrBot 当前版本或现有代码结构要求不同，可以调整，但需要说明原因。

---

# 8. 配置

敏感配置不得硬编码。

至少包括：

```text
JX3API Token
JX3API Ticket
API Base URL
默认服务器
HTTP Timeout
```

Token 与 Ticket：

- 不写入 Git；
- 不写死在代码；
- 不在日志中完整输出；
- 不加入测试数据；
- 不提交到 README。

---

# 9. 用户角色绑定

MVP 完成后增加角色绑定。

目标：

```text
QQ用户
↓
默认服务器
↓
默认角色
```

例如：

```text
QQ: 123456
server: 梦江南
role: 张三
```

用户以后只需要说：

```text
看看我33怎么样。
```

系统即可解析：

```text
我
↓
QQ 123456
↓
梦江南
↓
张三
```

然后调用：

```text
jx3_arena
```

---

# 10. 多工具 Agent

角色绑定完成后，支持一次请求调用多个 Tool。

例如：

```text
我今晚只有一个小时，上线干嘛？
```

Agent 可以调用：

```text
jx3_daily
+
jx3_role
+
jx3_adventure
```

再由 LLM 综合生成建议。

这一阶段是真正的 Agent 能力，而不是单一 Function Calling。

---

# 11. 剑网3知识库

实时数据使用 Tool。

知识型内容使用知识库或可靠的数据源。

例如：

实时：

```text
今天大战
金价
战绩
奇遇
交易行
```

通过 Tool。

知识：

```text
副本攻略
门派机制
奇遇攻略
技能说明
配装思路
```

通过：

```text
RAG / JX3BOX / 可靠资料
```

不要混淆两者。

---

# 12. 错误处理

至少处理：

- HTTP timeout；
- DNS / 网络错误；
- 429 限流；
- 4xx；
- 5xx；
- JSON 格式异常；
- API 返回 success=false；
- 空数据；
- Token 过期；
- Ticket 失效；
- 服务器不存在；
- 角色不存在；
- 参数缺失。

Tool 应返回机器可理解的错误信息。

不要直接抛出长 traceback 给用户。

---

# 13. 测试原则

所有核心 Tool 应具有测试。

测试不应依赖实时在线 API 才能通过。

优先使用：

- mock；
- fixture；
- 固定 API response。

测试至少覆盖：

```text
正常响应
空结果
网络超时
API错误
JSON错误
参数错误
```

---

# 14. 性能原则

使用异步 I/O。

推荐：

```text
aiohttp
```

或项目中已有且合理的异步 HTTP 客户端。

避免：

```text
requests
```

阻塞 AstrBot 主事件循环。

HTTP 客户端应尽量复用连接。

---

# 15. 日志

日志用于调试，不用于泄露数据。

允许记录：

```text
tool=jx3_daily
status=success
latency=320ms
```

不要记录：

```text
完整Token
完整Ticket
敏感请求Header
```

---

# 16. 项目路线

## V0.1

完成：

```text
jx3_daily
```

验证：

```text
自然语言
→
LLM
→
Tool Calling
→
JX3API
→
LLM
→
回答
```

---

## V0.2

增加：

```text
jx3_role
jx3_adventure
jx3_arena
```

---

## V0.3

增加：

```text
jx3_gold
jx3_trade
```

---

## V0.4

增加：

```text
角色绑定
默认服务器
默认角色
```

---

## V0.5

支持：

```text
多 Tool Agent
```

---

## V0.6

增加：

```text
剑网3知识库
```

---

## V0.7

增加：

```text
群聊上下文
昵称绑定
群成员别名
```

---

## V1.0

形成完整：

> AI 剑网3群助手。

---

# 17. 第一里程碑

当前项目最重要的第一个里程碑只有一个：

用户发送：

```text
今天大战是什么？
```

用户没有输入任何固定剑三指令。

LLM 自动判断应该调用：

```text
jx3_daily
```

Tool 查询真实数据。

LLM 根据 Tool 返回的数据生成正确回答。

如果这一完整链路能够稳定运行：

> MVP 技术路线即验证成功。
# CLAUDE.md

> 状态：**重写中**。旧实现（v0.2.0）将被整体删除并从零重做。本文件先于新代码落地，作为重写的约束与依据。
> 新代码结构确定后，更新「仓库结构」「常用命令」两节，删掉「待定决策」里已决定的条目。

## 项目是什么

agent-mq：给 AI 编程助手（Claude Code、Cursor 等）用的消息队列，让不同会话 / 不同机器上的 agent 互相发消息、派任务。

核心模型：
- 一个 **token** 就是一个命名空间。同一 token 下的 agent 互相可见，不同 token 完全隔离。
- agent 按 **名字** 寻址；消息投递到目标 agent 的收件箱。
- 接收方 **拉取（poll）** 消息，读取即消费。没有推送。
- 对 agent 暴露的是一组 MCP 工具（`mq_*`），通过 npm 包以 stdio MCP server 方式运行。

## 必须保持兼容的外部契约

这些已经发布、有外部用户或外部配置依赖，重写时不要随意改；要改须先和用户确认，并给出迁移方案：

| 契约 | 当前值 |
|---|---|
| npm 包名 / bin | `@agent-mq/mcp` / `agent-mq-mcp` |
| MCP 安装命令 | `npx --yes --package @agent-mq/mcp -- agent-mq-mcp`（见 `.mcp.json`、README） |
| Claude Code 插件 | `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`，插件名 `agent-mq` |
| Skill | `skills/mq/SKILL.md`（name: `mq`） |
| 网站 / 文档 URL | `https://agent-mq.com`，`/usage.md`、`/install.md`、`/llms.txt`（README 和用户提示词里直接引用） |
| 托管 API | Fly.io app `agent-mq-api`，路径前缀 `/api/v1`，`Authorization: Bearer <token>` |
| 本地配置 | `~/.agent-mq/config.json`（`{server, token}`） |
| Glama 收录 | 根目录 `glama.json` + 根目录 `Dockerfile`（需能直接启动 MCP server） |
| CI 密钥名 | `NPM_TOKEN`、`FLY_API_TOKEN`、`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID` |

MCP 工具名（`mq_login`、`mq_logout`、`mq_add`、`mq_send`、`mq_recv`、`mq_ls`、`mq_history`）也已写进用户的提示词和 cron 任务里；改名或改参数视为破坏性变更。

## 旧实现的教训（重写时要解决）

旧代码：`server/app.py`（FastAPI + SQLite，单文件）、`mcp/src/*.ts`（MCP server + HTTP client）、`site/`（Cloudflare Pages 静态站）。

1. **发件人可伪造**：`mq_send` 的 `sender` 由调用方随便填，服务端不校验。
2. **token 即用户 ID，明文入库**，且任意 ≥16 字符的字符串会被自动注册成新用户。
3. **跨租户数据泄露**：`/api/v1/analytics/summary` 对任何 token 返回全局统计。
4. **recv 非原子**：先查后删，并发 recv 可能重复投递；类型过滤在 Python 里做。
5. **无过期 / 清理**：inbox、done、analytics 表无 TTL、无上限，`history` 的 `limit` 无上限。
6. **版本号散落 6 处**（server、mcp package.json、index.ts、client.ts、plugin.json、SKILL.md），靠手改同步。
7. **只能轮询**：依赖 agent 自己设 cron 调 `mq_recv`；冷启动慢导致客户端加了超时重试的补丁。
8. 错误信息过时（提示运行不存在的 `mq login` 命令）；agent 注册无法删除。
9. 双语言栈（Python server + TS client）各自重复定义消息格式，没有共享 schema。

## 工作约定

- 开发分支：按会话指定的分支提交和推送；未经用户要求不开 PR、不推 `main`、不打 `v*` tag（打 tag 会触发发布：npm publish + Fly 部署 + Pages 部署）。
- 先写/改测试再改实现；每次提交前跑全部测试并保证通过。
- 消息格式、API 请求/响应只定义一次（单一 schema 来源），服务端和客户端共用或由其生成。
- 版本号只维护一处，其他位置由脚本/构建同步。
- 所有用户可见文档（README、`site/*.md`、SKILL.md、MCP 工具描述）与实现同步修改，不留过时说明。
- 不提交密钥、token、`server/data/` 下的数据库文件。
- 依赖尽量少；新增依赖前说明理由。

## 待定决策（重写前需与用户确认）

- [ ] 技术栈：继续 Python server + TS MCP，还是统一为单一语言（如全 TS）？
- [ ] 存储：继续 SQLite（Fly volume），还是换其他方案？
- [ ] 是否保留 `/api/v1` 兼容，还是出 `/api/v2` 并保留 v1 一段时间？
- [ ] 鉴权：token 如何签发、是否哈希存储、发件人如何绑定身份。
- [ ] 投递语义：是否增加 ack / 可见性超时 / 长轮询 / 消息 TTL。
- [ ] `site/` 是否一并重做，部署目标是否不变（Cloudflare Pages）。

## 仓库结构

_TBD — 新结构确定后填写。_

## 常用命令

_TBD — 新结构确定后填写（安装、构建、测试、本地起服务、发布流程）。_

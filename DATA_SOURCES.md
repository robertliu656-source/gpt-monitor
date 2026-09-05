# GPT Monitor 数据源记录 / Data sources

## 实机环境

- macOS 26.6.1，Build 25G76
- 架构：Apple Silicon arm64
- 系统内核：Darwin 25.6.0 arm64
- 构建 Python：Homebrew Python 3.14.6
- 默认数据根：`$HOME/.codex/sessions/**/*.jsonl`
- 文件名模式：`$HOME/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`

## 实机确认的可见回复结构

```text
top-level type=response_item
payload.type=message
payload.role=assistant
payload.phase=commentary 或 final_answer
payload.content[].type=output_text
payload.content[].text=屏幕可见正文
payload.internal_chat_message_metadata_passthrough.turn_id=稳定 turn 标识
payload.id=稳定 message 标识
```

同一可见消息还会出现 `event_msg / agent_message` 副本。实现只采用 `response_item`，因此不会
因副本重复朗读。`reasoning`、`custom_tool_call`、`custom_tool_call_output`、`mcp_tool_call_end`、
`token_count`、developer 和 user 消息均被排除。真实 turn 生命周期使用 `task_started` 和
`task_complete`；按需复制的 commentary 回退只接受已经 `task_complete` 的 turn。

## 读取边界

- 启动时已有文件从 EOF 开始；启动后新建文件从 0 开始。
- 每轮按修改时间监听最近至少 16 个 JSONL 文件。
- 仅处理以换行结束的完整行；末尾半行不推进 offset。
- 二进制增量读取支持 BOM、CRLF 和超过 64KB 的单行。
- `extra_roots` 只增加明确配置的数据根，不扫描整个磁盘。

## 隐私边界

日志只写文件名、事件类型、字符数、分段数、状态与错误类型。完整回复不会写入应用目录、
Application Support、Caches 或日志。复制功能按键触发后即时倒序扫描，正文只传给 `pbcopy`，
操作结束后释放完整正文变量。

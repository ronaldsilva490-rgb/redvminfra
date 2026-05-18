# InferProxy Anthropic compatibility notes

Scope: `inferproxy` should behave as a Claude-compatible gateway for Claude
Desktop and Claude Code while using InferAll as the upstream.

## Compatibility target

The primary mode is:

```text
INFERPROXY_UPSTREAM_MODE=messages
POST https://api.inferall.ai/v1/messages
```

This mode keeps the Anthropic request/response shape as intact as possible. The
OpenAI/generate mode is a fallback only; it is lossy for thinking blocks,
server tools, MCP blocks, citations, files, and tool streaming.

## Request fields

| Field | Current behavior | Notes |
| --- | --- | --- |
| `model` | Rewritten from local alias to upstream model id | Required for InferAll routing. |
| `messages` | Passed through | Preserve `thinking`, `redacted_thinking`, `tool_use`, `tool_result`, images, PDFs, and file/content blocks unchanged. |
| `system` | Passed through | Includes text blocks and cache markers when present. |
| `tools` custom | Schema is compacted for InferAll tolerance | Preserve tool name, description, compact JSON schema, and safe metadata. |
| `tools` server/MCP/built-in | Passed through when tool has `type` and no custom schema | Do not convert `web_search_...`, `mcp_toolset`, text editor, bash, or code tools into fake custom tools. |
| `tool_choice` | Passed through in messages mode | With extended thinking, `auto` and `none` are the safest choices. |
| `thinking` | Passed through except documented Opus post-write rescue | Thinking blocks and signatures must round-trip when tools are used. |
| `output_config` | Passed through | Used by Claude clients for effort and newer model behavior. |
| `metadata`, `container`, `context_management`, `mcp_servers`, `service_tier` | Passed through | Upstream support varies. Log and test before relying on them. |
| `stream` | Passed through | Proxy must never read `response.content` before returning a streaming `Response`. |

## Auxiliary endpoints

The proxy implements the common Anthropic-compatible endpoints needed by SDKs
and Claude clients:

| Endpoint | Behavior |
| --- | --- |
| `GET /v1/models` | Lists local aliases. |
| `GET /v1/models/{model_id}` | Resolves local alias or upstream model id. |
| `POST /v1/messages/count_tokens` | Local estimate only; InferAll has no compatible upstream token endpoint. |
| `POST /v1/files` | Stores the uploaded file locally and returns a Claude-like `file` object. |
| `GET /v1/files` | Lists local files. |
| `GET /v1/files/{file_id}` | Returns local file metadata. |
| `GET /v1/files/{file_id}/content` | Downloads local file bytes. |
| `DELETE /v1/files/{file_id}` | Deletes local metadata and bytes. |

Before forwarding a Messages request, local `source.type=file` references are
resolved to inline `source.type=base64` content. InferAll cannot see local
`file_id` values, so passing them through unchanged is not compatible.

Every response gets a `request-id` header. Error payloads include `request_id`
to match Anthropic's documented error shape.

## Beta headers

Claude clients may send `anthropic-beta` explicitly. The proxy preserves the
client header and, when `INFERPROXY_AUTO_BETA_HEADERS=1`, appends official beta
tokens only when the payload already uses the matching feature:

| Feature detected | Beta appended |
| --- | --- |
| tool with `eager_input_streaming` | `fine-grained-tool-streaming-2025-05-14` |
| `mcp_servers` or `mcp_toolset` | `mcp-client-2025-11-20` |
| file/document source with `file_id` or `source.type=file` | `files-api-2025-04-14` |
| `context_management.edits[].type=clear_tool_uses_20250919` or `clear_thinking_20251015` | `context-management-2025-06-27` |
| `context_management.edits[].type` beginning with `compact_` | `compact-2026-01-12` |
| `output_config.task_budget` | `task-budgets-2026-03-13` |

This is intentionally feature-triggered, not a blanket beta header list. Sending
unrelated betas can make upstream debugging harder and may change model behavior.

## Streaming contract

Expected Anthropic SSE sequence:

```text
message_start
content_block_start
content_block_delta
content_block_stop
message_delta
message_stop
```

Important delta types to preserve:

```text
text_delta
input_json_delta
thinking_delta
signature_delta
```

The proxy currently streams upstream bytes directly in messages mode. This is
the correct path for maximum fidelity. Any parsing/re-emitting layer must be
covered by fixture tests before production use.

## Tool metadata

Custom tools are compacted because InferAll previously rejected full Claude
Desktop schemas with fields such as JSON-schema `title`. The compactor must
still preserve Anthropic tool metadata that changes model behavior:

```text
eager_input_streaming
cache_control
input_examples
strict
defer_loading
allowed_callers
```

Live probe on the VM confirmed InferAll accepts:

```text
eager_input_streaming
cache_control
strict
input_examples
```

## Known upstream limits

`/v1/messages/count_tokens` is not exposed by InferAll today. Tested paths:

```text
https://api.inferall.ai/v1/messages/count_tokens
https://api.inferall.ai/v1/messages/tokens
https://api.inferall.ai/messages/count_tokens
```

All returned unavailable/not found in prior probes. The local
`/v1/messages/count_tokens` endpoint is therefore an estimate, not an exact
Anthropic-equivalent count.

Fine-grained tool streaming depends on the upstream model/provider. The proxy
preserves `eager_input_streaming`, but if InferAll returns a whole
`input_json_delta` at once, the proxy must not fake partial tool streaming unless
that behavior is explicitly enabled for UI smoothing only.

MCP connector support through `mcp_servers` is only compatible if the upstream
implements Anthropic's MCP connector beta. Local stdio MCP servers remain a
client-side Claude Code/Desktop feature and should not be forced through
InferProxy.

## Regression tests that must stay green

```powershell
cd C:\Projetos\redvm\servicos\inferproxy
python -m unittest discover -s tests -v
```

Minimum fixture coverage:

1. Raw messages-mode streaming does not buffer.
2. Thinking and `output_config` survive request translation.
3. `thinking_delta` and `signature_delta` pass through untouched.
4. Large `Write` tool calls keep `eager_input_streaming`.
5. Custom tools preserve safe metadata while compacting schema noise.
6. Server tools and MCP toolsets pass through without fake `input_schema`.
7. Tool-result round trips preserve IDs and block types.
8. Upstream errors map to Anthropic-shaped errors without leaking credentials.

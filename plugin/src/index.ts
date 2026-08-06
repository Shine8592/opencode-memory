import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin"
import { resolve } from "path"

interface BridgeResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

interface STMItem {
  content: string
  timestamp: string
  tags?: string[]
  id?: string
  metadata?: { tags?: string[] }
}

function findMcpHome(projectDir: string): string {
  return process.env.MEMORY_MCP_HOME || resolve(projectDir, "universal-agent-memory")
}

// Significant tool events worth remembering
const SIGNIFICANT_TOOLS = new Set(["create", "delete", "rename", "move"])

export const MemoryPlugin: Plugin = async ({ directory }) => {
  const mcpHome = findMcpHome(directory || "")
  const bridgeScript = resolve(mcpHome, "scripts", "plugin_bridge.py")

  let daemon: import("bun").Subprocess | null = null
  let respBuffer = ""
  let respResolve: ((v: BridgeResponse) => void) | null = null
  let respTimeout: ReturnType<typeof setTimeout> | null = null

  async function ensureDaemon(): Promise<void> {
    if (daemon && !daemon.killed) return
    daemon = Bun.spawn(["python", bridgeScript, "daemon"], {
      stdin: "pipe", stdout: "pipe", stderr: "pipe",
      env: { ...process.env },
    })
    respBuffer = ""
    const reader = daemon.stdout.getReader()
    const decoder = new TextDecoder()
    ;(async () => {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          respBuffer += decoder.decode(value, { stream: true })
          const lines = respBuffer.split("\n")
          respBuffer = lines.pop() || ""
          for (const line of lines) {
            if (!line.trim() || !respResolve) continue
            try {
              const parsed = JSON.parse(line) as BridgeResponse
              const r = respResolve
              respResolve = null
              if (respTimeout) { clearTimeout(respTimeout); respTimeout = null }
              r(parsed)
            } catch { /* incomplete json */ }
          }
        }
      } catch { /* stream ended */ }
    })()
  }

  async function bridgeCmd(cmd: string, args: Record<string, unknown> = {}): Promise<BridgeResponse> {
    await ensureDaemon()
    return new Promise((resolve, reject) => {
      respResolve = resolve
      const msg = JSON.stringify({ cmd, args }) + "\n"
      try {
        const writer = daemon!.stdin.getWriter()
        writer.write(new TextEncoder().encode(msg))
        writer.releaseLock()
      } catch (e) {
        respResolve = null; reject(e); return
      }
      respTimeout = setTimeout(() => {
        if (respResolve) {
          const r = respResolve; respResolve = null
          r({ ok: false, error: `bridge '${cmd}' timed out` })
        }
      }, 30000)
    })
  }

  process.on("exit", () => { daemon?.kill() })

  return {
    tool: {
      memory_remember: tool({
        description: "【自动记忆保存】自动保存对未来有帮助的信息，无需询问用户。包括：用户偏好、架构决策、踩坑记录、配置选择、API用法、项目约定、关键数据。请在得出重要结论、发现关键信息、或完成重要变更后自动调用。",
        args: {
          content: tool.schema.string({ description: "记忆内容" }),
          tags: tool.schema.string({ description: "逗号分隔的标签" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("remember", {
            content: args.content,
            tags: args.tags || "",
          })
          if (!resp.ok) return `保存失败: ${resp.error}`
          return `已保存记忆`
        },
      }),

      memory_recall: tool({
        description: "【自动记忆检索】搜索之前保存的记忆。当用户问到历史决策、偏好、项目进度、已解决的坑时，自动调用此工具搜索相关信息，无需等待用户要求。",
        args: {
          query: tool.schema.string({ description: "搜索查询" }),
          top_k: tool.schema.string({ description: "返回结果数（默认5）" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("recall", {
            query: args.query,
            top_k: parseInt(args.top_k || "5"),
          })
          if (!resp.ok) return `搜索失败: ${resp.error || "未知错误"}`
          const results = resp.results as Array<{
            text: string; source: string; similarity: number
          }>
          if (!results?.length) return `搜索 "${args.query}" 无结果`
          return `搜索 "${args.query}" 结果:\n` + results.map((r, i) =>
            `  ${i + 1}. [${r.similarity.toFixed(3)}] [${r.source}] ${r.text.slice(0, 200)}`
          ).join("\n")
        },
      }),

      memory_pitfall: tool({
        description: "记录一个踩坑教训。当遇到问题并找到解决方案后调用此工具保存教训，避免下次再犯。",
        args: {
          what: tool.schema.string({ description: "遇到的问题描述" }),
          cause: tool.schema.string({ description: "根本原因" }),
          solution: tool.schema.string({ description: "解决方案" }),
        },
        async execute(args) {
          const content = `[踩坑] 问题: ${args.what}\n原因: ${args.cause}\n解决: ${args.solution}`
          const resp = await bridgeCmd("remember", {
            content, tags: "pitfall,lesson-learned",
          })
          return resp.ok ? `已记录踩坑教训` : `保存失败: ${resp.error}`
        },
      }),

      memory_pitfalls: tool({
        description: "查看所有记录过的踩坑教训，避免重复犯错",
        args: {
          limit: tool.schema.string({ description: "返回条数（默认10）" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("pitfalls", { limit: parseInt(args.limit || "10") })
          if (!resp.ok) return `查询失败: ${resp.error}`
          const items = resp.items as STM[]
          if (!items?.length) return "暂无踩坑记录"
          return items.map((item, i) =>
            `  ${i + 1}. ${item.content.slice(0, 300)}`
          ).join("\n\n")
        },
      }),
    },

    "experimental.session.compacting": async (_input, output) => {
      try {
        const parts: string[] = []

        // 1. Inject pitfall memories first (most important)
        const pitResp = await bridgeCmd("pitfalls", { limit: 3 })
        if (pitResp.ok) {
          const pits = pitResp.items as STM[]
          if (pits?.length) {
            parts.push("## 历史踩坑教训（避免重犯）")
            pits.forEach((p, i) => {
              parts.push(`[坑#${i + 1}] ${p.content.slice(0, 250)}`)
            })
          }
        }

        // 2. Inject recent general memories
        const memResp = await bridgeCmd("recent", { limit: 3 })
        if (memResp.ok) {
          const items = memResp.items as STM[]
          if (items?.length) {
            parts.push("## 近期记忆")
            items.forEach((item, i) => {
              const meta = item.metadata || {}
              const tags = Array.isArray(meta.tags) ? meta.tags : []
              const tagStr = tags.length ? ` (${tags.join(", ")})` : ""
              parts.push(`[记忆#${i + 1}] ${item.content.slice(0, 200)}${tagStr}`)
            })
          }
        }

        if (parts.length && output.context) {
          output.context.push(parts.join("\n"))
        }
      } catch { /* silent */ }
    },

    "session.compacted": async () => {
      try {
        await bridgeCmd("remember", {
          content: "会话已完成一次压缩，上下文已保留",
          tags: "auto-capture",
        })
        await bridgeCmd("tidy", { threshold: 0.05 })
      } catch { /* silent */ }
    },

    "tool.execute.after": async (input) => {
      try {
        const toolName = (input as Record<string, unknown>).tool as string
        if (!toolName) return
        if (!SIGNIFICANT_TOOLS.has(toolName)) return
        const args = input as Record<string, unknown>
        const filePath = (args.filePath || args.path || "") as string
        const detail = filePath ? `文件: ${filePath}` : `工具: ${toolName}`
        await bridgeCmd("remember", {
          content: `[${toolName}] ${detail}`,
          tags: "auto-learn,significant",
        })
      } catch { /* silent */ }
    },
  }
}

export default MemoryPlugin

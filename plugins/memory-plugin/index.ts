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
  return process.env.MEMORY_MCP_HOME || resolve(projectDir, "opencode-mcp-memory")
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
        description: "Save a memory for future recall. Use when discovering important decisions, preferences, or project facts.",
        args: {
          content: tool.schema.string({ description: "Memory content" }),
          tags: tool.schema.string({ description: "Comma-separated tags" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("remember", {
            content: args.content,
            tags: args.tags || "",
          })
          if (!resp.ok) return `Save failed: ${resp.error}`
          return `Memory saved`
        },
      }),

      memory_recall: tool({
        description: "Search saved memories. Use when user asks about past decisions, preferences, or project history.",
        args: {
          query: tool.schema.string({ description: "Search query" }),
          top_k: tool.schema.string({ description: "Number of results (default 5)" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("recall", {
            query: args.query,
            top_k: parseInt(args.top_k || "5"),
          })
          if (!resp.ok) return `Search failed: ${resp.error || "unknown error"}`
          const results = resp.results as Array<{
            text: string; source: string; similarity: number
          }>
          if (!results?.length) return `No results for "${args.query}"`
          return `Results for "${args.query}":\n` + results.map((r, i) =>
            `  ${i + 1}. [${r.similarity.toFixed(3)}] [${r.source}] ${r.text.slice(0, 200)}`
          ).join("\n")
        },
      }),

      memory_pitfall: tool({
        description: "Record a lesson learned from a mistake. Use after finding a solution to avoid repeating the error.",
        args: {
          what: tool.schema.string({ description: "Problem description" }),
          cause: tool.schema.string({ description: "Root cause" }),
          solution: tool.schema.string({ description: "Solution" }),
        },
        async execute(args) {
          const content = `[Pitfall] Problem: ${args.what}\nCause: ${args.cause}\nSolution: ${args.solution}`
          const resp = await bridgeCmd("remember", {
            content, tags: "pitfall,lesson-learned",
          })
          return resp.ok ? `Lesson recorded` : `Save failed: ${resp.error}`
        },
      }),

      memory_pitfalls: tool({
        description: "View all recorded lessons to avoid repeating mistakes",
        args: {
          limit: tool.schema.string({ description: "Number of results (default 10)" }),
        },
        async execute(args) {
          const resp = await bridgeCmd("pitfalls", { limit: parseInt(args.limit || "10") })
          if (!resp.ok) return `Query failed: ${resp.error}`
          const items = resp.items as STMItem[]
          if (!items?.length) return "No pitfall records"
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
          const pits = pitResp.items as STMItem[]
          if (pits?.length) {
            parts.push("## Historical Lessons (avoid repeating)")
            pits.forEach((p, i) => {
              parts.push(`[Pit#${i + 1}] ${p.content.slice(0, 250)}`)
            })
          }
        }

        // 2. Inject recent general memories
        const memResp = await bridgeCmd("recent", { limit: 3 })
        if (memResp.ok) {
          const items = memResp.items as STMItem[]
          if (items?.length) {
            parts.push("## Recent Memories")
            items.forEach((item, i) => {
              const meta = item.metadata || {}
              const tags = Array.isArray(meta.tags) ? meta.tags : []
              const tagStr = tags.length ? ` (${tags.join(", ")})` : ""
              parts.push(`[Mem#${i + 1}] ${item.content.slice(0, 200)}${tagStr}`)
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
          content: "Session compacted, context preserved",
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
        const detail = filePath ? `File: ${filePath}` : `Tool: ${toolName}`
        await bridgeCmd("remember", {
          content: `[${toolName}] ${detail}`,
          tags: "auto-learn,significant",
        })
      } catch { /* silent */ }
    },
  }
}

export default MemoryPlugin

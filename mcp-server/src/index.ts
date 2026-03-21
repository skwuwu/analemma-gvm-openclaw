#!/usr/bin/env node
/**
 * Analemma GVM — MCP Server
 *
 * Exposes GVM governance capabilities as MCP tools.
 * Works with OpenClaw, Claude Desktop, Cursor, Windsurf, and any MCP client.
 *
 * Dual-lock architecture:
 *   Layer 1 (MCP, cooperative):  Agent declares intent, requests secrets, checkpoints
 *   Layer 2 (HTTP proxy, forced): All outbound HTTP goes through GVM proxy regardless
 *
 * Env vars:
 *   GVM_PROXY_URL  — GVM proxy base URL (default: http://127.0.0.1:8080)
 *   GVM_AGENT_ID   — Agent identity (default: "mcp-agent")
 *   GVM_TENANT_ID  — Tenant identity (default: none)
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod/v4";

const GVM_PROXY_URL = process.env.GVM_PROXY_URL ?? "http://127.0.0.1:8080";
const GVM_AGENT_ID = process.env.GVM_AGENT_ID ?? "mcp-agent";
const GVM_TENANT_ID = process.env.GVM_TENANT_ID;

// ── HTTP helper ──────────────────────────────────────────────────────────────

async function gvmFetch(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    params?: Record<string, string>;
  } = {},
): Promise<{ status: number; data: unknown }> {
  const url = new URL(path, GVM_PROXY_URL);
  if (options.params) {
    for (const [k, v] of Object.entries(options.params)) {
      url.searchParams.set(k, v);
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-GVM-Agent-Id": GVM_AGENT_ID,
  };
  if (GVM_TENANT_ID) {
    headers["X-GVM-Tenant-Id"] = GVM_TENANT_ID;
  }

  const resp = await fetch(url.toString(), {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let data: unknown;
  const ct = resp.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    data = await resp.json();
  } else {
    data = await resp.text();
  }

  return { status: resp.status, data };
}

function ok(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "gvm-governance",
  version: "0.1.0",
});

// ── Tool 1: gvm_policy_check ─────────────────────────────────────────────────

server.registerTool(
  "gvm_policy_check",
  {
    title: "GVM Policy Check",
    description:
      "Check what GVM would decide for a given request WITHOUT executing it. " +
      "Returns Allow, Delay, or Deny with the matched rule. " +
      "Call this BEFORE making any external API request to know if it will be permitted.",
    inputSchema: {
      method: z.string().describe("HTTP method (GET, POST, PUT, DELETE)"),
      url: z.string().describe("Target URL (e.g. https://api.stripe.com/v1/charges)"),
      operation: z.string().optional().describe(
        "Semantic operation name (e.g. gvm.payment.charge). Optional for Tier 1 check.",
      ),
    },
  },
  async (args) => {
    const parsed = new URL(args.url);
    const { status, data } = await gvmFetch("/gvm/check", {
      method: "POST",
      body: {
        method: args.method,
        target_host: parsed.host,
        target_path: parsed.pathname,
        operation: args.operation ?? "unknown",
      },
    });

    return ok(
      status === 200
        ? JSON.stringify(data, null, 2)
        : `GVM check failed (HTTP ${status}): ${JSON.stringify(data)}`,
    );
  },
);

// ── Tool 2: gvm_declare_intent ───────────────────────────────────────────────

server.registerTool(
  "gvm_declare_intent",
  {
    title: "GVM Declare Intent",
    description:
      "Declare what you intend to do BEFORE making an API call. " +
      "Registers your semantic operation with the proxy for cross-layer forgery detection. " +
      "Returns the policy decision — if Deny, do NOT proceed.",
    inputSchema: {
      operation: z.string().describe("Semantic operation (e.g. gvm.data.read, gvm.payment.charge)"),
      method: z.string().describe("HTTP method you plan to use"),
      url: z.string().describe("Target URL you plan to call"),
      reason: z.string().optional().describe("Brief reason for this action (logged in WAL)"),
    },
  },
  async (args) => {
    const parsed = new URL(args.url);

    // Step 1: dry-run policy check
    const { data } = await gvmFetch("/gvm/check", {
      method: "POST",
      body: {
        method: args.method,
        target_host: parsed.host,
        target_path: parsed.pathname,
        operation: args.operation,
      },
    });

    const result = data as Record<string, unknown>;
    const decision = String(result?.decision ?? "Unknown");
    const proceed = decision === "Allow" || decision.startsWith("Delay");

    // Step 2: register intent with proxy (Shadow Mode verification)
    // This enables the proxy to match this intent when the actual HTTP request arrives.
    if (proceed) {
      await gvmFetch("/gvm/intent", {
        method: "POST",
        body: {
          method: args.method,
          host: parsed.host,
          path: parsed.pathname,
          operation: args.operation,
          agent_id: GVM_AGENT_ID,
        },
      });
    }

    return ok(
      JSON.stringify(
        {
          decision,
          operation: args.operation,
          target: `${args.method} ${args.url}`,
          proceed,
          ...(proceed ? {} : { action: "Do NOT proceed. This request will be blocked." }),
          ...(result?.matched_rule ? { matched_rule: result.matched_rule } : {}),
        },
        null,
        2,
      ),
    );
  },
);

// ── Tool 3: gvm_request_secret ───────────────────────────────────────────────

server.registerTool(
  "gvm_request_secret",
  {
    title: "GVM Request Secret",
    description:
      "Confirm that GVM will auto-inject credentials for a given API host. " +
      "The agent never sees raw keys — the proxy injects them into the Authorization header. " +
      "You do NOT need to set auth headers manually.",
    inputSchema: {
      host: z.string().describe("Target API host (e.g. api.stripe.com)"),
    },
  },
  async (args) => {
    return ok(
      JSON.stringify(
        {
          host: args.host,
          injection: "automatic",
          agent_action: "none — do NOT set Authorization headers",
          how: `Make HTTP requests to ${args.host} through the proxy (HTTP_PROXY=${GVM_PROXY_URL}). ` +
            "The proxy strips any agent-supplied auth headers and injects the correct credential.",
          proxy_url: GVM_PROXY_URL,
        },
        null,
        2,
      ),
    );
  },
);

// ── Tool 4: gvm_checkpoint ───────────────────────────────────────────────────

server.registerTool(
  "gvm_checkpoint",
  {
    title: "GVM Checkpoint",
    description:
      "Save a checkpoint of the current agent state. " +
      "If a subsequent action is denied, rollback to this checkpoint instead of restarting. " +
      "Call BEFORE risky operations (IC-2+).",
    inputSchema: {
      label: z.string().describe("Human-readable label for this checkpoint"),
      step: z.number().describe("Step number in the current workflow (0-based)"),
      state: z
        .string()
        .optional()
        .describe("Serialized agent state (JSON string of context, variables, etc.)"),
    },
  },
  async (args) => {
    const { status, data } = await gvmFetch("/gvm/checkpoint", {
      method: "POST",
      body: {
        agent_id: GVM_AGENT_ID,
        step: args.step,
        label: args.label,
        state: args.state ?? "{}",
      },
    });

    return ok(
      status === 200 || status === 201
        ? JSON.stringify(
            {
              saved: true,
              checkpoint_id: `${GVM_AGENT_ID}:step-${args.step}`,
              label: args.label,
              step: args.step,
            },
            null,
            2,
          )
        : `Checkpoint failed (HTTP ${status}): ${JSON.stringify(data)}`,
    );
  },
);

// ── Tool 5: gvm_rollback ─────────────────────────────────────────────────────

server.registerTool(
  "gvm_rollback",
  {
    title: "GVM Rollback",
    description:
      "Restore agent state to a previously saved checkpoint. " +
      "Use after a Deny to resume from the last approved state.",
    inputSchema: {
      step: z.number().describe("Step number of the checkpoint to restore"),
    },
  },
  async (args) => {
    const { status, data } = await gvmFetch(
      `/gvm/checkpoint/${GVM_AGENT_ID}/${args.step}`,
    );

    if (status !== 200) {
      return ok(`Rollback failed (HTTP ${status}): no checkpoint at step ${args.step}.`);
    }

    const cp = data as Record<string, unknown>;
    return ok(
      JSON.stringify(
        {
          restored: true,
          step: args.step,
          label: cp.label,
          state: cp.state,
          merkle_verified: cp.merkle_verified,
        },
        null,
        2,
      ),
    );
  },
);

// ── Tool 6: gvm_audit_log ────────────────────────────────────────────────────

server.registerTool(
  "gvm_audit_log",
  {
    title: "GVM Audit Log",
    description:
      "View governance status and recent decisions. " +
      "Shows proxy info and provides CLI commands for detailed WAL analysis.",
    inputSchema: {
      last_n: z.number().optional().describe("Number of recent events (default: 10)"),
      decision: z.string().optional().describe("Filter: Allow, Delay, or Deny"),
    },
  },
  async (args) => {
    const { status, data } = await gvmFetch("/gvm/info");

    if (status !== 200) {
      return ok(`Failed to retrieve audit info (HTTP ${status}): ${JSON.stringify(data)}`);
    }

    return ok(
      JSON.stringify(
        {
          proxy_status: "running",
          info: data,
          cli_commands: {
            list: `gvm audit list --last ${args.last_n ?? 10}` +
              (args.decision ? ` --decision ${args.decision}` : ""),
            verify: "gvm audit verify --wal data/wal.log",
            export: "gvm audit export --format json --since 7d",
          },
        },
        null,
        2,
      ),
    );
  },
);

// ── Tool 7: gvm_load_rulesets ─────────────────────────────────────────────────

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Resolve rulesets dir relative to this file (works in dist/ too)
function findRulesetsDir(): string {
  // Try: repo root/rulesets (dev), then relative to dist/
  const candidates = [
    join(dirname(fileURLToPath(import.meta.url)), "..", "..", "rulesets"),
    join(dirname(fileURLToPath(import.meta.url)), "..", "rulesets"),
    join(process.cwd(), "rulesets"),
  ];
  for (const dir of candidates) {
    if (existsSync(dir)) return dir;
  }
  return candidates[0]; // fallback
}

interface RegistryEntry {
  ruleset: string;
  domains: string[];
}

interface SkillRegistry {
  skills: Record<string, RegistryEntry>;
  local_only_skills: string[];
}

server.registerTool(
  "gvm_load_rulesets",
  {
    title: "GVM Load Rulesets",
    description:
      "Auto-detect installed OpenClaw skills and load matching GVM governance rulesets. " +
      "Call this at session start to configure the proxy with skill-appropriate rules. " +
      "Returns which rulesets were loaded and which skills have no matching ruleset.",
    inputSchema: {
      installed_skills: z
        .array(z.string())
        .describe("List of installed OpenClaw skill names (from /skills command)"),
    },
  },
  async (args) => {
    const rulesetsDir = findRulesetsDir();
    let registry: SkillRegistry;

    try {
      const raw = readFileSync(join(rulesetsDir, "registry.json"), "utf-8");
      registry = JSON.parse(raw) as SkillRegistry;
    } catch {
      return ok(
        JSON.stringify({
          error: "registry.json not found",
          rulesets_dir: rulesetsDir,
        }),
      );
    }

    const loaded: Array<{ skill: string; ruleset: string; domains: string[] }> = [];
    const local_only: string[] = [];
    const no_ruleset: string[] = [];
    const seen_rulesets = new Set<string>();

    for (const skill of args.installed_skills) {
      if (registry.local_only_skills.includes(skill)) {
        local_only.push(skill);
        continue;
      }

      const entry = registry.skills[skill];
      if (entry && !seen_rulesets.has(entry.ruleset)) {
        seen_rulesets.add(entry.ruleset);

        // Read the ruleset file and count rules
        try {
          const content = readFileSync(join(rulesetsDir, entry.ruleset), "utf-8");
          const ruleCount = (content.match(/\[\[rules\]\]/g) || []).length;
          loaded.push({
            skill,
            ruleset: entry.ruleset,
            domains: entry.domains,
          });
        } catch {
          no_ruleset.push(`${skill} (ruleset file missing: ${entry.ruleset})`);
        }
      } else if (!entry) {
        no_ruleset.push(skill);
      }
    }

    // List available rulesets for reference
    let available: string[] = [];
    try {
      available = readdirSync(rulesetsDir).filter(
        (f) => f.endsWith(".toml") && !f.startsWith("_"),
      );
    } catch {
      // ignore
    }

    return ok(
      JSON.stringify(
        {
          loaded,
          local_only_skills: local_only,
          no_ruleset:
            no_ruleset.length > 0
              ? {
                  skills: no_ruleset,
                  action:
                    "These skills have no matching ruleset. Their domains will use " +
                    "Default-to-Caution (Delay) or Shadow Mode policy. " +
                    "Review logs with `gvm audit list` and consider contributing a ruleset.",
                }
              : "all skills covered",
          available_rulesets: available,
          apply_command:
            loaded.length > 0
              ? `Copy matched rulesets to GVM config: cp rulesets/{${loaded.map((l) => l.ruleset).join(",")}} config/`
              : "No rulesets to apply",
        },
        null,
        2,
      ),
    );
  },
);

// ── Start ────────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write(
    `GVM MCP server running (proxy: ${GVM_PROXY_URL}, agent: ${GVM_AGENT_ID})\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err}\n`);
  process.exit(1);
});

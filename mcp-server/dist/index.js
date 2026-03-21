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
async function gvmFetch(path, options = {}) {
    const url = new URL(path, GVM_PROXY_URL);
    if (options.params) {
        for (const [k, v] of Object.entries(options.params)) {
            url.searchParams.set(k, v);
        }
    }
    const headers = {
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
    let data;
    const ct = resp.headers.get("content-type") ?? "";
    if (ct.includes("application/json")) {
        data = await resp.json();
    }
    else {
        data = await resp.text();
    }
    return { status: resp.status, data };
}
function ok(text) {
    return { content: [{ type: "text", text }] };
}
// ── MCP Server ───────────────────────────────────────────────────────────────
const server = new McpServer({
    name: "gvm-governance",
    version: "0.1.0",
});
// ── Tool 1: gvm_policy_check ─────────────────────────────────────────────────
server.registerTool("gvm_policy_check", {
    title: "GVM Policy Check",
    description: "Check what GVM would decide for a given request WITHOUT executing it. " +
        "Returns Allow, Delay, or Deny with the matched rule. " +
        "Call this BEFORE making any external API request to know if it will be permitted.",
    inputSchema: {
        method: z.string().describe("HTTP method (GET, POST, PUT, DELETE)"),
        url: z.string().describe("Target URL (e.g. https://api.stripe.com/v1/charges)"),
        operation: z.string().optional().describe("Semantic operation name (e.g. gvm.payment.charge). Optional for Tier 1 check."),
    },
}, async (args) => {
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
    return ok(status === 200
        ? JSON.stringify(data, null, 2)
        : `GVM check failed (HTTP ${status}): ${JSON.stringify(data)}`);
});
// ── Internal: declare intent + execute via proxy ─────────────────────────────
// Max request body size (5MB)
const MAX_BODY_SIZE = 5 * 1024 * 1024;
// Allowed URL schemes
const ALLOWED_SCHEMES = new Set(["http:", "https:"]);
// Headers that must not be set by the agent
const BLOCKED_HEADERS = new Set([
    "authorization", "cookie", "proxy-authorization",
    "x-api-key", "x-auth-token", "x-gvm-agent-id", "x-gvm-tenant-id",
    "host",
]);
// Fetch timeout (30s)
const FETCH_TIMEOUT_MS = 30_000;
// Max WAL lines to read
const MAX_WAL_LINES = 50_000;
async function declareAndFetch(args) {
    // Validate URL scheme (prevent file://, data://, SSRF to metadata endpoints)
    let parsed;
    try {
        parsed = new URL(args.url);
    }
    catch {
        return { decision: "Deny", error: "Invalid URL" };
    }
    if (!ALLOWED_SCHEMES.has(parsed.protocol)) {
        return { decision: "Deny", error: `Scheme ${parsed.protocol} not allowed (http/https only)` };
    }
    // Validate body size
    if (args.body && args.body.length > MAX_BODY_SIZE) {
        return { decision: "Deny", error: `Body too large (${args.body.length} > ${MAX_BODY_SIZE} bytes)` };
    }
    // Validate operation (alphanumeric + dots + underscores only)
    if (args.operation && !/^[a-zA-Z0-9._-]+$/.test(args.operation)) {
        return { decision: "Deny", error: "Invalid operation name (alphanumeric, dots, underscores only)" };
    }
    // Step 1: policy check (dry-run)
    const { data: checkData } = await gvmFetch("/gvm/check", {
        method: "POST",
        body: {
            method: args.method,
            target_host: parsed.host,
            target_path: parsed.pathname,
            operation: args.operation,
        },
    });
    const checkResult = checkData;
    const decision = String(checkResult?.decision ?? "Unknown");
    if (decision !== "Allow") {
        return {
            decision,
            error: String(checkResult?.next_action ?? "Request blocked by policy"),
        };
    }
    // Step 2: register intent (Shadow Mode verification)
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
    // Step 3: execute request through proxy
    // Strip blocked headers (prevent agent from injecting auth/cookies)
    const safeHeaders = {
        "X-GVM-Agent-Id": GVM_AGENT_ID,
    };
    if (GVM_TENANT_ID) {
        safeHeaders["X-GVM-Tenant-Id"] = GVM_TENANT_ID;
    }
    if (args.headers) {
        for (const [k, v] of Object.entries(args.headers)) {
            if (!BLOCKED_HEADERS.has(k.toLowerCase())) {
                safeHeaders[k] = v;
            }
        }
    }
    if (args.body) {
        safeHeaders["Content-Type"] = safeHeaders["Content-Type"] ?? "application/json";
    }
    try {
        const resp = await fetch(args.url, {
            method: args.method,
            headers: safeHeaders,
            body: args.body ?? undefined,
            signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
        });
        const ct = resp.headers.get("content-type") ?? "";
        let responseData;
        if (ct.includes("application/json")) {
            responseData = await resp.json();
        }
        else {
            responseData = await resp.text();
        }
        return { decision: "Allow", status: resp.status, response: responseData };
    }
    catch (err) {
        return {
            decision: "Allow",
            status: 0,
            error: `Request failed: ${err instanceof Error ? err.message : String(err)}`,
        };
    }
}
// ── Tool 2: gvm_fetch ────────────────────────────────────────────────────────
server.registerTool("gvm_fetch", {
    title: "GVM Fetch",
    description: "Execute an HTTP request with governance verification. " +
        "Automatically declares intent, checks policy, and routes through the GVM proxy. " +
        "Use this for ALL external API calls. One tool call = intent + execution.",
    inputSchema: {
        operation: z.string().describe("What you're doing (e.g. stripe.read_charges, github.create_issue)"),
        method: z.string().describe("HTTP method: GET, POST, PUT, DELETE"),
        url: z.string().describe("Full URL (e.g. https://api.stripe.com/v1/charges)"),
        headers: z.record(z.string(), z.string()).optional().describe("Additional HTTP headers"),
        body: z.string().optional().describe("Request body (JSON string)"),
    },
}, async (args) => {
    const result = await declareAndFetch(args);
    if (result.error && !result.response) {
        return ok(JSON.stringify({
            decision: result.decision,
            blocked: true,
            error: result.error,
        }, null, 2));
    }
    return ok(JSON.stringify({
        decision: result.decision,
        status: result.status,
        response: result.response,
        ...(result.error ? { warning: result.error } : {}),
    }, null, 2));
});
// ── Tool 2a: gvm_read ────────────────────────────────────────────────────────
server.registerTool("gvm_read", {
    title: "GVM Read",
    description: "Read data from an external API with governance verification. " +
        "Shorthand for gvm_fetch with method=GET. " +
        "Use for read-only API calls (list, get, search).",
    inputSchema: {
        operation: z.string().describe("What you're reading (e.g. stripe.list_charges, github.get_issues)"),
        url: z.string().describe("Full URL to read from"),
    },
}, async (args) => {
    const result = await declareAndFetch({
        operation: args.operation,
        method: "GET",
        url: args.url,
    });
    return ok(JSON.stringify(result, null, 2));
});
// ── Tool 2b: gvm_write ───────────────────────────────────────────────────────
server.registerTool("gvm_write", {
    title: "GVM Write",
    description: "Write data to an external API with governance verification. " +
        "Shorthand for gvm_fetch with method=POST. " +
        "Use for write operations (create, update, send).",
    inputSchema: {
        operation: z.string().describe("What you're writing (e.g. slack.send_message, github.create_issue)"),
        url: z.string().describe("Full URL to write to"),
        body: z.string().describe("Request body (JSON string)"),
    },
}, async (args) => {
    const result = await declareAndFetch({
        operation: args.operation,
        method: "POST",
        url: args.url,
        body: args.body,
    });
    return ok(JSON.stringify(result, null, 2));
});
// ── Tool 3: gvm_checkpoint ────────────────────────────────────────────────────
server.registerTool("gvm_checkpoint", {
    title: "GVM Checkpoint",
    description: "Save a checkpoint of the current agent state. " +
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
}, async (args) => {
    const { status, data } = await gvmFetch("/gvm/checkpoint", {
        method: "POST",
        body: {
            agent_id: GVM_AGENT_ID,
            step: args.step,
            label: args.label,
            state: args.state ?? "{}",
        },
    });
    return ok(status === 200 || status === 201
        ? JSON.stringify({
            saved: true,
            checkpoint_id: `${GVM_AGENT_ID}:step-${args.step}`,
            label: args.label,
            step: args.step,
        }, null, 2)
        : `Checkpoint failed (HTTP ${status}): ${JSON.stringify(data)}`);
});
// ── Tool 5: gvm_rollback ─────────────────────────────────────────────────────
server.registerTool("gvm_rollback", {
    title: "GVM Rollback",
    description: "Restore agent state to a previously saved checkpoint. " +
        "Use after a Deny to resume from the last approved state.",
    inputSchema: {
        step: z.number().describe("Step number of the checkpoint to restore"),
    },
}, async (args) => {
    const { status, data } = await gvmFetch(`/gvm/checkpoint/${GVM_AGENT_ID}/${args.step}`);
    if (status !== 200) {
        return ok(`Rollback failed (HTTP ${status}): no checkpoint at step ${args.step}.`);
    }
    const cp = data;
    return ok(JSON.stringify({
        restored: true,
        step: args.step,
        label: cp.label,
        state: cp.state,
        merkle_verified: cp.merkle_verified,
    }, null, 2));
});
// ── Tool 5: gvm_status — replaces CLI "gvm status" ──────────────────────────
server.registerTool("gvm_status", {
    title: "GVM Status",
    description: "Show current GVM security status: shadow mode, active rulesets, " +
        "proxy health, and intent store stats. " +
        "Use when user asks 'what's my security status?' or 'is GVM running?'",
    inputSchema: {},
}, async () => {
    const { status, data } = await gvmFetch("/gvm/info");
    if (status !== 200) {
        return ok(JSON.stringify({ proxy: "offline", error: "GVM proxy not responding" }));
    }
    const info = data;
    const shadow = info.shadow;
    const registry = info.registry;
    return ok(JSON.stringify({
        proxy: "running",
        shadow_mode: shadow?.mode ?? "unknown",
        active_intents: shadow?.active_intents ?? 0,
        operations: {
            core: registry?.core_operations ?? 0,
            custom: registry?.custom_operations ?? 0,
        },
        version: info.version,
    }, null, 2));
});
// ── Tool 6: gvm_audit_log — replaces CLI "gvm audit list" ───────────────────
server.registerTool("gvm_audit_log", {
    title: "GVM Audit Log",
    description: "View recent governance decisions from the WAL audit log. " +
        "Shows Allow, Delay, Deny decisions with operation, target, and timestamp. " +
        "Use when user asks 'what was blocked?' or 'show recent API calls'.",
    inputSchema: {
        last_n: z.number().optional().describe("Number of recent events (default: 20)"),
        filter: z
            .string()
            .optional()
            .describe("Filter by decision: 'all' (default), 'denied', 'delayed', 'allowed'"),
    },
}, async (args) => {
    // Read WAL file directly for richer data
    const walPaths = [
        join(process.cwd(), "data", "wal.log"),
        join(process.env.HOME ?? "", ".gvm", "data", "wal.log"),
        "data/wal.log",
    ];
    let events = [];
    for (const p of walPaths) {
        try {
            if (!existsSync(p))
                continue;
            const raw = readFileSync(p, "utf-8");
            // Limit: read only last MAX_WAL_LINES lines to prevent OOM
            const allLines = raw.trim().split("\n");
            const lines = allLines.slice(-MAX_WAL_LINES);
            for (const line of lines) {
                try {
                    const evt = JSON.parse(line);
                    if (evt.event_id)
                        events.push(evt);
                }
                catch {
                    // skip malformed lines
                }
            }
            break; // found and parsed WAL
        }
        catch {
            continue;
        }
    }
    // Filter
    const filter = args.filter?.toLowerCase() ?? "all";
    if (filter !== "all") {
        events = events.filter((e) => {
            const d = String(e.decision ?? "").toLowerCase();
            if (filter === "denied")
                return d === "deny" || d.includes("deny");
            if (filter === "delayed")
                return d.includes("delay");
            if (filter === "allowed")
                return d === "allow";
            return true;
        });
    }
    // Last N
    const lastN = args.last_n ?? 20;
    events = events.slice(-lastN);
    // Format for readability
    const formatted = events.map((e) => ({
        time: e.timestamp,
        decision: e.decision,
        operation: e.operation ?? "unknown",
        target: `${e.transport && e.transport.method || "?"} ${e.transport && e.transport.host || "?"}${e.transport && e.transport.path || ""}`,
        agent: e.agent_id,
        status: e.status,
    }));
    return ok(JSON.stringify({
        total_in_wal: events.length,
        filter,
        events: formatted,
    }, null, 2));
});
// ── Tool 7: gvm_blocked_summary — replaces CLI dashboard ────────────────────
server.registerTool("gvm_blocked_summary", {
    title: "GVM Blocked Summary",
    description: "Human-readable summary of governance activity. " +
        "Shows counts of allowed, delayed, and denied requests. " +
        "Use when user asks 'what happened today?' or 'security summary'.",
    inputSchema: {
        period: z
            .string()
            .optional()
            .describe("Time period: 'today', '1h', '24h', 'all' (default: 'today')"),
    },
}, async (args) => {
    // Read WAL
    const walPaths = [
        join(process.cwd(), "data", "wal.log"),
        join(process.env.HOME ?? "", ".gvm", "data", "wal.log"),
        "data/wal.log",
    ];
    let events = [];
    for (const p of walPaths) {
        try {
            if (!existsSync(p))
                continue;
            const lines = readFileSync(p, "utf-8").trim().split("\n");
            for (const line of lines) {
                try {
                    const evt = JSON.parse(line);
                    if (evt.event_id)
                        events.push(evt);
                }
                catch {
                    // skip
                }
            }
            break;
        }
        catch {
            continue;
        }
    }
    // Filter by period
    const period = args.period ?? "today";
    const now = Date.now();
    if (period !== "all") {
        let cutoff = 0;
        if (period === "today") {
            const todayStart = new Date();
            todayStart.setHours(0, 0, 0, 0);
            cutoff = todayStart.getTime();
        }
        else if (period === "1h") {
            cutoff = now - 3600_000;
        }
        else if (period === "24h") {
            cutoff = now - 86400_000;
        }
        events = events.filter((e) => {
            const ts = e.timestamp ? new Date(String(e.timestamp)).getTime() : 0;
            return ts >= cutoff;
        });
    }
    // Count by decision
    let allowed = 0;
    let delayed = 0;
    let denied = 0;
    const deniedDetails = [];
    for (const e of events) {
        const d = String(e.decision ?? "").toLowerCase();
        if (d === "allow") {
            allowed++;
        }
        else if (d.includes("delay")) {
            delayed++;
        }
        else if (d === "deny" || d.includes("deny")) {
            denied++;
            const transport = e.transport;
            deniedDetails.push(`${transport?.method ?? "?"} ${transport?.host ?? "?"}${transport?.path ?? ""} — ${e.operation ?? "unknown"}`);
        }
    }
    // Get proxy status
    const { data: infoData } = await gvmFetch("/gvm/info").catch(() => ({
        data: null,
    }));
    const info = infoData;
    const shadow = info?.shadow;
    return ok(JSON.stringify({
        period,
        summary: {
            allowed,
            delayed,
            denied,
            total: allowed + delayed + denied,
        },
        denied_details: deniedDetails.length > 0 ? deniedDetails : "none",
        shadow_mode: shadow?.mode ?? "unknown",
        active_intents: shadow?.active_intents ?? 0,
    }, null, 2));
});
// ── Tool 7: gvm_select_rulesets — user-driven, never auto-detect ─────────────
import { readFileSync, writeFileSync, readdirSync, existsSync, copyFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
function findRulesetsDir() {
    const candidates = [
        join(dirname(fileURLToPath(import.meta.url)), "..", "..", "rulesets"),
        join(dirname(fileURLToPath(import.meta.url)), "..", "rulesets"),
        join(process.cwd(), "rulesets"),
    ];
    for (const dir of candidates) {
        if (existsSync(dir))
            return dir;
    }
    return candidates[0];
}
function findConfigDir() {
    // GVM_CONFIG_DIR explicitly set, or derive from GVM_CONFIG_PATH
    if (process.env.GVM_CONFIG_DIR && existsSync(process.env.GVM_CONFIG_DIR)) {
        return process.env.GVM_CONFIG_DIR;
    }
    const configPath = process.env.GVM_CONFIG_PATH;
    if (configPath && existsSync(configPath)) {
        return dirname(configPath);
    }
    const candidates = [
        join(process.cwd(), "config"),
        join(process.env.HOME ?? "", ".gvm", "config"),
        join(process.env.USERPROFILE ?? "", ".gvm", "config"),
    ];
    for (const dir of candidates) {
        if (existsSync(dir))
            return dir;
    }
    // Create default config dir if nothing exists
    const defaultDir = candidates[0];
    try {
        const { mkdirSync } = require("node:fs");
        mkdirSync(defaultDir, { recursive: true });
    }
    catch { /* ignore */ }
    return defaultDir;
}
server.registerTool("gvm_select_rulesets", {
    title: "GVM Select Rulesets",
    description: "Show available governance rulesets and apply user-selected ones to the proxy. " +
        "NEVER auto-detect or auto-apply. The user must explicitly choose which rulesets to load. " +
        "If called without 'apply', lists available rulesets with descriptions. " +
        "If called with 'apply', copies selected rulesets to proxy config and triggers reload.",
    inputSchema: {
        apply: z
            .array(z.string())
            .optional()
            .describe("Rulesets to apply (e.g. ['gmail', 'github']). " +
            "Omit to list available rulesets without applying."),
    },
}, async (args) => {
    const rulesetsDir = findRulesetsDir();
    // List available rulesets
    let available = [];
    try {
        const files = readdirSync(rulesetsDir).filter((f) => f.endsWith(".toml") && !f.startsWith("_"));
        for (const file of files) {
            const name = file.replace(".toml", "");
            // Path traversal prevention
            if (file.includes("..") || file.includes("/") || file.includes("\\"))
                continue;
            try {
                const content = readFileSync(join(rulesetsDir, file), "utf-8");
                const ruleCount = (content.match(/\[\[rules\]\]/g) || []).length;
                // Extract first comment line as description
                const descLine = content.split("\n").find((l) => l.startsWith("# GVM Ruleset:") || l.startsWith("# Covers:"));
                const desc = descLine?.replace(/^#\s*/, "") ?? `${ruleCount} rules`;
                available.push({ name, file, description: desc });
            }
            catch {
                available.push({ name, file, description: "(unreadable)" });
            }
        }
    }
    catch {
        return ok(JSON.stringify({ error: "rulesets directory not found" }));
    }
    // List mode: show what's available
    if (!args.apply || args.apply.length === 0) {
        return ok(JSON.stringify({
            mode: "list",
            available: available.map((r) => ({
                name: r.name,
                description: r.description,
            })),
            usage: "Call gvm_select_rulesets with apply=['gmail','github'] to activate. " +
                "Default: all external requests blocked (Shadow strict). " +
                "Each ruleset you add opens specific domains with specific permissions.",
        }, null, 2));
    }
    // Apply mode: copy selected rulesets to config dir
    const configDir = findConfigDir();
    const applied = [];
    const errors = [];
    // Build new SRR from scratch: _default.toml + selected rulesets only.
    // No appending to existing rules — prevents first-match-wins conflicts.
    const sections = [];
    // Always include _default.toml (localhost allow + fallback)
    const defaultPath = join(rulesetsDir, "_default.toml");
    if (existsSync(defaultPath)) {
        sections.push("# GVM SRR Rules (generated by gvm_select_rulesets)\n" +
            `# Applied: ${new Date().toISOString()}\n` +
            `# Rulesets: _default + ${args.apply.join(", ")}\n\n` +
            readFileSync(defaultPath, "utf-8"));
    }
    for (const name of args.apply) {
        if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
            errors.push(`${name}: invalid name`);
            continue;
        }
        const file = `${name}.toml`;
        const srcPath = join(rulesetsDir, file);
        // Path traversal prevention
        if (file.includes("..") || file.includes("/") || file.includes("\\")) {
            errors.push(`${name}: invalid path`);
            continue;
        }
        if (!existsSync(srcPath)) {
            errors.push(`${name}: ruleset not found`);
            continue;
        }
        try {
            const content = readFileSync(srcPath, "utf-8");
            const ruleCount = (content.match(/\[\[rules\]\]/g) || []).length;
            const domains = new Set();
            for (const match of content.matchAll(/pattern\s*=\s*"([^"\/]+)/g)) {
                if (match[1])
                    domains.add(match[1]);
            }
            sections.push(`\n# -- Ruleset: ${name} --\n` + content);
            applied.push({ name, domains: [...domains].join(", "), rules: ruleCount });
        }
        catch (e) {
            errors.push(`${name}: ${e instanceof Error ? e.message : String(e)}`);
        }
    }
    // Write complete SRR file (replace, not append)
    if (sections.length > 0) {
        const srrPath = join(configDir, "srr_network.toml");
        // Backup existing file for custom/power-user recovery
        if (existsSync(srrPath)) {
            const backupPath = srrPath + ".bak";
            copyFileSync(srrPath, backupPath);
        }
        const combined = sections.join("\n");
        // Write as-is (LF) — Rust toml handles LF fine
        writeFileSync(srrPath, combined, "utf-8");
        // Hot-reload
        try {
            const { status, data } = await gvmFetch("/gvm/reload", { method: "POST" });
            if (status === 200) {
                const d = data;
                process.stderr.write(`SRR hot-reloaded: ${d.rules} rules.\n`);
            }
            else {
                process.stderr.write(`SRR reload failed: ${JSON.stringify(data)}\n`);
                // Restore backup
                const backupPath = srrPath + ".bak";
                if (existsSync(backupPath)) {
                    copyFileSync(backupPath, srrPath);
                    await gvmFetch("/gvm/reload", { method: "POST" });
                    process.stderr.write("Restored previous SRR from backup.\n");
                }
            }
        }
        catch (e) {
            process.stderr.write(`Reload call failed: ${e}\n`);
        }
    }
    return ok(JSON.stringify({
        mode: "apply",
        applied,
        errors: errors.length > 0 ? errors : undefined,
        note: applied.length > 0
            ? "SRR replaced with selected rulesets. Previous config backed up to .bak"
            : "No rules applied.",
    }, null, 2));
});
// ── Proxy auto-launch ────────────────────────────────────────────────────────
import { spawn, execSync } from "node:child_process";
let proxyChild = null;
async function ensureProxy() {
    // Check if proxy is already running
    try {
        const resp = await fetch(`${GVM_PROXY_URL}/gvm/health`, {
            signal: AbortSignal.timeout(1000),
        });
        if (resp.ok) {
            process.stderr.write(`GVM proxy already running at ${GVM_PROXY_URL}\n`);
            return;
        }
    }
    catch {
        // Not running — need to start it
    }
    // Find gvm-proxy binary
    let proxyBin = "gvm-proxy";
    try {
        execSync("gvm-proxy --version", { stdio: "ignore" });
    }
    catch {
        // Try common locations
        const candidates = [
            join(process.env.HOME ?? "", ".cargo", "bin", "gvm-proxy"),
            join(process.env.USERPROFILE ?? "", ".cargo", "bin", "gvm-proxy.exe"),
        ];
        const found = candidates.find((p) => existsSync(p));
        if (found) {
            proxyBin = found;
        }
        else {
            process.stderr.write("Warning: gvm-proxy not found. Install with: cargo binstall gvm-proxy\n" +
                "MCP tools will work when the proxy is started manually.\n");
            return;
        }
    }
    const configPath = process.env.GVM_CONFIG_PATH;
    const proxyArgs = configPath ? ["--config", configPath] : [];
    process.stderr.write(`Starting GVM proxy (${proxyBin}${configPath ? ` --config ${configPath}` : ""})...\n`);
    proxyChild = spawn(proxyBin, proxyArgs, {
        stdio: ["ignore", "ignore", "pipe"],
        detached: false,
        env: {
            ...process.env,
            GVM_SHADOW_MODE: process.env.GVM_SHADOW_MODE ?? "strict",
            // Share config dir with MCP server for ruleset management
            GVM_CONFIG_DIR: process.env.GVM_CONFIG_DIR ?? (configPath ? dirname(configPath) : ""),
        },
    });
    proxyChild.stderr?.on("data", (data) => {
        const line = data.toString().trim();
        if (line.includes("listening") || line.includes("ERROR")) {
            process.stderr.write(`[gvm-proxy] ${line}\n`);
        }
    });
    proxyChild.on("exit", (code) => {
        if (code !== null && code !== 0) {
            process.stderr.write(`Warning: gvm-proxy exited with code ${code}\n`);
        }
        proxyChild = null;
    });
    // Wait for proxy to be ready
    for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 250));
        try {
            const resp = await fetch(`${GVM_PROXY_URL}/gvm/health`, {
                signal: AbortSignal.timeout(500),
            });
            if (resp.ok) {
                process.stderr.write("GVM proxy started successfully.\n");
                return;
            }
        }
        catch {
            // Keep waiting
        }
    }
    process.stderr.write("Warning: GVM proxy may not have started. Check logs.\n");
}
function cleanupProxy() {
    if (proxyChild) {
        process.stderr.write("Stopping GVM proxy...\n");
        proxyChild.kill();
        proxyChild = null;
    }
}
process.on("exit", cleanupProxy);
process.on("SIGINT", () => { cleanupProxy(); process.exit(0); });
process.on("SIGTERM", () => { cleanupProxy(); process.exit(0); });
// ── Start ────────────────────────────────────────────────────────────────────
async function main() {
    await ensureProxy();
    const transport = new StdioServerTransport();
    await server.connect(transport);
    process.stderr.write(`GVM MCP server running (proxy: ${GVM_PROXY_URL}, agent: ${GVM_AGENT_ID})\n`);
}
main().catch((err) => {
    process.stderr.write(`Fatal: ${err}\n`);
    process.exit(1);
});

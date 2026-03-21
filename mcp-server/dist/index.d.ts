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
export {};

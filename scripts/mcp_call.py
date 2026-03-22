#!/usr/bin/env python3
"""
MCP tool caller for CI integration tests.

Sends a JSON-RPC initialize + tools/call to the MCP server via stdin,
parses the response, and prints the tool result JSON to stdout.

Usage:
    python3 scripts/mcp_call.py <tool_name> [<arguments_json>]

Example:
    python3 scripts/mcp_call.py gvm_policy_check '{"method":"GET","url":"https://example.com"}'

Env vars:
    GVM_PROXY_URL  (default: http://127.0.0.1:8080)
    GVM_AGENT_ID   (default: ci-agent)
"""

import subprocess
import json
import sys
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: mcp_call.py <tool_name> [args_json]"}))
        sys.exit(1)

    tool_name = sys.argv[1]
    tool_args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    # Find MCP server
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    mcp_server = os.path.join(repo_dir, "mcp-server", "dist", "index.js")

    if not os.path.exists(mcp_server):
        print(json.dumps({"error": f"MCP server not found: {mcp_server}"}))
        sys.exit(1)

    # Build JSON-RPC messages
    init = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ci", "version": "1.0"},
        },
    })
    call = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": tool_args},
    })

    stdin_data = (init + "\n" + call + "\n").encode("utf-8")

    env = {
        **os.environ,
        "GVM_PROXY_URL": os.environ.get("GVM_PROXY_URL", "http://127.0.0.1:8080"),
        "GVM_AGENT_ID": os.environ.get("GVM_AGENT_ID", "ci-agent"),
    }

    try:
        r = subprocess.run(
            ["node", mcp_server],
            input=stdin_data,
            capture_output=True,
            timeout=15,
            env=env,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "MCP server timed out"}))
        return
    except FileNotFoundError:
        print(json.dumps({"error": "node not found"}))
        return

    stdout = r.stdout.decode("utf-8", "replace").strip()
    stderr = r.stderr.decode("utf-8", "replace").strip()

    if not stdout:
        print(json.dumps({
            "error": "MCP server returned empty stdout",
            "returncode": r.returncode,
            "stderr": stderr[:500],
        }))

    # Parse JSON-RPC responses
    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if d.get("id") == 2:
                content = d.get("result", {}).get("content", [])
                if content:
                    # Print the tool result text (already JSON)
                    print(content[0].get("text", "{}"))
                    return
                # Check for JSON-RPC error
                if "error" in d:
                    print(json.dumps({"error": d["error"].get("message", str(d["error"]))}))
                    return
        except json.JSONDecodeError:
            continue

    # No matching response found
    print(json.dumps({
        "error": "no id=2 response found",
        "stdout_lines": stdout.split("\n")[:5],
        "stderr": stderr[:300],
    }))


if __name__ == "__main__":
    main()

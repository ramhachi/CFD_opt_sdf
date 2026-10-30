"""Keep one Colab MCP adapter connection open for manual JSON-lines commands.

Use only when the fixed Colab tools are unavailable in the current Codex chat.
The script does not connect to a notebook or execute code until commanded.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter",
        type=Path,
        default=Path.home() / ".codex/mcp/colab_codex_adapter.py",
        help="Path to the configured Codex Colab adapter",
    )
    return parser.parse_args()


async def run(adapter: Path) -> None:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    if not adapter.is_file():
        raise FileNotFoundError(f"Colab adapter not found: {adapter}")

    transport = StdioTransport(
        command="uvx",
        args=[
            "--index", "https://pypi.org/simple", "--with", "fastmcp==2.14.5",
            "python", str(adapter),
        ],
    )
    connected = False
    async with Client(transport, timeout=900, init_timeout=120) as client:
        print(json.dumps({"ready": True, "ops": ["connect", "tools", "call", "close"]}), flush=True)
        while line := await asyncio.to_thread(sys.stdin.readline):
            try:
                request = json.loads(line)
                op = request["op"]
                if op == "close":
                    print('{"closed":true}', flush=True)
                    break
                if op == "connect":
                    if connected:
                        print('{"connected":true,"reused":true}', flush=True)
                        continue
                    result = await client.call_tool(
                        "colab_connect_session", {}, timeout=90, raise_on_error=False
                    )
                    connected = not result.is_error and any(
                        getattr(item, "text", "").strip().lower() == "true"
                        for item in result.content
                    )
                elif op in ("tools", "call"):
                    if not connected:
                        raise ValueError("Connect first with {\"op\":\"connect\"}")
                    if op == "tools":
                        result = await client.call_tool(
                            "colab_list_tools", {}, timeout=120, raise_on_error=False
                        )
                    else:
                        result = await client.call_tool(
                            "colab_call_tool",
                            {"name": request["name"], "arguments": request.get("arguments", {})},
                            timeout=900,
                            raise_on_error=False,
                        )
                else:
                    raise ValueError(f"Unknown op: {op}")
                print(json.dumps({
                    "op": op,
                    "is_error": result.is_error,
                    "connected": connected,
                    "content": [item.model_dump(exclude_none=True) for item in result.content],
                }, ensure_ascii=False, default=str), flush=True)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(run(parse_args().adapter))

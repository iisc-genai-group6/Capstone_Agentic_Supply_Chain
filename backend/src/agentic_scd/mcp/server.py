from __future__ import annotations

import argparse
import json

from agentic_scd.mcp.external_data import ExternalDataMCP, manifest


def run_fastmcp() -> bool:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return False
    tools = ExternalDataMCP()
    server = FastMCP("agentic-scd-external-data")

    @server.tool()
    def fetch_rss_signals(live: bool = False) -> dict:
        return tools.call_tool("fetch_rss_signals", {"live": live})

    @server.tool()
    def fetch_weather_hubs(live: bool = False) -> dict:
        return tools.call_tool("fetch_weather_hubs", {"live": live})

    @server.tool()
    def load_freight_snapshot() -> dict:
        return tools.call_tool("load_freight_snapshot", {})

    @server.tool()
    def load_supply_dataset() -> dict:
        return tools.call_tool("load_supply_dataset", {})

    @server.tool()
    def synthetic_scenarios(count: int = 4) -> dict:
        return tools.call_tool("synthetic_scenarios", {"count": count})

    server.run()
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agentic-scd-mcp")
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--tool")
    parser.add_argument("--args", default="{}")
    args = parser.parse_args(argv)
    if args.manifest:
        print(json.dumps(manifest(), indent=2))
        return
    if args.tool:
        print(json.dumps(ExternalDataMCP().call_tool(args.tool, json.loads(args.args)), indent=2, default=str))
        return
    if not run_fastmcp():
        print(json.dumps(manifest(), indent=2))


if __name__ == "__main__":
    main()

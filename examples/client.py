import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

async def main():
    """
    Example script to connect to the MCP server via streamable-http and list its tools.
    Ensure the server is running on http://localhost:8000/mcp before running this script.
    """
    url = "http://localhost:8000/mcp"
    print(f"Connecting to {url}...")

    try:
        async with streamablehttp_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                print("\n Connected to FastMCP server!")

                # Fetch available tools
                tools_response = await session.list_tools()

                print("\n Available Tools:")
                for tool in tools_response.tools:
                    print(f"  - {tool.name}: {tool.description}")

    except Exception as e:
        print(f"\n Failed to connect: {e}")
        print("Did you start the server with `make dev` or `docker compose up`?")

if __name__ == "__main__":
    asyncio.run(main())

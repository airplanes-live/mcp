# Airplanes.live MCP Server
This is the official Airplanes.live MCP server

# Install

Install dependencies:  
`uv sync`

Install the MCP server into Claude Code (or other tool) by editing ~/.mcp.json:
```json
{
    "mcpServers": {
        "airplanes-live": {
            "command": "uv",
            "args": [
                "--directory",
                "/ABSOLUTE/PATH/TO/PARENT/FOLDER/mcp",
                "run",
                "main.py"
            ]
        }
    }
}
```
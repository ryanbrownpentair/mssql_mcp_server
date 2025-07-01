"""
Convenience script to run the MCP server and log any errors.
"""
import sys
from src.mssql_mcp_server.run_and_log import run_mcp_server

if __name__ == "__main__":
    sys.exit(run_mcp_server())

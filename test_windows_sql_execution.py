import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_windows_sql_execution")

# Add project root directory to Python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Load environment variables from .env file
load_dotenv()

from mssql_mcp_server.server_manager import get_server_manager
from mssql_mcp_server.server import call_tool

async def test_execute_sql_on_windows_servers():
    """Test SQL execution on Windows servers using tools"""
    logger.info("Starting SQL execution test on Windows servers...")
    
    # Initialize server manager
    server_manager = get_server_manager()
    
    # Target servers for testing
    windows_servers = [
        "USCHITDB63-PTODS",
        "USCHITDB63-WQSDW"
    ]
    
    # Execute SQL queries on each server
    for server_name in windows_servers:
        logger.info(f"Running SQL execution test on server {server_name}...")
        
        # Test case: Switch server
        result = await call_tool("switch_server", {"server": server_name})
        if result and result[0].text and "Switched to server" in result[0].text:
            logger.info(f"Successfully switched to server {server_name}")
        else:
            logger.error(f"Failed to switch to server {server_name}")
            continue
        
        # Test case: Get table list
        try:
            result = await call_tool("execute_sql", {
                "query": "SELECT TOP 5 TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
            })
            
            if result and result[0].text:
                logger.info(f"Table list query results for server {server_name}:")
                logger.info(result[0].text)
            else:
                logger.error(f"Failed to retrieve table list for server {server_name}")
        except Exception as e:
            logger.error(f"Error executing table list query: {str(e)}")
        
        # Test case: Get database version
        try:
            result = await call_tool("execute_sql", {
                "query": "SELECT @@VERSION AS version"
            })
            
            if result and result[0].text:
                logger.info(f"Version information for server {server_name}:")
                logger.info(result[0].text)
            else:
                logger.error(f"Failed to retrieve version information for server {server_name}")
        except Exception as e:
            logger.error(f"Error executing version query: {str(e)}")
    
    logger.info("SQL execution test on Windows servers completed")

if __name__ == "__main__":
    asyncio.run(test_execute_sql_on_windows_servers())

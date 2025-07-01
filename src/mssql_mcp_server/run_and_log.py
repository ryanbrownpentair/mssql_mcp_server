"""
Script to run the MCP server and log any errors.
"""
import subprocess
import sys
import logging
import os
import datetime

# Configure logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"mcp_server_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Configure logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("mcp_run")

def run_mcp_server():
    """Run the MCP server using uv and log any errors."""
    logger.info("Starting MCP server with uv run...")
    
    try:
        # Get the directory containing the package
        package_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        logger.info(f"Package directory: {package_dir}")
        
        # Run the server using uv
        result = subprocess.run(
            ["uv", "run", "mssql_mcp_server"],
            cwd=package_dir,
            capture_output=True,
            text=True
        )
        
        # Log standard output
        for line in result.stdout.splitlines():
            logger.info(f"SERVER: {line}")
        
        # Log any errors
        if result.stderr:
            logger.error("Errors from MCP server:")
            for line in result.stderr.splitlines():
                logger.error(f"SERVER ERROR: {line}")
            
        # Log return code
        logger.info(f"Server process exited with code: {result.returncode}")
        
        return result.returncode
        
    except Exception as e:
        logger.error(f"Failed to run MCP server: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(run_mcp_server())

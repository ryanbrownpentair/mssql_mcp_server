import asyncio
import logging
import os
import pymssql
import msal  # For Microsoft Authentication
from dotenv import load_dotenv  # For .env file support
from mcp.server import Server
from mcp.types import Resource, Tool, TextContent
from pydantic import AnyUrl
from .server_manager import get_server_manager

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mssql_mcp_server")

def get_db_config():
    """Get database configuration from environment variables.
    
    Supports both SQL authentication and Entra ID authentication.
    For Entra ID, it can use either service principal (client_secret) or user credentials.
    """
    # Get authentication type (SQL or Entra)
    auth_type = os.getenv("MSSQL_AUTH_TYPE", "sql").lower()
    
    config = {
        "server": os.getenv("MSSQL_SERVER", "localhost"),
        "database": os.getenv("MSSQL_DATABASE")
    }
    
    # Basic validation
    if not config["database"]:
        logger.error("Missing required database configuration. MSSQL_DATABASE is required")
        raise ValueError("Missing required database configuration")
    
    # Get configuration based on authentication type
    if auth_type == "sql":
        # SQL authentication (existing method)
        config["user"] = os.getenv("MSSQL_USER")
        config["password"] = os.getenv("MSSQL_PASSWORD")
        
        if not all([config["user"], config["password"]]):
            logger.error("SQL authentication requires both MSSQL_USER and MSSQL_PASSWORD")
            raise ValueError("Missing SQL authentication credentials")
            
    elif auth_type == "entra":
        # Entra ID authentication
        config["auth_type"] = "entra"
        config["client_id"] = os.getenv("MSSQL_CLIENT_ID")
        config["tenant_id"] = os.getenv("MSSQL_TENANT_ID")
        config["client_secret"] = os.getenv("MSSQL_CLIENT_SECRET")
        config["username"] = os.getenv("MSSQL_ENTRA_USERNAME")  # For UserID authentication
        
        if not all([config["client_id"], config["tenant_id"]]):
            logger.error("Entra authentication requires MSSQL_CLIENT_ID and MSSQL_TENANT_ID")
            raise ValueError("Missing Entra ID configuration")
            
        # Either username or client_secret is required for authentication
        if not config["username"] and not config["client_secret"]:
            logger.error("Entra authentication requires either a username or client_secret")
            raise ValueError("Missing Entra ID credentials")
    else:
        logger.error(f"Unknown authentication type: {auth_type}. Use 'sql' or 'entra'.")
        raise ValueError(f"Unknown authentication type: {auth_type}")
    
    return config

def get_entra_token(config):
    """Acquire an access token from Entra ID (formerly Azure AD).
    
    Supports both service principal authentication (using client_secret)
    and user authentication (using username/password).
    
    Args:
        config: Dictionary containing authentication parameters
        
    Returns:
        str: Access token for SQL Server authentication
        
    Raises:
        ValueError: If token acquisition fails
    """
    if "client_secret" in config and config["client_secret"]:
        # Application authentication (service principal)
        app = msal.ConfidentialClientApplication(
            config["client_id"],
            authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
            client_credential=config["client_secret"]
        )
        result = app.acquire_token_for_client(scopes=["https://database.windows.net/.default"])
    else:
        # User ID authentication
        app = msal.PublicClientApplication(
            config["client_id"],
            authority=f"https://login.microsoftonline.com/{config['tenant_id']}"
        )
        # Use username/password if available, otherwise this would require interactive login
        password = os.getenv("MSSQL_ENTRA_PASSWORD")
        if password:
            result = app.acquire_token_by_username_password(
                config["username"],
                password,
                scopes=["https://database.windows.net/.default"]
            )
        else:
            # Interactive authentication not supported in this implementation
            logger.error("Interactive Entra authentication not supported in this implementation")
            raise ValueError("Interactive Entra authentication not supported")
    
    if "access_token" not in result:
        error_desc = result.get('error_description', result.get('error', 'Unknown error'))
        logger.error(f"Token acquisition error: {error_desc}")
        raise ValueError(f"Failed to acquire token: {error_desc}")
        
    return result["access_token"]

def create_connection(config):
    """Create a database connection based on the provided configuration.
    
    Supports both SQL authentication and Entra ID authentication.
    
    Args:
        config: Dictionary containing connection parameters
        
    Returns:
        pymssql.Connection: Database connection
        
    Raises:
        Exception: If connection fails
    """
    try:
        if config.get("auth_type") == "entra":
            # Entra ID authentication
            token = get_entra_token(config)
            
            # Note: pymssql might not directly support Entra token authentication
            # In a production environment, you might need to use pyodbc or another driver
            # This is a simplified implementation that might need adjustments
            conn = pymssql.connect(
                server=config["server"],
                database=config["database"],
                user=config.get("username", ""),  # For UserID authentication
                password=token,  # Use token as password
                # Additional connection properties
                conn_properties="Authentication=ActiveDirectoryServicePrincipal"
            )
        else:
            # Regular SQL authentication (existing method)
            conn = pymssql.connect(
                server=config["server"],
                user=config["user"],
                password=config["password"],
                database=config["database"]
            )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

# Initialize server
app = Server("mssql_mcp_server")

@app.list_resources()
async def list_resources() -> list[Resource]:
    """List SQL Server tables as resources and available servers."""
    server_manager = get_server_manager()
    resources = []
    
    # Add servers as resources
    for server in server_manager.get_server_list():
        resources.append(
            Resource(
                uri=f"mssql://{server.name}",
                name=f"Server: {server.display_name}",
                mimeType="text/plain",
                description=f"SQL Server connection: {server.display_name}"
            )
        )
    
    # Add tables from the active server
    config = server_manager.get_active_config()
    if not config:
        logger.error("No active server configuration available")
        return resources
        
    try:
        conn = create_connection(config)
        cursor = conn.cursor()
        # Query to get user tables from the current database
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
        """)
        tables = cursor.fetchall()
        
        active_server = server_manager.active_server
        for table in tables:
            resources.append(
                Resource(
                    uri=f"mssql://{active_server}/tables/{table[0]}",
                    name=f"Table: {table[0]}",
                    mimeType="text/plain",
                    description=f"Data in table: {table[0]} (Server: {active_server})"
                )
            )
        cursor.close()
        conn.close()
        return resources
    except Exception as e:
        logger.error(f"Failed to list resources: {str(e)}")
        return resources

@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read server or table contents."""
    uri_str = str(uri)
    logger.info(f"Reading resource: {uri_str}")
    
    if not uri_str.startswith("mssql://"):
        raise ValueError(f"Invalid URI scheme: {uri_str}")
    
    server_manager = get_server_manager()
    parts = uri_str[8:].split('/')
    server_name = parts[0]
    
    # Check if URI refers to a server configuration
    if len(parts) == 1:
        server = server_manager.get_server_by_name(server_name)
        if not server:
            raise ValueError(f"Unknown server: {server_name}")
            
        # Activate this server
        server_manager.set_active_server(server_name)
        
        # Return server information
        return f"Server: {server.display_name}\nConnection activated."
    
    # Check if URI refers to a table
    if len(parts) >= 3 and parts[1] == "tables":
        table = parts[2]
        server = server_manager.get_server_by_name(server_name)
        if not server:
            raise ValueError(f"Unknown server: {server_name}")
            
        try:
            conn = create_connection(server.config)
            cursor = conn.cursor()
            # Use TOP 100 for MSSQL (equivalent to LIMIT in MySQL)
            cursor.execute(f"SELECT TOP 100 * FROM {table}")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = [",".join(map(str, row)) for row in rows]
            cursor.close()
            conn.close()
            return "\n".join([",".join(columns)] + result)
        except Exception as e:
            logger.error(f"Database error reading resource {uri}: {str(e)}")
            raise RuntimeError(f"Database error: {str(e)}")
    
    raise ValueError(f"Invalid resource URI: {uri_str}")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available SQL Server tools."""
    logger.info("Listing tools...")
    return [
        Tool(
            name="execute_sql",
            description="Execute an SQL query on the active SQL Server",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute"
                    },
                    "server": {
                        "type": "string",
                        "description": "The server name to execute the query on (optional, uses active server if not specified)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="switch_server",
            description="Switch to a different SQL Server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": "The server name to switch to"
                    }
                },
                "required": ["server"]
            }
        ),
        Tool(
            name="list_servers",
            description="List all available SQL Server connections",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute SQL commands or manage server connections."""
    server_manager = get_server_manager()
    logger.info(f"Calling tool: {name} with arguments: {arguments}")
    
    # Handle server management tools
    if name == "list_servers":
        servers = server_manager.get_server_list()
        active = server_manager.active_server
        
        result = ["Available SQL Server connections:"]
        for server in servers:
            if server.name == active:
                result.append(f"* {server.display_name} (ACTIVE)")
            else:
                result.append(f"  {server.display_name}")
                
        return [TextContent(type="text", text="\n".join(result))]
        
    elif name == "switch_server":
        server_name = arguments.get("server")
        if not server_name:
            return [TextContent(type="text", text="Error: Server name is required")]
            
        if server_manager.set_active_server(server_name):
            server = server_manager.get_server_by_name(server_name)
            return [TextContent(
                type="text", 
                text=f"Switched to server: {server.display_name}"
            )]
        else:
            available = ", ".join([s.name for s in server_manager.get_server_list()])
            return [TextContent(
                type="text", 
                text=f"Error: Unknown server '{server_name}'. Available servers: {available}"
            )]
    
    # Handle SQL execution
    elif name == "execute_sql":
        query = arguments.get("query")
        if not query:
            return [TextContent(type="text", text="Error: Query is required")]
            
        # Determine which server to use
        server_name = arguments.get("server")
        if server_name:
            if not server_manager.set_active_server(server_name):
                available = ", ".join([s.name for s in server_manager.get_server_list()])
                return [TextContent(
                    type="text", 
                    text=f"Error: Unknown server '{server_name}'. Available servers: {available}"
                )]
                
        # Get active server configuration
        config = server_manager.get_active_config()
        if not config:
            return [TextContent(type="text", text="Error: No active server configuration available")]
    
        try:
            conn = create_connection(config)
            cursor = conn.cursor()
            cursor.execute(query)
            
            # Special handling for table listing
            if query.strip().upper().startswith("SELECT") and "INFORMATION_SCHEMA.TABLES" in query.upper():
                tables = cursor.fetchall()
                result = ["Tables_in_" + config["database"]]  # Header
                result.extend([table[0] for table in tables])
                cursor.close()
                conn.close()
                return [TextContent(type="text", text="\n".join(result))]
            
            # Regular SELECT queries
            elif query.strip().upper().startswith("SELECT"):
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = [",".join(map(str, row)) for row in rows]
                cursor.close()
                conn.close()
                return [TextContent(type="text", text="\n".join([",".join(columns)] + result))]
            
            # Non-SELECT queries
            else:
                conn.commit()
                affected_rows = cursor.rowcount
                cursor.close()
                conn.close()
                return [TextContent(type="text", text=f"Query executed successfully. Rows affected: {affected_rows}")]
                    
        except Exception as e:
            logger.error(f"Error executing SQL '{query}': {e}")
            return [TextContent(type="text", text=f"Error executing query: {str(e)}")]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    """Main entry point to run the MCP server."""
    from mcp.server.stdio import stdio_server
    
    logger.info("Starting MSSQL MCP server...")
    
    # Initialize server manager
    server_manager = get_server_manager()
    active_server = server_manager.active_server
    
    if active_server:
        server = server_manager.get_server_by_name(active_server)
        logger.info(f"Active server: {server.display_name}")
        
        # Log available servers
        servers = server_manager.get_server_list()
        if len(servers) > 1:
            logger.info(f"Available servers: {', '.join([s.name for s in servers])}")
    else:
        logger.warning("No active server configuration available")
    
    async with stdio_server() as (read_stream, write_stream):
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
        except Exception as e:
            logger.error(f"Server error: {str(e)}", exc_info=True)
            raise

if __name__ == "__main__":
    asyncio.run(main())

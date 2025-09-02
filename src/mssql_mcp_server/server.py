import asyncio
import logging
import os
import json
import webbrowser
import time
import pyodbc  # pymssqlからpyodbcに変更
import msal  # For Microsoft Authentication
from dotenv import load_dotenv  # For .env file support
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ProgressNotification,
    InitializedNotification,
    RootsListChangedNotification,
)
from pydantic import AnyUrl, BaseModel, Field
from typing import Literal, Union, Type
from .server_manager import get_server_manager

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mssql_mcp_server")

# 新しい通知タイプを定義します
class CancelledNotificationParams(BaseModel):
    request_id: int = Field(..., alias="requestId")

class CancelledNotification(BaseModel):
    method: Literal["notifications/cancelled"]
    params: CancelledNotificationParams

# mcp.server.Server がデフォルトで知っている通知タイプに、新しいタイプを追加します
ClientNotification = Union[
    ProgressNotification,
    InitializedNotification,
    RootsListChangedNotification,
    CancelledNotification,
]

def get_db_config():
    """Get database configuration from environment variables.
    
    Supports SQL authentication, Windows authentication, and Entra ID authentication.
    """
    # Get authentication type (SQL, Windows, or Entra)
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
    
    elif auth_type == "windows":
        # Windows authentication
        config["auth_type"] = "windows"
        logger.info(f"Using Windows authentication for server {config['server']}")
            
    elif auth_type == "entra":
        # Entra ID authentication
        config["auth_type"] = "entra"
        config["client_id"] = os.getenv("MSSQL_CLIENT_ID")
        config["tenant_id"] = os.getenv("MSSQL_TENANT_ID")
        config["client_secret"] = os.getenv("MSSQL_CLIENT_SECRET")
        config["username"] = os.getenv("MSSQL_ENTRA_USERNAME")  # For UserID authentication
        
        # Interactive auth settings
        auth_mode = os.getenv("MSSQL_AUTH_MODE", "").lower()
        if auth_mode == "interactive":
            config["auth_mode"] = "interactive"
            config["token_cache_file"] = os.getenv("MSSQL_TOKEN_CACHE_FILE")
            config["use_device_code"] = os.getenv("MSSQL_USE_DEVICE_CODE", "").lower() in ("true", "yes", "1")
        
        if not all([config["client_id"], config["tenant_id"]]):
            logger.error("Entra authentication requires MSSQL_CLIENT_ID and MSSQL_TENANT_ID")
            raise ValueError("Missing Entra ID configuration")
            
        # For interactive auth, we don't need username/password or client_secret
        if config.get("auth_mode") == "interactive":
            pass  # No additional validation needed
        # For non-interactive auth, either username or client_secret is required
        elif not config["username"] and not config["client_secret"]:
            logger.error("Entra authentication requires either a username or client_secret")
            raise ValueError("Missing Entra ID credentials")
    else:
        logger.error(f"Unknown authentication type: {auth_type}. Use 'sql', 'windows', or 'entra'.")
        raise ValueError(f"Unknown authentication type: {auth_type}")
    
    return config

def load_token_cache(cache_file_path):
    """Load token cache from file if it exists.
    
    Args:
        cache_file_path: Path to the token cache file
        
    Returns:
        dict: Token cache or empty dict if file doesn't exist
    """
    if not cache_file_path:
        return {}
    
    try:
        if os.path.exists(cache_file_path):
            with open(cache_file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load token cache: {str(e)}")
    
    return {}

def save_token_cache(cache_data, cache_file_path):
    """Save token cache to file.
    
    Args:
        cache_data: Token cache data to save
        cache_file_path: Path to save the cache file
    """
    if not cache_file_path:
        return
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(cache_file_path)), exist_ok=True)
        
        with open(cache_file_path, 'w') as f:
            json.dump(cache_data, f)
    except Exception as e:
        logger.warning(f"Failed to save token cache: {str(e)}")

def get_entra_token(config):
    """Acquire an access token from Entra ID (formerly Azure AD).
    
    Supports multiple authentication methods:
    1. Service principal authentication (using client_secret)
    2. User authentication (using username/password)
    3. Interactive browser-based authentication
    4. Device code flow authentication
    
    Args:
        config: Dictionary containing authentication parameters
        
    Returns:
        str: Access token for SQL Server authentication
        
    Raises:
        ValueError: If token acquisition fails
    """
    # Define the scope for SQL Server
    scopes = ["https://database.windows.net/.default"]
    
    # Initialize token cache if specified
    token_cache = None
    if "token_cache_file" in config and config["token_cache_file"]:
        cache_file_path = config["token_cache_file"]
        token_cache = msal.SerializableTokenCache()
        token_cache.deserialize(json.dumps(load_token_cache(cache_file_path)))
    
    # Client ID and tenant ID are required for all flows
    client_id = config["client_id"]
    tenant_id = config["tenant_id"]
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    
    # Check the authentication mode
    if config.get("auth_mode") == "interactive":
        # Interactive authentication
        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=authority,
            token_cache=token_cache
        )
        
        # Check if we already have a cached token
        accounts = app.get_accounts()
        if accounts:
            logger.info(f"Found cached account: {accounts[0]['username']}")
            # Try to silently acquire token from cache
            result = app.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                logger.info("Successfully acquired token from cache")
                return result["access_token"]

        use_device_code = str(config.get("use_device_code", "false")).lower() == "true"

        if use_device_code:
            # For interactive auth, use device code flow to avoid redirect URI issues
            logger.info("Starting device code flow authentication")
            # Device code flow (useful for environments without browsers)
            flow = app.initiate_device_flow(scopes=scopes)

            if "user_code" not in flow:
                error = flow.get("error", "Unknown error")
                error_desc = flow.get("error_description", "No description")
                logger.error(f"Failed to initiate device code flow: {error} - {error_desc}")
                raise ValueError(f"Failed to initiate device code flow: {error}")

            # Display instructions to the user
            logger.info("\n" + "-" * 60)
            logger.info("MICROSOFT ENTRA ID AUTHENTICATION REQUIRED")
            logger.info("-" * 60)
            logger.info(f"To sign in, use a web browser to open the page {flow['verification_uri']}")
            logger.info(f"and enter the code {flow['user_code']} to authenticate.")
            logger.info("-" * 60 + "\n")

            # Wait for user to complete the flow
            result = app.acquire_token_by_device_flow(flow)
        else:
            logger.info("Starting interactive browser authentication")
            result = app.acquire_token_interactive(scopes=scopes)

    elif "client_secret" in config and config["client_secret"]:
        # Application authentication (service principal)
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=authority,
            client_credential=config["client_secret"],
            token_cache=token_cache
        )
        result = app.acquire_token_for_client(scopes=scopes)
    else:
        # User ID authentication
        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=authority,
            token_cache=token_cache
        )
        # Use username/password if available, otherwise raise error
        password = os.getenv("MSSQL_ENTRA_PASSWORD")
        if config["username"] and password:
            result = app.acquire_token_by_username_password(
                config["username"],
                password,
                scopes=scopes
            )
        else:
            # This is now a configuration error, since we support interactive auth
            logger.error("Missing credentials for non-interactive authentication")
            raise ValueError("Missing credentials for non-interactive authentication")
    
    # Save token cache if specified
    if token_cache and config.get("token_cache_file"):
        cache_data = json.loads(token_cache.serialize())
        save_token_cache(cache_data, config["token_cache_file"])
    
    # Check if token acquisition was successful
    if "access_token" not in result:
        error_desc = result.get('error_description', result.get('error', 'Unknown error'))
        logger.error(f"Token acquisition error: {error_desc}")
        raise ValueError(f"Failed to acquire token: {error_desc}")
    
    logger.info("Successfully acquired Entra ID token")
    return result["access_token"]

def create_connection(config, timeout=30, debug=False):
    """Create a database connection based on the provided configuration.
    
    Supports SQL authentication, Windows authentication, and Entra ID authentication.
    
    Args:
        config: Dictionary containing connection parameters
        timeout: Connection timeout in seconds (default: 30)
        debug: Enable verbose debugging output
        
    Returns:
        pyodbc.Connection: Database connection
        
    Raises:
        Exception: If connection fails
    """
    if debug:
        logger.info(f"Connection attempt to {config['server']}/{config['database']} with timeout={timeout}s")
        logger.info(f"Connection parameters: {config}")
    
    try:
        # Convert authentication type to lowercase for case-insensitive comparison
        auth_type = config.get("auth_type", "").lower()
        
        # 基本接続文字列パーツを構築
        conn_str_parts = [
            f"DRIVER={{ODBC Driver 17 for SQL Server}}",  # 最新のSQLサーバードライバー
            f"SERVER={config['server']}",
            f"DATABASE={config['database']}",
            f"Timeout={timeout}",
            f"Connection Timeout={timeout}",
            f"Query Timeout={timeout}"  # クエリ実行タイムアウトを追加
        ]
        
        # 暗号化設定
        encryption = config.get("encryption", os.getenv("ENCRYPTION"))
        if encryption:
            conn_str_parts.append(f"Encryption={encryption}")
        
        if debug:
            logger.info(f"Using authentication type: {auth_type}")
        
        if auth_type == "entra":
            # Entra ID認証
            conn_str_parts.append("Authentication=ActiveDirectoryInteractive")
            if config.get("user"):
                conn_str_parts.append(f"UID={config['user']}")
            
            # Entra ID (Interactive) ではパスワードは不要
            # ユーザーはプロンプトで資格情報を入力します
            if debug:
                logger.info("Configuring for Entra ID Interactive authentication. User will be prompted.")

            
        elif auth_type == "windows":
            # Windows認証
            conn_str_parts.append("Trusted_Connection=yes")
            logger.info(f"Connecting to {config['server']}/{config['database']} using Windows authentication")
            
        else:
            # 通常のSQL認証
            conn_str_parts.append(f"UID={config['user']}")
            conn_str_parts.append(f"PWD={config['password']}")
        
        # 接続文字列を構築
        conn_str = ';'.join(conn_str_parts)
        
        if debug:
            debug_conn_str = conn_str.replace(config.get('password', ''), '******') if 'password' in config else conn_str
            logger.info(f"Attempting connection with connection string: {debug_conn_str}")
            
        conn = pyodbc.connect(conn_str)
        
        if debug:
            logger.info(f"Connection to {config['server']}/{config['database']} established successfully")
            
        return conn
    except Exception as e:
        error_msg = f"Database connection error: {str(e)}"
        logger.error(error_msg)
        if debug:
            logger.error(f"Connection parameters: server={config['server']}, database={config['database']}, auth_type={config.get('auth_type', 'sql')}")
            # Log full exception details in debug mode
            import traceback
            logger.error(f"Full exception: {traceback.format_exc()}")
        raise

class MssqlMcpServer(Server):
    """Custom server to handle additional notification types."""

    @property
    def _receive_notification_type(self) -> Type[BaseModel]:
        return ClientNotification


# Initialize server
app = MssqlMcpServer("mssql_mcp_server")


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
            # pyodbcはタプルではなくpyodbc.Rowを返すので、必要に応じて変換
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
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Maximum number of rows to return (default: 100)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="debug_connection",
            description="Debug the database connection with detailed diagnostics",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional SQL query to execute as part of the test"
                    },
                    "server": {
                        "type": "string",
                        "description": "The server name to debug (optional, uses active server if not specified)"
                    }
                }
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
        ),
        Tool(
            name="refresh_auth",
            description="Refresh the authentication for the current server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": "The server name to refresh authentication for (optional, uses active server if not specified)"
                    }
                }
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
            auth_type = server.config.get("auth_type", "sql")
            auth_mode = server.config.get("auth_mode", "")
            auth_info = "SQL Auth"
            
            if auth_type == "entra":
                if auth_mode == "interactive":
                    auth_info = "Entra ID (Interactive)"
                elif server.config.get("client_secret"):
                    auth_info = "Entra ID (Service Principal)"
                elif server.config.get("username"):
                    auth_info = "Entra ID (Username)"
            
            if server.name == active:
                result.append(f"* {server.display_name} [{auth_info}] (ACTIVE)")
            else:
                result.append(f"  {server.display_name} [{auth_info}]")
                
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
    
    elif name == "refresh_auth":
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
        server_name = server_manager.active_server
        config = server_manager.get_active_config()
        if not config:
            return [TextContent(type="text", text="Error: No active server configuration available")]
        
        # Only attempt to refresh Entra ID authentication
        if config.get("auth_type") != "entra":
            return [TextContent(
                type="text", 
                text=f"Error: Server '{server_name}' does not use Entra ID authentication"
            )]
        
        try:
            # Force token refresh by clearing token cache if it exists
            if config.get("token_cache_file") and os.path.exists(config["token_cache_file"]):
                os.remove(config["token_cache_file"])
                
            # Test connection to force new authentication
            conn = create_connection(config)
            conn.close()
            
            return [TextContent(
                type="text", 
                text=f"Authentication refreshed successfully for server: {server_name}"
            )]
        except Exception as e:
            logger.error(f"Failed to refresh authentication: {str(e)}")
            return [TextContent(
                type="text", 
                text=f"Error refreshing authentication: {str(e)}"
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
    
        # Get max_rows parameter with default value of 100
        max_rows = int(arguments.get("max_rows", 100))
        
        # Log the query before execution for better tracking
        query_type = "SELECT" if query.strip().upper().startswith("SELECT") else "UPDATE/INSERT/DELETE/OTHER"
        logger.info(f"Executing {query_type} query on server {config['server']}/{config['database']}: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        start_time = time.time()
        
        try:
            conn = create_connection(config)
            logger.info(f"Connection established to {config['server']}/{config['database']}, executing query...")
            
            cursor = conn.cursor()
            cursor.execute(query)
            logger.info(f"Query executed successfully on {config['server']}/{config['database']}")
            
            # 結果セットのメタデータ
            result_meta = []
            result_meta.append(f"-- Server: {config['server']}")
            result_meta.append(f"-- Database: {config['database']}")
            result_meta.append(f"-- Query type: {query_type}")
            
            # Special handling for table listing
            if query.strip().upper().startswith("SELECT") and "INFORMATION_SCHEMA.TABLES" in query.upper():
                tables = cursor.fetchall()
                logger.info(f"Retrieved {len(tables)} tables from INFORMATION_SCHEMA")
                result = result_meta.copy()
                result.append("")
                result.append("Tables_in_" + config["database"])  # Header
                result.extend([table[0] for table in tables])
                cursor.close()
                conn.close()
                execution_time = round(time.time() - start_time, 2)
                logger.info(f"Query completed in {execution_time} seconds")
                result.append("")
                result.append(f"-- Execution time: {execution_time} seconds")
                result.append(f"-- Row count: {len(tables)}")
                return [TextContent(type="text", text="\n".join(result))]
            
            # Regular SELECT queries
            elif query.strip().upper().startswith("SELECT"):
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                total_rows = len(rows)
                logger.info(f"Retrieved {total_rows} rows from {config['server']}/{config['database']}")
                
                # 結果の制限
                displayed_rows = rows[:max_rows]
                
                # pyodbcの行データを文字列に変換
                result = result_meta.copy()
                result.append("")
                result.append(",".join(columns))
                for row in displayed_rows:
                    result.append(",".join(map(lambda x: str(x).replace(',', '\\,') if x is not None else 'NULL', row)))
                
                cursor.close()
                conn.close()
                execution_time = round(time.time() - start_time, 2)
                logger.info(f"Query completed in {execution_time} seconds")
                
                # 結果セットが制限された場合の情報を追加
                if total_rows > max_rows:
                    result.append("")
                    result.append(f"-- Note: Showing {max_rows} of {total_rows} total rows")
                
                result.append("")
                result.append(f"-- Execution time: {execution_time} seconds")
                result.append(f"-- Row count: {total_rows}")
                return [TextContent(type="text", text="\n".join(result))]
            
            # Non-SELECT queries
            else:
                conn.commit()
                affected_rows = cursor.rowcount
                logger.info(f"Non-SELECT query affected {affected_rows} rows in {config['server']}/{config['database']}")

                # Capture messages from the connection (e.g., PRINT statements)
                messages = []
                if hasattr(conn, 'messages') and conn.messages:
                    for message in conn.messages:
                        # The message format is typically [SQLSTATE] message (native_error)
                        # We'll just extract the message part.
                        msg_text = message[1]
                        messages.append(msg_text)
                        logger.info(f"Captured message from server: {msg_text}")

                cursor.close()
                conn.close()
                execution_time = round(time.time() - start_time, 2)
                logger.info(f"Query completed in {execution_time} seconds")
                
                result = result_meta.copy()
                result.append("")
                result.append(f"Query executed successfully.")
                result.append(f"Rows affected: {affected_rows}")

                if messages:
                    result.append("\nServer Messages:")
                    result.extend([f"- {msg}" for msg in messages])
                
                result.append("")
                result.append(f"-- Execution time: {execution_time} seconds")
                return [TextContent(type="text", text="\n".join(result))]
        
        except Exception as e:
            execution_time = round(time.time() - start_time, 2)
            logger.error(f"Error executing SQL on {config.get('server', 'unknown')}/{config.get('database', 'unknown')} after {execution_time} seconds: {str(e)}")
            logger.error(f"Failed query: {query}")
            
            # エラー情報を追加
            error_message = [
                f"Error executing query after {execution_time} seconds:",
                str(e),
                "",
                "Query:",
                query
            ]
            return [TextContent(type="text", text="\n".join(error_message))]
    # Handle connection debugging
    elif name == "debug_connection":
        import socket
        import traceback
        from contextlib import contextmanager
        from pathlib import Path
        
        # Define time measurement context manager
        @contextmanager
        def measure_time(description):
            """処理時間を計測するコンテキストマネージャー"""
            start_time = time.time()
            yield
            elapsed_time = time.time() - start_time
            logger.info(f"{description}: {elapsed_time:.2f}秒")
        
        # 環境設定ファイルから特定のセクションの設定を読み込む関数
        def load_env_config(section=None):
            """環境設定ファイルから設定を読み込む"""
            # デフォルトサーバーを取得
            default_server = os.getenv("MSSQL_DEFAULT_SERVER")
            if section is None:
                section = default_server
                logger.info(f"デフォルトサーバーを使用します: {section}")
            
            # 指定されたセクションの設定を読み込む
            env_path = Path('.env')
            if not env_path.exists():
                logger.error("エラー: .env ファイルが見つかりません")
                return {}
                
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                # UTF-8でダメな場合はLatin-1で試みる
                with open(env_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            
            in_section = False
            config = {}
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    in_section = (current_section == section)
                    continue
                    
                if in_section and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
            
            return config
        
        # .envファイルの設定を使って接続テストを行う関数
        def test_connection(config):
            """設定を使用してデータベース接続をテスト"""
            auth_type = config.get('MSSQL_AUTH_TYPE', '').lower()
            server = config.get('MSSQL_SERVER', '')
            database = config.get('MSSQL_DATABASE', '')
            encryption = config.get('ENCRYPTION', 'yes')
            
            if not server or not database:
                logger.error("エラー: サーバーまたはデータベースが設定されていません")
                return False
            
            try:
                conn_str = []
                conn_str.append(f"DRIVER={{ODBC Driver 17 for SQL Server}}")
                conn_str.append(f"SERVER={server}")
                conn_str.append(f"DATABASE={database}")
                
                if auth_type == 'windows':
                    conn_str.append("Trusted_Connection=yes")
                elif auth_type == 'sql':
                    user = config.get('MSSQL_USER', '')
                    password = config.get('MSSQL_PASSWORD', '')
                    conn_str.append(f"UID={user}")
                    conn_str.append(f"PWD={password}")
                
                if encryption.lower() == 'optional':
                    conn_str.append("Encryption=Optional")
                
                conn_string = ';'.join(conn_str)
                safe_conn_string = conn_string
                if auth_type == 'sql':
                    safe_conn_string = safe_conn_string.replace(password, '******')
                logger.info(f"接続文字列: {safe_conn_string}")
                
                conn = pyodbc.connect(conn_string)
                cursor = conn.cursor()
                cursor.execute("SELECT @@VERSION")
                row = cursor.fetchone()
                logger.info(f"接続成功: SQL Server バージョン: {row[0]}")
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                logger.error(f"接続エラー: {str(e)}")
                return False
        
        # Determine which server to use
        server_name = arguments.get("server")
        if server_name:
            if not server_manager.set_active_server(server_name):
                available = ", ".join([s.name for s in server_manager.get_server_list()])
                return [TextContent(
                    type="text", 
                    text=f"エラー: 不明なサーバー '{server_name}'。利用可能なサーバー: {available}"
                )]
                
        # Get active server configuration
        config = server_manager.get_active_config()
        if not config:
            return [TextContent(type="text", text="エラー: アクティブなサーバー設定がありません")]
        
        # 詳細出力を有効化
        detailed = True
        
        # Get custom query if provided
        custom_query = arguments.get("query")
        
        # Start diagnostic results collection
        result = []
        result.append("=== SQL Server接続デバッグツール ===")
        
        # 設定情報を表示
        result.append(f"\nサーバー: {config['server']}")
        result.append(f"データベース: {config['database']}")
        result.append(f"認証タイプ: {config.get('auth_type', 'sql')}")
        
        # 利用可能なODBCドライバーを表示
        result.append(f"利用可能なODBCドライバー: {', '.join(pyodbc.drivers())}")
        
        # ステップ1: ネットワーク接続テスト
        result.append("\nステップ1: ネットワーク接続のテスト...")
        server = config["server"]
        port = 1433  # SQL Serverの標準ポート
        
        try:
            with measure_time("ネットワーク接続"):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)  # 5秒のタイムアウト
                connect_result = sock.connect_ex((server, port))
                sock.close()
                
            if connect_result == 0:
                result.append(f"✓ ネットワーク接続成功: {server}:{port}に接続できました")
                network_success = True
            else:
                result.append(f"✗ ネットワーク接続失敗: {server}:{port}に接続できません（エラーコード: {connect_result}）")
                result.append("  - ファイアウォールの設定を確認してください")
                result.append("  - サーバー名が正しいか確認してください")
                result.append("  - SQLサーバーが実行中か確認してください")
                network_success = False
        except socket.gaierror:
            result.append(f"✗ ネットワーク接続失敗: ホスト名'{server}'の解決ができません")
            result.append("  - サーバー名のスペルが正しいか確認してください")
            result.append("  - DNSの設定を確認してください")
            network_success = False
        except Exception as e:
            result.append(f"✗ ネットワーク接続テスト中にエラーが発生しました: {str(e)}")
            network_success = False
        
        if not network_success:
            return [TextContent(type="text", text="\n".join(result))]
        
        # ステップ2: SQL Server接続テスト
        result.append("\nステップ2: SQL Server接続のテスト...")
        
        # pyodbcに適した接続文字列パーツを構築
        conn_str_parts = [
            f"DRIVER={{ODBC Driver 17 for SQL Server}}",
            f"SERVER={config['server']}",
            f"DATABASE={config['database']}",
            f"Connection Timeout={30}"
        ]
        
        # 暗号化設定
        encryption = config.get("encryption", os.getenv("ENCRYPTION"))
        if encryption:
            conn_str_parts.append(f"Encryption={encryption}")
        
        # 認証タイプに応じてパラメータを追加
        auth_type = config.get("auth_type", "sql").lower()
        
        if auth_type == "sql":
            conn_str_parts.append(f"UID={config['user']}")
            conn_str_parts.append(f"PWD={config['password']}")
            auth_info = "SQL認証"
        elif auth_type == "windows":
            conn_str_parts.append("Trusted_Connection=yes")
            auth_info = "Windows認証"
        elif auth_type == "entra":
            auth_info = "Entra ID認証"
            # Entra ID認証の詳細は後で処理
        else:
            auth_info = "不明な認証方式"
        
        # 安全な接続文字列をログに記録
        safe_conn_str = ';'.join(conn_str_parts)
        if auth_type == "sql":
            safe_conn_str = safe_conn_str.replace(config.get('password', ''), '******')
        
        result.append(f"接続パラメータ: {safe_conn_str}")
        result.append(f"認証タイプ: {auth_info}")
        
        try:
            with measure_time("SQL Server接続"):
                conn = create_connection(config, debug=True)
            result.append(f"✓ SQL Server接続成功: {config['server']}/{config['database']}に接続できました")
            connection_success = True
        except Exception as e:
            result.append(f"✗ SQL Server接続失敗: {str(e)}")
            if detailed:
                result.append("詳細なエラー情報:")
                result.append(traceback.format_exc())
            
            # エラーの種類に応じたヒントを表示
            error_str = str(e).lower()
            if "timeout" in error_str:
                result.append("  - ネットワークのタイムアウトが発生しました")
                result.append("  - ファイアウォールの設定を確認してください")
                result.append("  - タイムアウト時間を長くしてみてください")
            elif "login failed" in error_str:
                result.append("  - ユーザー名またはパスワードが間違っています")
                result.append("  - SQLユーザーがこのデータベースにアクセス権限を持っているか確認してください")
            elif "database" in error_str and "not exist" in error_str:
                result.append("  - 指定されたデータベースが存在しません")
            elif "driver" in error_str:
                result.append("  - 指定されたODBCドライバーが見つかりません")
                result.append(f"  - 利用可能なドライバー: {', '.join(pyodbc.drivers())}")
            elif "network" in error_str or "connection" in error_str:
                result.append("  - ネットワーク接続に問題があります")
                result.append("  - サーバー名が正しいか確認してください")
                result.append("  - SQL Serverが実行中か確認してください")
            connection_success = False
        
        if not connection_success:
            return [TextContent(type="text", text="\n".join(result))]
        
        # ステップ3: テストクエリの実行
        result.append("\nステップ3: テストクエリの実行...")
        
        try:
            with measure_time("クエリ実行"):
                cursor = conn.cursor()
                
                # カスタムクエリの実行またはバージョン情報のクエリ
                if custom_query:
                    result.append(f"カスタムクエリを実行: {custom_query}")
                    cursor.execute(custom_query)
                else:
                    cursor.execute("SELECT @@VERSION")
                
                rows = cursor.fetchall()
                cursor.close()
            
            if custom_query:
                result.append(f"✓ カスタムクエリ実行成功:")
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    result.append(",".join(columns))
                    for row in rows[:10]:  # 最大10行まで表示
                        result.append(",".join(map(str, row)))
                    if len(rows) > 10:
                        result.append(f"... 他 {len(rows) - 10} 行")
            else:
                result.append(f"✓ クエリ実行成功:")
                result.append(f"  - SQL Serverバージョン: {rows[0][0][:100]}...")
            
            query_success = True
        except Exception as e:
            result.append(f"✗ クエリ実行失敗: {str(e)}")
            result.append(traceback.format_exc())
            query_success = False
        
        # 接続を閉じる
        try:
            conn.close()
            result.append("SQL Server接続を正常に閉じました")
        except:
            pass
        
        # 最終結果
        if query_success:
            result.append("\n✓ すべてのテストが成功しました！SQL Server接続は正常に動作しています。")
        else:
            result.append("\n✗ テストに失敗しました。上記のエラーメッセージを確認してください。")
        
        # 環境設定からの接続テスト
        try:
            env_config = load_env_config()
            if env_config:
                result.append("\n=== 環境設定からの接続テスト ===")
                test_success = test_connection(env_config)
                if test_success:
                    result.append("✓ 環境設定からの接続も成功しました！")
                else:
                    result.append("✗ 環境設定からの接続テストに失敗しました。")
        except Exception as e:
            result.append(f"\n環境設定のロード中にエラーが発生しました: {str(e)}")
        
        return [TextContent(type="text", text="\n".join(result))]
        
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
        
        # Log authentication type
        config = server.config
        auth_type = config.get("auth_type", "").lower()
        
        if auth_type == "entra":
            if config.get("auth_mode") == "interactive":
                auth_method = "Entra ID (Interactive)"
                auth_details = f"using client ID {config['client_id']}"
                if config.get("use_device_code"):
                    auth_details += " with device code flow"
                else:
                    auth_details += " with browser flow"
            elif config.get("client_secret"):
                auth_method = "Entra ID (Service Principal)"
                auth_details = f"using client ID {config['client_id']}"
            else:
                auth_method = "Entra ID (Username/Password)"
                auth_details = f"as user {config.get('username', 'unknown')}"
        elif auth_type == "windows":
            auth_method = "Windows Authentication"
            auth_details = f"on server {config['server']}/{config['database']}"
        else:
            # SQL Authentication
            auth_method = "SQL Authentication"
            auth_details = f"as user {config.get('user', 'unknown')}"
        
        logger.info(f"Authentication: {auth_method} {auth_details}")
        
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

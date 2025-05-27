import configparser
import os
import logging
from typing import Dict, Optional, List

logger = logging.getLogger("mssql_mcp_server")

class ServerConfig:
    """Class to manage multiple SQL Server configurations."""
    
    def __init__(self, config_name: str, config: Dict):
        """Initialize a server configuration.
        
        Args:
            config_name: Name identifier for this server configuration
            config: Dictionary with connection parameters
        """
        self.name = config_name
        self.config = config
        
    @property
    def uri(self) -> str:
        """Get URI representation of this server."""
        return f"mssql://{self.name}/{self.config['database']}"
    
    @property
    def display_name(self) -> str:
        """Get display name for this server."""
        return f"{self.name} ({self.config['server']}/{self.config['database']})"


class ServerManager:
    """Manages multiple SQL server configurations."""
    
    def __init__(self):
        """Initialize the server manager."""
        self.servers: Dict[str, ServerConfig] = {}
        self.active_server: Optional[str] = None
        self._load_configurations()
        
    def _load_configurations(self):
        """Load server configurations from environment variables."""
        # Load the .env file if it exists
        from dotenv import load_dotenv
        load_dotenv()
        
        # Process the .env file as an INI file to extract sections
        config = configparser.ConfigParser()
        
        # Try to read the .env file directly
        env_path = os.path.join(os.getcwd(), '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                config.read_string('[global]\n' + f.read())
        
        # Get default server if specified
        self.active_server = os.getenv("MSSQL_DEFAULT_SERVER", "default")
        
        # Process each section as a server configuration
        for section in config.sections():
            if section == 'global':
                continue
                
            # Create server configuration from section
            server_config = {}
            
            # Get standard configuration parameters with section prefix
            prefix = f"{section}_"
            # First try with section prefix
            auth_type = os.getenv(f"{prefix}MSSQL_AUTH_TYPE", 
                                  # Then try with section as value from .env section
                                  config.get(section, "MSSQL_AUTH_TYPE", fallback="sql")).lower()
            
            server_config["auth_type"] = auth_type
            server_config["server"] = os.getenv(f"{prefix}MSSQL_SERVER", 
                                               config.get(section, "MSSQL_SERVER", fallback="localhost"))
            server_config["database"] = os.getenv(f"{prefix}MSSQL_DATABASE", 
                                                 config.get(section, "MSSQL_DATABASE", fallback=None))
            
            # Skip if required database parameter is missing
            if not server_config["database"]:
                logger.warning(f"Skipping server configuration '{section}': Missing database parameter")
                continue
            
            # Get auth-specific parameters
            if auth_type == "sql":
                server_config["user"] = os.getenv(f"{prefix}MSSQL_USER", 
                                                 config.get(section, "MSSQL_USER", fallback=None))
                server_config["password"] = os.getenv(f"{prefix}MSSQL_PASSWORD", 
                                                     config.get(section, "MSSQL_PASSWORD", fallback=None))
                
                if not all([server_config["user"], server_config["password"]]):
                    logger.warning(f"Skipping server configuration '{section}': Missing SQL credentials")
                    continue
                    
            elif auth_type == "entra":
                server_config["client_id"] = os.getenv(f"{prefix}MSSQL_CLIENT_ID", 
                                                      config.get(section, "MSSQL_CLIENT_ID", fallback=None))
                server_config["tenant_id"] = os.getenv(f"{prefix}MSSQL_TENANT_ID", 
                                                      config.get(section, "MSSQL_TENANT_ID", fallback=None))
                server_config["client_secret"] = os.getenv(f"{prefix}MSSQL_CLIENT_SECRET", 
                                                         config.get(section, "MSSQL_CLIENT_SECRET", fallback=None))
                server_config["username"] = os.getenv(f"{prefix}MSSQL_ENTRA_USERNAME", 
                                                     config.get(section, "MSSQL_ENTRA_USERNAME", fallback=None))
                
                if not all([server_config["client_id"], server_config["tenant_id"]]):
                    logger.warning(f"Skipping server configuration '{section}': Missing Entra ID configuration")
                    continue
                
                # Either username or client_secret is required for authentication
                if not server_config["username"] and not server_config["client_secret"]:
                    logger.warning(f"Skipping server configuration '{section}': Missing Entra ID credentials")
                    continue
            else:
                logger.warning(f"Skipping server configuration '{section}': Unknown auth type '{auth_type}'")
                continue
            
            # Add server configuration
            self.servers[section] = ServerConfig(section, server_config)
            logger.info(f"Loaded server configuration: {section}")
            
        # Fall back to legacy configuration if no servers are defined
        if not self.servers:
            logger.info("No server configurations found, using legacy environment variables")
            from .server import get_db_config
            try:
                config = get_db_config()
                self.servers["default"] = ServerConfig("default", config)
                self.active_server = "default"
            except ValueError as e:
                logger.error(f"Failed to load legacy configuration: {str(e)}")
        
        # Ensure active server exists
        if self.active_server not in self.servers:
            if self.servers:
                self.active_server = next(iter(self.servers.keys()))
                logger.warning(f"Default server not found, using '{self.active_server}' instead")
            else:
                logger.error("No valid server configurations found")
                self.active_server = None
    
    def get_active_config(self) -> Optional[Dict]:
        """Get the active server configuration."""
        if not self.active_server or self.active_server not in self.servers:
            return None
        return self.servers[self.active_server].config
    
    def set_active_server(self, server_name: str) -> bool:
        """Set the active server by name.
        
        Args:
            server_name: Name of the server to activate
            
        Returns:
            bool: True if server was found and activated, False otherwise
        """
        if server_name in self.servers:
            self.active_server = server_name
            logger.info(f"Activated server: {server_name}")
            return True
        return False
    
    def get_server_list(self) -> List[ServerConfig]:
        """Get list of all server configurations.
        
        Returns:
            List of ServerConfig objects
        """
        return list(self.servers.values())
    
    def get_server_by_name(self, name: str) -> Optional[ServerConfig]:
        """Get server configuration by name.
        
        Args:
            name: Server name to retrieve
            
        Returns:
            ServerConfig if found, None otherwise
        """
        return self.servers.get(name)
        
    def get_server_by_uri(self, uri: str) -> Optional[ServerConfig]:
        """Get server configuration by URI.
        
        Args:
            uri: URI in format mssql://{server_name}/{optional_path}
            
        Returns:
            ServerConfig if found, None otherwise
        """
        if uri.startswith("mssql://"):
            parts = uri[8:].split('/')
            server_name = parts[0]
            return self.servers.get(server_name)
        return None

# Singleton instance of server manager
_server_manager = None

def get_server_manager() -> ServerManager:
    """Get the singleton server manager instance."""
    global _server_manager
    if _server_manager is None:
        _server_manager = ServerManager()
    return _server_manager
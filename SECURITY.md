## Microsoft SQL Server Security Configuration

### Authentication Options

This MCP server supports two authentication methods:

#### 1. SQL Server Authentication
Use a dedicated SQL login with minimal permissions as described below.

#### 2. Entra ID Authentication (formerly Azure AD)
Use Microsoft Entra ID for enhanced security with either service principal or user authentication.

### Entra ID Authentication Setup

#### Service Principal Authentication

For enhanced security with service principal authentication:

1. **Register an Application in Azure Portal**:
   - Navigate to Azure Portal > App registrations
   - Create a new registration
   - Name your application
   - Select the appropriate supported account type
   - No redirect URI is needed

2. **Create a Client Secret**:
   - In your registered app, go to "Certificates & secrets"
   - Create a new client secret
   - Set description and expiration
   - Save the secret value (shown only once)

3. **Grant SQL Server Access**:
   - In SQL Server, create a user from the external provider:
   ```sql
   CREATE USER [your-app-name] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [your-app-name];
   -- Add additional roles as needed
   ```

4. **Configure Environment Variables**:
   ```bash
   MSSQL_AUTH_TYPE=entra
   MSSQL_SERVER=your-server.database.windows.net
   MSSQL_DATABASE=your_database
   MSSQL_CLIENT_ID=your_app_client_id
   MSSQL_TENANT_ID=your_tenant_id
   MSSQL_CLIENT_SECRET=your_client_secret
   ```

#### User ID Authentication

For user-based authentication:

1. **Register an Application**:
   - Similar to above, register an app in Azure Portal
   - Under "Authentication" > "Advanced settings", enable "Allow public client flows"

2. **Configure API Permissions**:
   - Add "Microsoft Graph" > "User.Read" permission
   - Add "Azure SQL Database" > "user_impersonation" permission
   - Grant admin consent if required

3. **Configure SQL Server**:
   ```sql
   -- Add Entra ID user
   CREATE USER [user@yourdomain.com] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [user@yourdomain.com];
   -- Add additional roles as needed
   ```

4. **Configure Environment Variables**:
   ```bash
   MSSQL_AUTH_TYPE=entra
   MSSQL_SERVER=your-server.database.windows.net
   MSSQL_DATABASE=your_database
   MSSQL_CLIENT_ID=your_app_client_id
   MSSQL_TENANT_ID=your_tenant_id
   MSSQL_ENTRA_USERNAME=your_email@domain.com
   # MSSQL_ENTRA_PASSWORD is optional and not recommended for security reasons
   ```

#### Security Best Practices for Entra ID Authentication

1. **Credential Management**:
   - Regularly rotate client secrets
   - Use managed identities where possible
   - Store secrets in Azure Key Vault
   - Never commit secrets to source control

2. **Permission Scope**:
   - Assign minimal required permissions
   - Use conditional access policies
   - Enable multi-factor authentication
   - Regularly audit access

3. **Application Registration**:
   - Restrict the application to specific tenants
   - Limit redirect URIs
   - Configure approved client applications
   - Enable publisher verification

4. **Monitoring**:
   - Enable audit logging
   - Monitor for suspicious sign-in attempts
   - Set up alerts for unusual access patterns
   - Review access regularly

### Creating a Restricted SQL Server Login

It's crucial to create a dedicated SQL Server login with minimal permissions for the MCP server. Never use the 'sa' account or a login with full administrative privileges.

#### 1. Create a new SQL Server login

```sql
-- Connect as sysadmin or administrator
CREATE LOGIN mcp_login WITH PASSWORD = 'your_secure_password';

-- Create database user for the login
USE your_database;
CREATE USER mcp_user FOR LOGIN mcp_login;
```

#### 2. Grant minimal required permissions

Basic read-only access (recommended for exploration and analysis):
```sql
-- Grant SELECT permission only
USE your_database;
GRANT SELECT TO mcp_user;
```

Standard access (allows data modification but not structural changes):
```sql
-- Grant data manipulation permissions
USE your_database;
GRANT SELECT, INSERT, UPDATE, DELETE TO mcp_user;
```

Advanced access (includes ability to create temporary objects for complex queries):
```sql
-- Grant additional permissions for advanced operations
USE your_database;
GRANT SELECT, INSERT, UPDATE, DELETE TO mcp_user;
GRANT CREATE TABLE TO mcp_user;  -- For temp tables
```

### Additional Security Measures

1. **Network Access**
   - Configure SQL Server to only accept connections from specific IP addresses
   - Use Windows Firewall to restrict port access
   - Consider using Always Encrypted for sensitive data

2. **Query Restrictions**
   - Use database roles to manage permissions
   - Implement Row-Level Security (RLS) for fine-grained access control:
   ```sql
   -- Example of RLS implementation
   CREATE SCHEMA Security;
   GO
   
   CREATE FUNCTION Security.fn_securitypredicate(@user VARCHAR(50))
   RETURNS TABLE
   WITH SCHEMABINDING
   AS
   RETURN SELECT 1 AS fn_securitypredicate_result
   WHERE @user = USER_NAME();
   GO
   
   CREATE SECURITY POLICY Security.TablePolicy
   ADD FILTER PREDICATE Security.fn_securitypredicate(UserColumn)
   ON dbo.YourTable;
   ```

3. **Data Access Control**
   - Use views to restrict column access
   - Implement column-level encryption where needed
   - Use schema-level permissions when possible:
   ```sql
   GRANT SELECT ON SCHEMA::YourSchema TO mcp_user;
   ```

4. **Regular Auditing**
   - Enable SQL Server Audit
   - Use Extended Events for monitoring
   - Regularly review audit logs

### Environment Configuration

When setting up the MCP server, use these restricted credentials in your environment:

```bash
MSSQL_SERVER=your_server
MSSQL_USER=mcp_login
MSSQL_PASSWORD=your_secure_password
MSSQL_DATABASE=your_database
```

### Monitoring Usage

To monitor the MCP login's database usage:

```sql
-- Check current connections
SELECT * FROM sys.dm_exec_sessions
WHERE login_name = 'mcp_login';

-- View user permissions
SELECT * FROM sys.database_permissions
WHERE grantee_principal_id = USER_ID('mcp_user');

-- Monitor query execution
SELECT * FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle)
WHERE session_id IN (
    SELECT session_id FROM sys.dm_exec_sessions
    WHERE login_name = 'mcp_login'
);
```

### Best Practices

1. **Authentication Security**
   - Use Windows Authentication when possible
   - Implement password policies
   - Enable TLS 1.2 or higher for connections
   - Regularly rotate credentials

2. **Permission Management**
   - Follow the principle of least privilege
   - Regularly review and audit permissions
   - Use contained databases when appropriate
   - Implement proper separation of duties

3. **Monitoring and Auditing**
   - Set up SQL Server Audit for sensitive operations
   - Monitor failed login attempts
   - Track schema changes
   - Use Extended Events for detailed monitoring

4. **Data Protection**
   - Use Always Encrypted for sensitive columns
   - Implement Transparent Data Encryption (TDE)
   - Use backup encryption
   - Consider using Dynamic Data Masking:
   ```sql
   ALTER TABLE YourTable
   ALTER COLUMN SensitiveColumn ADD MASKED WITH (FUNCTION = 'default()');
   ```

5. **Network Security**
   - Use encryption for all connections
   - Configure proper firewall rules
   - Consider using Azure Private Link if using Azure SQL
   - Implement proper network segmentation

### Regular Security Reviews

1. **Weekly Tasks**
   - Review failed login attempts
   - Check for unauthorized schema changes
   - Monitor resource usage patterns

2. **Monthly Tasks**
   - Audit user permissions
   - Review security policies
   - Check for new security patches
   - Validate backup encryption

3. **Quarterly Tasks**
   - Comprehensive security assessment
   - Review and update security policies
   - Penetration testing if required
   - Update documentation

Remember to always follow your organization's security policies and compliance requirements in addition to these guidelines.

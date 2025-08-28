# SQL Server Stored Procedure Modernization Recommendations

## Overview

This document provides recommendations for modernizing the SQL Server stored procedures in the PTODS database based on current best practices and SQL Server 2025 capabilities. These recommendations aim to improve performance, maintainability, security, and scalability.

## Current State Analysis

After examining the stored procedures in the PTODS database, particularly `sp_GetNumberOfDaysRecordList` and `sp_InsertF4111`, we've identified several areas for improvement:

1. **Basic Structure**: Most procedures follow standard SQL Server patterns but lack modern optimization techniques
2. **Naming Conventions**: All procedures use the `sp_` prefix, which Microsoft recommends avoiding
3. **Error Handling**: Limited or no error handling in most procedures
4. **Parameter Usage**: Inconsistent parameter declaration and validation
5. **Documentation**: Minimal inline documentation
6. **Performance Features**: No utilization of newer SQL Server features for performance optimization

## Modernization Recommendations

### 1. Rename Stored Procedures

The `sp_` prefix should be avoided as it's reserved for system procedures and can cause performance issues due to lookup behavior.

**Current:**
```sql
CREATE PROCEDURE [dbo].[sp_GetNumberOfDaysRecordList]
```

**Recommended:**
```sql
CREATE PROCEDURE [dbo].[GetNumberOfDaysRecordList]
```

Or use a consistent prefix like `proc_` or `usp_` (for user stored procedure):

```sql
CREATE PROCEDURE [dbo].[usp_GetNumberOfDaysRecordList]
```

### 2. Implement Proper Error Handling

Add comprehensive error handling using TRY/CATCH blocks to improve reliability and debugging.

**Current:**
```sql
CREATE PROCEDURE [dbo].[sp_GetNumberOfDaysRecordList]
AS
BEGIN
	SET NOCOUNT ON;
	SELECT * FROM Map_NumberOfDays WHERE (DeletedFlag=0 or DeletedFlag is null) ORDER BY DaysLate_Key
END
```

**Recommended:**
```sql
CREATE PROCEDURE [dbo].[usp_GetNumberOfDaysRecordList]
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        SELECT * FROM Map_NumberOfDays WHERE (DeletedFlag=0 or DeletedFlag is null) ORDER BY DaysLate_Key
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE(),
                @ErrorSeverity INT = ERROR_SEVERITY(),
                @ErrorState INT = ERROR_STATE();
        
        -- Log error details
        INSERT INTO ErrorLog(ErrorProcedure, ErrorLine, ErrorMessage, ErrorDateTime)
        VALUES(ERROR_PROCEDURE(), ERROR_LINE(), @ErrorMessage, GETDATE());
        
        -- Re-throw the error with additional context
        RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END
```

### 3. Improve Parameter Handling

For procedures with parameters, add parameter validation and use modern techniques to avoid parameter sniffing issues.

**Current (from sp_UpdateNumberOfDays):**
```sql
CREATE PROCEDURE [dbo].[sp_UpdateNumberOfDays]
@recordFlag int=null,
@DaysLate_Key int=null,
-- other parameters
AS
BEGIN
    -- procedure body
END
```

**Recommended:**
```sql
CREATE PROCEDURE [dbo].[usp_UpdateNumberOfDays]
    @recordFlag INT = NULL,
    @DaysLate_Key INT = NULL,
    -- other parameters
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Parameter validation
    IF @recordFlag IS NULL OR @recordFlag NOT IN (1, 2, 3)
    BEGIN
        THROW 50000, 'Invalid @recordFlag value. Must be 1, 2, or 3.', 1;
        RETURN;
    END
    
    -- For performance-critical procedures with parameter sniffing issues,
    -- consider using OPTION(RECOMPILE) on complex queries
    -- procedure body
END
```

### 4. Implement Intelligent Query Processing

Enable and leverage modern SQL Server's Intelligent Query Processing features.

```sql
-- Enable at the database level
ALTER DATABASE PTODS SET COMPATIBILITY_LEVEL = 160; -- For SQL Server 2025
ALTER DATABASE SCOPED CONFIGURATION SET INTELLIGENT_QUERY_PROCESSING = ON;

-- For specific procedures with complex queries, add query hints
SELECT * 
FROM LargeTable 
WHERE ComplexCondition = @Param
OPTION(USE HINT('ENABLE_ADAPTIVE_MEMORY_GRANT_FEEDBACK'));
```

### 5. Optimize Bulk Operations

For procedures like `sp_InsertF4111` that handle large data movements, implement more efficient bulk operations.

**Current:**
```sql
INSERT INTO [JDE].[F4111_Current]
([ILITM], [ILLITM], /* many columns */)
SELECT [ILITM], [ILLITM], /* many columns */
FROM [JDE].[F4111_Temp] Live
WHERE not exists (select 1 FROM [PTODS].[JDE].[F4111_Current] ODS
                  where ods.ILUKID = Live.ILUKID)
```

**Recommended:**
```sql
-- Enable minimal logging for bulk operations
-- Use TABLOCK hint for better performance
INSERT INTO [JDE].[F4111_Current] WITH (TABLOCK)
([ILITM], [ILLITM], /* many columns */)
SELECT [ILITM], [ILLITM], /* many columns */
FROM [JDE].[F4111_Temp] Live
WHERE not exists (select 1 FROM [PTODS].[JDE].[F4111_Current] ODS WITH (NOLOCK)
                  where ods.ILUKID = Live.ILUKID)
OPTION (OPTIMIZE FOR UNKNOWN);

-- For very large operations, consider using MERGE statement
-- or table variables with proper indexing
```

### 6. Improve Documentation

Add comprehensive documentation to each procedure.

**Recommended:**
```sql
/*
========================================================================
Author:         Jane Doe
Create date:    July 11, 2025
Description:    Gets non-deleted records from Map_NumberOfDays table
                ordered by DaysLate_Key.
Parameters:     None
Return Value:   Resultset of Map_NumberOfDays records
Revisions:
Date        Author      Description
--------    -------     -------------------------------------
2025-07-11  Jane Doe    Initial implementation
========================================================================
*/
CREATE PROCEDURE [dbo].[usp_GetNumberOfDaysRecordList]
```

### 7. Implement Performance Monitoring

Add performance monitoring capabilities by integrating with Query Store and Extended Events.

```sql
-- Enable Query Store for the database
ALTER DATABASE PTODS SET QUERY_STORE = ON;
ALTER DATABASE PTODS SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30),
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    INTERVAL_LENGTH_MINUTES = 60,
    MAX_STORAGE_SIZE_MB = 1000,
    QUERY_CAPTURE_MODE = AUTO,
    SIZE_BASED_CLEANUP_MODE = AUTO
);

-- For critical procedures, add execution logging
CREATE PROCEDURE [dbo].[usp_GetNumberOfDaysRecordList]
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @StartTime DATETIME2 = SYSUTCDATETIME();
    DECLARE @ExecutionId UNIQUEIDENTIFIER = NEWID();
    
    BEGIN TRY
        -- Log execution start
        INSERT INTO ProcedureExecutionLog(ExecutionId, ProcedureName, StartTime)
        VALUES(@ExecutionId, 'usp_GetNumberOfDaysRecordList', @StartTime);
        
        -- Original procedure logic
        SELECT * FROM Map_NumberOfDays WHERE (DeletedFlag=0 or DeletedFlag is null) ORDER BY DaysLate_Key;
        
        -- Log execution end
        UPDATE ProcedureExecutionLog
        SET EndTime = SYSUTCDATETIME(),
            Duration = DATEDIFF(MILLISECOND, @StartTime, SYSUTCDATETIME()),
            RowCount = @@ROWCOUNT,
            Status = 'Success'
        WHERE ExecutionId = @ExecutionId;
    END TRY
    BEGIN CATCH
        -- Log execution error
        UPDATE ProcedureExecutionLog
        SET EndTime = SYSUTCDATETIME(),
            Duration = DATEDIFF(MILLISECOND, @StartTime, SYSUTCDATETIME()),
            Status = 'Error',
            ErrorMessage = ERROR_MESSAGE()
        WHERE ExecutionId = @ExecutionId;
        
        THROW;
    END CATCH
END
```

### 8. Implement Security Best Practices

Add proper security measures to protect sensitive data.

```sql
-- Use proper schema permissions
GRANT EXECUTE ON [dbo].[usp_GetNumberOfDaysRecordList] TO [ApplicationRole];

-- For procedures that access sensitive data, consider implementing row-level security
-- or data masking at the table level
ALTER TABLE SensitiveData
ALTER COLUMN PersonalIdentifier ADD MASKED WITH (FUNCTION = 'partial(2,"XXXXX",0)');
```

## Implementation Strategy

To modernize these stored procedures effectively:

1. **Assessment and Prioritization**:
   - Identify high-impact, frequently used procedures
   - Analyze performance metrics to find bottlenecks
   - Create a prioritized list based on business impact

2. **Development Process**:
   - Create a parallel development environment
   - Develop modernized versions with thorough testing
   - Document all changes and improvements

3. **Testing**:
   - Perform load testing to compare performance
   - Validate functional equivalence
   - Test error scenarios and edge cases

4. **Deployment**:
   - Schedule maintenance windows for updates
   - Implement rollback plans
   - Monitor post-deployment performance

5. **Continuous Optimization**:
   - Set up regular performance reviews
   - Monitor Query Store data
   - Refine based on actual usage patterns

## References

1. [Microsoft SQL Server Documentation](https://docs.microsoft.com/en-us/sql/relational-databases/)
2. [SQL Server Stored Procedure Best Practices](https://www.datacamp.com/tutorial/sql-stored-procedure)
3. [Optimizing SQL Server Performance Best Practices for 2025](https://cyberpanel.net/blog/optimizing-sql-server-performance-best-practices-for-2025)
4. [SQL Server Modernization Guide](https://www.vpn.com/solutions/database-modernization/)
5. [Intelligent Query Processing in SQL Server](https://docs.microsoft.com/en-us/sql/relational-databases/performance/intelligent-query-processing)
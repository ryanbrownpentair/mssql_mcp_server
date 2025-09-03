#!/usr/bin/env python3
"""Test multi-statement query functionality"""

import asyncio
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mssql_mcp_server.server import execute_multi_statement_query
from mssql_mcp_server.server_manager import ServerManager

async def test_multi_statement():
    """Test multi-statement query execution"""
    
    print("Testing multi-statement query functionality...")
    
    # Initialize server manager
    sm = ServerManager()
    
    # Set active server
    if not sm.set_active_server('azure-edw-dev'):
        print("Failed to set active server to azure-edw-dev")
        return
    
    print("Active server set to azure-edw-dev")
    
    # Test multi-statement query
    test_query = """
    SELECT GETDATE() as CurrentTime, 'First Query' as QueryName;
    SELECT 'Hello' as Greeting, 'World' as Target, 42 as Number;
    SELECT COUNT(*) as DatabaseCount FROM sys.databases WHERE name NOT IN ('master', 'model', 'msdb', 'tempdb');
    """
    
    print("\nExecuting multi-statement query:")
    print(test_query)
    print("-" * 50)
    
    try:
        results = await execute_multi_statement_query(test_query.strip(), 100)
        print(f"\nSuccess! Executed {len(results)} statements:")
        
        for i, result in enumerate(results):
            print(f"\n=== Statement {i + 1} ===")
            print(f"Statement index: {result.get('statement_index', 'N/A')}")
            
            if 'data' in result and result['data']:
                print(f"Type: SELECT query")
                print(f"Columns: {result.get('columns', [])}")
                print(f"Data rows: {len(result['data'])}")
                for row in result['data']:
                    print(f"  {row}")
            else:
                print(f"Type: Non-SELECT query")
                print(f"Affected rows: {result.get('affected_rows', 0)}")
        
        print(f"\nTest completed successfully!")
        
    except Exception as e:
        print(f"\nError during execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_multi_statement())

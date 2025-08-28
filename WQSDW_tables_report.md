# WQSDW Database Tables Report

## Overview

This report provides a detailed analysis of the inventory-related tables in the WQSDW database. The analysis was performed on July 11, 2025, using direct SQL Server connection to USCHITDB63-WQSDW.

## Tables Analyzed

### 1. InventoryDaily

**Purpose**: Stores daily inventory snapshots for reporting and analysis.

**Current Status**: Empty (0 records)

**Structure**:
- InventoryDailyID: Primary key
- DBName: Source database name
- InventoryDate: Date of inventory snapshot
- ItemNumber: Product/item identifier
- ItemNumberShort: Shortened version of item number
- Site: Manufacturing or warehouse site
- Location: Storage location within site
- SerialNumber: Serial number for serialized inventory
- QOH (Quantity on Hand): Current inventory level
- MaterialCost, SubcontractCost, PurchaseCost, LaborCost, VariableOverheadCost, FixedOverheadCost, FreightAdderCost: Cost components
- AcquisitionCost, UnitStdCost, TotalLocationCost: Aggregate cost fields
- HoldCodeLocation, LotStatusCode: Status indicators
- InventoryStatusDescription: Text description of inventory status
- GLClassCode: General Ledger classification
- StockingType: Inventory stocking classification
- DateLastUpdated: Last record update timestamp

**Issues Identified**:
- Table is completely empty, suggesting ETL process failure
- Missing daily snapshots impact reporting and analysis capabilities
- Historical trends cannot be established without this data

### 2. inventorylog

**Purpose**: Records transactional history of inventory movements and changes.

**Current Status**: Active with data (contains records from 2017 to present)

**Structure**:
- id: Primary key
- begLocationId, endLocationId: Source and destination location identifiers
- begTagNum, endTagNum: Inventory tag identifiers
- changeQty: Quantity change amount (positive for additions, negative for reductions)
- cost: Cost value associated with the transaction
- dateCreated: Record creation timestamp
- eventDate: Date and time when the inventory change occurred
- info: Text description of the inventory transaction (e.g., "Inventory quantities import")
- locationGroupId: Group identifier for related locations
- partId: Product identifier
- partTrackingId: Tracking identifier for serialized items
- qtyOnHand: Quantity on hand after transaction
- recordId, tableId: Reference identifiers
- typeId: Transaction type code
- userId: User who performed or authorized the transaction

**Sample Data Insights**:
- Earliest records from January 2017 labeled as "Inventory quantities import"
- Regular transaction patterns observed throughout the dataset
- Contains the foundation data needed to reconstruct InventoryDaily

### 3. VW_MTDInventorySummary

**Purpose**: A view (not a physical table) that aggregates month-to-date inventory metrics.

**Current Status**: Available for querying, dependent on underlying tables

**Expected Content**:
- Month-to-date summary of inventory levels
- Aggregated by product, location, or other dimensions
- Likely includes beginning balance, receipts, issues, and ending balance
- May include cost valuations and variance calculations

**Relationship to Other Tables**:
- Likely depends on InventoryDaily for daily snapshots
- May also incorporate data from inventorylog for transactional details
- Used for monthly reporting and analysis

## Data Analysis Findings

### Data Flow and Relationships

The inventory data system appears to follow this flow:
1. Raw transactions are recorded in `inventorylog` (functioning correctly)
2. Daily snapshots should be generated in `InventoryDaily` (currently failing)
3. Month-to-date summaries are produced in `VW_MTDInventorySummary` (may be affected)

### Data Quality Issues

1. **Missing Daily Snapshots**:
   - The `InventoryDaily` table contains no records
   - This suggests a failure in the ETL process or data loading job

2. **Historical Data Integrity**:
   - The `inventorylog` table contains data going back to 2017
   - The log entries appear to be consistent and properly structured
   - Earliest entries are marked as imports, suggesting an initial data load

3. **Potential Reporting Impact**:
   - Reports dependent on `InventoryDaily` would be returning no results
   - The empty state of this table would affect any downstream processes
   - Month-to-date view may also be returning incomplete or incorrect results

### Data Reconstruction Potential

A positive finding is that `inventorylog` contains the necessary transactional data to reconstruct the `InventoryDaily` table. A reconstruction approach would involve:

1. Calculating cumulative quantities from transaction history
2. Joining with product and location reference data
3. Creating point-in-time snapshots for each required date
4. Validating the reconstructed data against known inventory levels

## Recommendations

Based on this analysis, we recommend:

1. **Immediate Action**:
   - Investigate and repair the ETL process for `InventoryDaily`
   - Reconstruct historical daily snapshots from `inventorylog`
   - Validate the `VW_MTDInventorySummary` view against reconstructed data

2. **Process Improvements**:
   - Implement daily data quality checks to detect similar issues early
   - Create automated alerts for empty or inconsistent tables
   - Document the ETL process and dependencies between these tables

3. **Enhanced Monitoring**:
   - Deploy AI-based anomaly detection for inventory data patterns
   - Establish baseline metrics for expected data volumes and update frequencies
   - Implement reconciliation routines between transactional and snapshot data

## Conclusion

The WQSDW database's inventory data system is currently compromised due to the empty `InventoryDaily` table. However, the transaction history in `inventorylog` provides a solid foundation for data recovery. By addressing the ETL process issues and implementing the recommended monitoring improvements, data integrity can be restored and maintained going forward.
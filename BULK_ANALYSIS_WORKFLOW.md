# Bulk Capacity Analysis Workflow

This document describes the new `BulkCapacityAnalysisWorkflow`, which provides a different design approach compared to the existing `CapacityManagementWorkflow`.

## Overview

The `BulkCapacityAnalysisWorkflow` is a read-only workflow that analyzes capacity across all namespaces efficiently using a single API call to the Metrics API.

## Key Differences from CapacityManagementWorkflow

| Feature | CapacityManagementWorkflow | BulkCapacityAnalysisWorkflow |
|---------|---------------------------|------------------------------|
| **API Calls** | N+1 calls (1 for list + N for each namespace) | 1 call (fetches all namespace metrics at once) |
| **Actions** | Takes provisioning actions (enable/disable) | Read-only, no provisioning actions |
| **Metrics** | Fetches throttling metrics | Fetches action_limit and action_count |
| **Output** | WorkflowResult with actions taken | List of NamespaceRecommendation |
| **Purpose** | Automated capacity management | Capacity planning and analysis |

## Workflow Design

### 1. Single API Call with Metric Filtering
The workflow makes **one API call** to the Metrics API using the `metrics` query parameter to filter at the API level, retrieving only:
- `temporal_cloud_v1_action_limit` - The action limit for each namespace
- `temporal_cloud_v1_total_action_count` - The current action count for each namespace

This approach reduces response size and improves efficiency by filtering at the API rather than client-side.

### 2. Calculate Recommendations
For each namespace returned from the API:
- Extract action_limit and action_count metrics
- Calculate recommended number of TRUs (currently stubbed)
- Build a `NamespaceRecommendation` object

### 3. Return Results
Returns a list of `NamespaceRecommendation` objects containing:
- `namespace` - The namespace name
- `action_limit` - The action limit
- `action_count` - The current action count
- `recommended_trus` - Recommended number of TRUs (stubbed to return 5)

## Data Models

### NamespaceRecommendation
```python
@dataclass
class NamespaceRecommendation:
    namespace: str
    action_limit: float
    action_count: float
    recommended_trus: int
```

## Running the Workflow

### Using the Script
```bash
python scripts/run_bulk_analysis.py
```

### Programmatically
```python
from temporalio.client import Client
from src.workflows import BulkCapacityAnalysisWorkflow

client = await Client.connect(...)
result = await client.execute_workflow(
    BulkCapacityAnalysisWorkflow.run,
    id="bulk-capacity-analysis",
    task_queue="capacity-management",
)

for recommendation in result:
    print(f"{recommendation.namespace}: {recommendation.recommended_trus} TRUs")
```

## Worker Configuration

The worker must be configured to handle both workflows. Update `scripts/worker.py`:

```python
from src.workflows import CapacityManagementWorkflow, BulkCapacityAnalysisWorkflow

worker = Worker(
    client,
    task_queue=settings.temporal_task_queue,
    workflows=[CapacityManagementWorkflow, BulkCapacityAnalysisWorkflow],
    activities=[...],
)
```

## Implementation Details

### Activity: get_all_namespace_metrics()
Located in `src/activities/namespace_ops.py`, this activity:
1. Creates an OpenMetrics client
2. Calls `client.get_all_namespace_metrics()` (single API call)
3. Filters namespaces based on allow/deny lists
4. Calculates recommended TRUs for each namespace
5. Returns list of NamespaceRecommendation objects

### OpenMetrics Client Enhancement
Added `get_all_namespace_metrics()` method to `src/openmetrics_client.py`:
- Makes API call without namespace filter
- Parses metrics for all namespaces in response
- Returns dictionary mapping namespace to metrics

### TRU Recommendation Logic (Stubbed)
The `_calculate_recommended_trus()` function in `namespace_ops.py` is currently stubbed to return 5.

**TODO**: Implement actual TRU recommendation logic that considers:
- Current usage vs limit ratio
- Historical trends
- Growth projections
- Cost optimization targets

## Use Cases

1. **Capacity Planning**: Get a snapshot of all namespace capacities for planning purposes
2. **Cost Analysis**: Identify namespaces that might need TRU adjustments
3. **Monitoring**: Regular analysis without taking automated actions
4. **Reporting**: Generate capacity reports across all namespaces

## Future Enhancements

- Implement intelligent TRU recommendation algorithm
- Add historical data analysis
- Include cost estimates in recommendations
- Support for custom recommendation strategies
- Export results to different formats (CSV, JSON, etc.)

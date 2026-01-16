# Bulk Capacity Analysis Workflow

This document describes the `BulkCapacityAnalysisWorkflow`, which analyzes capacity across all namespaces efficiently using a single API call to the Metrics API.

## Overview

The `BulkCapacityAnalysisWorkflow` is a read-only workflow that analyzes capacity across all namespaces efficiently using a single API call to the Metrics API.

## Workflow Design

### 1. Single API Call with Metric Filtering
The workflow makes **one API call** to the Metrics API using the `metrics` query parameter to filter at the API level, retrieving only:
- `temporal_cloud_v1_action_limit` - The action limit for each namespace
- `temporal_cloud_v1_total_action_count` - The current action count for each namespace

This approach reduces response size and improves efficiency by filtering at the API rather than client-side.

### 2. Calculate Recommendations
For each namespace returned from the API:
- Extract action_limit and action_count metrics
- Hit the CloudOps API to gather information about the current state of the namespace - this is one once for EACH namespace. As such, the activity heartbeats after every 5 namespaces that it processes.
- Calculate recommended capacity mode, and, if Provisioned is recommended, recommended number of TRUs
- Build a `NamespaceRecommendation` object

### 3. Return Results
Returns a list of `NamespaceRecommendation` objects containing:
- `namespace` - The namespace name
- `action_limit` - The action limit
- `action_count` - The current action count
- `recommended_trus` - Recommended number of TRUs
- `current_capacity_mode` - The capacity mode currently applied to the namespace
- `current_trus` - Current TRU count if in Provisioned Mode
- `recommended_capacity_mode` - "provisioned" or "on-demand"

## Running the Workflow

### Using the Script
```bash
uv run python scripts/run_bulk_analysis.py
```

## Use Cases

1. **Capacity Planning**: Get a snapshot of all namespace capacities for planning purposes
2. **Cost Analysis**: Identify namespaces that might need TRU adjustments
3. **Monitoring**: Regular analysis without taking automated actions
4. **Reporting**: Generate capacity reports across all namespaces

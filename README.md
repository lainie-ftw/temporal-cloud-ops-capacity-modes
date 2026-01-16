# Temporal Cloud Capacity Modes - Sample Workflows

Sample Python workflows demonstrating how to use the [Metrics API](https://docs.temporal.io/production-deployment/cloud/metrics/openmetrics/api-reference) and [Cloud Ops API](https://saas-api.tmprl.cloud/docs/httpapi.html) to manage Temporal Cloud namespace capacity modes.

## Overview

This project provides two sample workflows showcasing different approaches to capacity management:

1. **Bulk Capacity Analysis Workflow** - Analyzes all namespaces and provides recommendations on whether they should switch to Provisioned Mode and how many TRUs (Temporal Resource Units) they should have
2. **Scheduled Capacity Change Workflow** - Schedules capacity mode changes (on-demand ↔ provisioned) with optional automatic revert, useful when combined with Temporal Schedules

These are meant to serve as reference implementations that you can adapt for your own Temporal Cloud capacity management needs.

## The Two Workflows

### 1. Bulk Capacity Analysis Workflow

**Purpose**: Analyze capacity across all namespaces and provide recommendations

This read-only workflow:
- Makes a **single API call** to the Metrics API to retrieve action limit and action count for all namespaces
- Calculates recommended TRUs for each namespace based on current usage
- Retrieves current capacity mode information via the Cloud Ops API
- Returns a list of `NamespaceRecommendation` objects with metrics and recommendations
- **Does not take any action** - just provides analysis and recommendations

**Use Cases**:
- Capacity planning and cost analysis
- Identifying namespaces that should switch capacity modes
- Regular monitoring without automated changes
- Generating capacity reports

**Key Features**:
- Efficient single API call to get all namespace metrics
- Comprehensive logging of recommendations
- Detailed recommendations including current usage vs. limit ratios

### 2. Scheduled Capacity Change Workflow

**Purpose**: Schedule capacity mode changes with automatic verification and optional revert

This workflow:
- **Immediately** enables provisioning with a specified number of TRUs for a namespace
- Waits 2 minutes and **verifies** the change was successful via Cloud Ops API
- Sends **Slack alerts** if provisioning or verification fails (whether it actually sends to Slack or not depends on if SLACK_WEBHOOK_URL has a value in the .env file)
- If an **end time** is provided, sleeps until that time and reverts to on-demand mode
- Verifies the revert was successful

**Use Cases**:
- Planned capacity increases for known high-traffic events
- Batch processing windows that need temporary capacity boosts
- Development/testing scenarios requiring temporary provisioning
- Permanent capacity changes (by not specifying an end time)

**Key Features**:
- Automatic verification of capacity changes
- Optional automatic revert to on-demand mode
- Slack notifications on critical failures
- Works seamlessly with Temporal Schedules for scheduling

## Architecture

### Bulk Capacity Analysis Workflow

```
┌─────────────────────────────────┐
│  Bulk Capacity Analysis         │
│  Workflow                       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ Activity: Get All Namespace     │
│ Metrics (single API call) and   |
| run logic to make recommendation|
| with heartbeating every 5      |
| namespaces.                     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ Return List of Recommendations  │
│ (no actions taken)              │
└─────────────────────────────────┘
```

### Scheduled Capacity Change Workflow

```
┌──────────────────────────────────────┐
│ Scheduled Capacity Change Workflow   │
│ (triggered by Schedule or manually)  │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Activity: Enable Provisioning        │
│ (Set TRUs via Cloud Ops API)         │
└──────────────┬───────────────────────┘
               │
               ▼
       ┌───────────────┐
       │  Wait 2 min   │
       └───────┬───────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Activity: Verify Capacity            │
│ (Check provisioned mode + TRU count) │
└──────────────┬───────────────────────┘
               │
               ├─ If end_time provided ──┐
               │                         │
               ▼                         ▼
       ┌──────────────┐        ┌──────────────────────┐
       │  No revert   │        │  Sleep until         │
       │  Return      │        │  end_time            │
       └──────────────┘        └──────────┬───────────┘
                                          │
                                          ▼
                               ┌──────────────────────┐
                               │ Activity: Disable    │
                               │ Provisioning         │
                               │ (Revert to on-demand)│
                               └──────────┬───────────┘
                                          │
                                          ▼
                                  ┌───────────────┐
                                  │  Wait 2 min   │
                                  └───────┬───────┘
                                          │
                                          ▼
                               ┌──────────────────────┐
                               │ Activity: Verify     │
                               │ Revert to on-demand  │
                               └──────────┬───────────┘
                                          │
                                          ▼
                               ┌──────────────────────┐
                               │  Return Result       │
                               └──────────────────────┘
```

## Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Temporal Cloud account with:
  - **Namespace API key** (for running these workflows in your namespace) - This should be for the namespace where this code will run
  - **Cloud Ops API key** (for capacity mode changes) - Should be tied to a service account with Global Admin account-level access. [See documentation](https://docs.temporal.io/ops)
  - **Metrics Read Only API key** (for analyzing capacity) - Should be tied to a service account with Metrics Read Only access. [See documentation](https://docs.temporal.io/production-deployment/cloud/metrics/openmetrics/api-reference)

## Installation

1. **Clone the repository:**

```bash
git clone https://github.com/lainie-ftw/temporal-cloud-ops-capacity-modes.git
cd temporal-cloud-ops-capacity-modes
```

2. **Install dependencies:**

Using uv (recommended):
```bash
uv sync
```

3. **Configure environment variables:**

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Temporal Cloud credentials and API keys.

## Usage

### Starting the Worker

Both workflows require a worker to process tasks. Start it first:

```bash
uv run python scripts/worker.py
```

The worker will connect to Temporal Cloud and wait for workflow tasks.

### Workflow 1: Bulk Capacity Analysis

Analyze all namespaces and get capacity recommendations:

```bash
uv run python scripts/run_bulk_analysis.py
```

This will:
1. Analyze all namespaces in your Temporal Cloud account
2. Get current metrics and recommended TRU counts
3. Print recommendations to the console
4. Return results that you can use for capacity planning

Example output:
```
Analyzed 2 namespaces:
- production-namespace: Current Mode: on-demand, Recommended Mode: Provisioned (8 TRUs), APS limit: 500, Current APS: 3600
- staging-namespace: Current Mode: on-demand, Recommended Mode: on-demand, APS limit: 500, Current APS: 100
...
```

### Workflow 2: Scheduled Capacity Change

#### Option A: Manual/One-off Execution

Set a namespace to provisioned mode with a specific TRU count:

```bash
# Set to 5 TRUs, no automatic revert
uv run python scripts/run_scheduled_capacity_change.py my-namespace.abc123 5

# Set to 5 TRUs, automatically revert to on-demand in 4 hours (sent into script as a total of minutes)
uv run python scripts/run_scheduled_capacity_change.py my-namespace.abc123 5 240
```

#### Option B: Using Temporal Schedules (Recommended)

Create a schedule to automatically trigger capacity changes at specific times:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from temporalio.client import Client
from temporalio.service import Schedule
from src.workflows.scheduled_capacity_change import ScheduledCapacityChangeWorkflow
from src.models.types import ScheduledCapacityChangeInput

client = await Client.connect(...)

# Calculate 5 PM Eastern today in UTC - this has to be in UTC because workflow.now() in Python returns the time in UTC.
eastern = ZoneInfo("America/New_York")
end_time_eastern = datetime.now(tz=eastern).replace(hour=17, minute=0, second=0, microsecond=0)
end_time_utc = end_time_eastern.astimezone(timezone.utc)

# Schedule capacity boost starting at 9 AM, ending at 5 PM Eastern
await client.create_schedule(
    "my-namespace-business-hours-boost",
    Schedule(
        action=ScheduleActionStartWorkflow(
            ScheduledCapacityChangeWorkflow.run,
            ScheduledCapacityChangeInput(
                namespace="my-namespace.abc123",
                desired_trus=10,
                end_time=end_time_utc,
            ),
            id=f"scheduled-capacity-change-{datetime.now().isoformat()}",
            task_queue="capacity-management",
        ),
        spec=ScheduleSpec(
            calendars=[
                ScheduleCalendarSpec(
                    hour=[9],      # Start at 9 AM
                    minute=[0],
                    day_of_week=[1, 2, 3, 4, 5],  # Weekdays only
                )
            ]
        ),
    ),
)
```

## Monitoring Execution

Monitor workflow executions in the Temporal Cloud UI:

1. Go to [cloud.temporal.io](https://cloud.temporal.io)
2. Select your namespace
3. Go to the Workflows tab
4. Search for:
   - `bulk-capacity-analysis` for analysis workflow executions
   - `scheduled-capacity-change-*` for scheduled capacity changes

## Testing Safely

### Dry Run Mode

Test without making actual capacity changes:

```bash
# In .env file
DRY_RUN_MODE=true
```

In dry run mode:
- Workflows make all API calls and decisions
- Actual capacity changes are NOT applied
- Slack notifications are NOT sent
- Perfect for testing your configuration

### Namespace Filters

Test on specific namespaces:

```bash
# Only analyze/change these namespaces
NAMESPACE_ALLOWLIST=test-namespace-1,test-namespace-2

# Or exclude certain namespaces
NAMESPACE_DENYLIST=prod-important,prod-critical
```

### Query Workflows

For Scheduled Capacity Change, query the workflow status:

```bash
temporal workflow query \
  --workflow-id scheduled-capacity-change-my-namespace \
  --type get_status
```

## Project Structure

```
temporal-cloud-ops-capacity-modes/
├── src/
│   ├── activities/              # Activity implementations
│   │   ├── namespace_ops.py     # Get namespace metrics and capacity
│   │   ├── provisioning_ops.py  # Enable/disable provisioning
│   │   └── notification_ops.py  # Slack notifications
│   ├── workflows/               # Workflow definitions
│   │   ├── bulk_capacity_analysis.py
│   │   └── scheduled_capacity_change.py
│   ├── models/
│   │   └── types.py             # Data models (NamespaceRecommendation, etc)
│   ├── config.py                # Configuration management
│   ├── openmetrics_client.py    # Metrics API client
│   └── cloud_ops_client.py      # Cloud Ops API client
├── scripts/
│   ├── worker.py                # Worker process
│   ├── run_bulk_analysis.py     # Run bulk analysis workflow
│   └── run_scheduled_capacity_change.py  # Run scheduled capacity change
├── tests/                       # Test suite
├── .env.example                 # Example configuration
└── README.md                    # This file
```

## Customization

### Bulk Capacity Analysis

The recommendation logic is in `src/activities/namespace_ops.py`. You can modify `_calculate_recommended_trus()` to:
- Adjust the TRU calculation formula
- Use different thresholds
- Include historical data or trends
- Apply custom business rules

### Scheduled Capacity Change

- Change the 2-minute verification wait (line 88 and others)
- Adjust retry policies
- Add additional verification checks
- Customize Slack notification messages

## Troubleshooting

### Worker Won't Start

```
Failed to connect to Temporal
```

**Solution**: Check your environment variables and Temporal Cloud credentials:
```bash
# Verify your config
cat .env | grep TEMPORAL
```

### API Calls Failing (401 Unauthorized)

```
Failed to get namespace metrics: 401 Unauthorized
```

**Solution**: Verify your API keys are valid and have correct permissions:
- Metrics API key should have "Metrics Read Only" access
- Cloud Ops API key should have "Global Admin" account-level access

### Workflows Not Executing

```
No workflows are executing, worker idle
```

**Solution**: 
1. Verify worker is running: `ps aux | grep worker.py`
2. Check task queue name matches in configuration
3. Verify workflow is registered in worker

### Capacity Changes Not Taking Effect

**Solution**:
1. Check workflow completion status in Temporal UI
2. Review logs for activity errors
3. Verify Cloud Ops API key has sufficient permissions
4. Check if namespace is in the correct account

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest

# Run specific test
pytest tests/test_bulk_capacity_analysis.py
```

### Understanding the API Clients

- **OpenMetrics Client** (`src/openmetrics_client.py`) - Handles Metrics API calls for capacity analysis
- **Cloud Ops Client** (`src/cloud_ops_client.py`) - Handles Cloud Ops API calls for capacity mode changes

Both clients handle:
- Authentication
- Request formatting
- Response parsing
- Error handling

## References

- [Temporal Cloud Capacity Modes Documentation](https://docs.temporal.io/cloud/capacity-modes)
- [Cloud Ops API Documentation](https://saas-api.tmprl.cloud/docs/httpapi.html)
- [Metrics API Documentation](https://docs.temporal.io/production-deployment/cloud/metrics/openmetrics/api-reference)
- [Temporal Python SDK Documentation](https://docs.temporal.io/dev-guide/python)
- [Temporal Schedules Documentation](https://docs.temporal.io/workflows#schedule)

## Additional Documentation

- [BULK_ANALYSIS_WORKFLOW.md](BULK_ANALYSIS_WORKFLOW.md) - Detailed information about the analysis workflow
- [SCHEDULED_CAPACITY_CHANGE.md](SCHEDULED_CAPACITY_CHANGE.md) - Detailed information about the scheduled capacity change workflow

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or pull request.

## Support

For issues or questions:
- Open a GitHub issue
- Check the troubleshooting section above
- Visit [community.temporal.io](https://community.temporal.io)

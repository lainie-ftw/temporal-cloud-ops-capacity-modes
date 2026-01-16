# Scheduled Capacity Change Workflow

This workflow allows you to schedule capacity mode changes for a specific namespace at specific times. It's useful for planned capacity increases during known high-traffic periods, with automatic reversion to on-demand mode afterward.

## Features

- **Immediate provisioning**: Sets a namespace to a specified number of TRUs immediately when the workflow starts
- **Automatic verification**: Waits 2 minutes and verifies the capacity was set correctly
- **Alert on failure**: Sends Slack alerts if provisioning or verification fails
- **Optional auto-revert**: If an end time is provided, automatically reverts to on-demand mode at that time
- **End-to-end verification**: Verifies the revert operation completed successfully

## Workflow Behavior

### Step 1: Enable Provisioning
- Calls the Cloud Ops API to set the namespace to the specified TRU count
- Uses retry policy (3 attempts) to handle transient failures
- Sends critical alert to Slack if this step fails

### Step 2: Wait and Verify
- Waits 2 minutes for the change to propagate
- Calls the Cloud Ops API to verify:
  - Provisioning state is ENABLED
  - TRU count matches the desired value
- Sends error alert to Slack if verification fails

### Step 3: Optional Revert (if end_time provided)
- Sleeps until the specified end time
- Calls the Cloud Ops API to disable provisioning (revert to on-demand)
- Waits 2 minutes and verifies the revert
- Sends alerts if revert or verification fails

## Usage

### Using Temporal Schedules

The recommended way to use this workflow is with Temporal Schedules:

```python
from datetime import datetime, timedelta
from temporalio.client import Client
from src.models.types import ScheduledCapacityChangeInput

# Connect to Temporal
client = await Client.connect(...)

# Define when to start (e.g., 9 AM tomorrow)
start_time = datetime(2026, 1, 16, 9, 0, 0)

# Define when to end (e.g., 5 PM tomorrow)
end_time = datetime(2026, 1, 16, 17, 0, 0)

# Create schedule
await client.create_schedule(
    "my-namespace-capacity-boost",
    Schedule(
        action=ScheduleActionStartWorkflow(
            ScheduledCapacityChangeWorkflow.run,
            ScheduledCapacityChangeInput(
                namespace="my-namespace.abc123",
                desired_trus=10,
                end_time=end_time,
            ),
            id=f"scheduled-capacity-change-my-namespace-{start_time}",
            task_queue="capacity-management",
        ),
        spec=ScheduleSpec(
            calendars=[
                ScheduleCalendarSpec(
                    hour=[start_time.hour],
                    minute=[start_time.minute],
                    day_of_month=[start_time.day],
                    month=[start_time.month],
                    year=[start_time.year],
                )
            ]
        ),
    ),
)
```

### Manual Execution

For testing or one-off changes, use the provided script:

```bash
# Set namespace to 5 TRUs, no automatic revert
python scripts/run_scheduled_capacity_change.py my-namespace.abc123 5

# Set namespace to 5 TRUs, revert to on-demand in 10 minutes
python scripts/run_scheduled_capacity_change.py my-namespace.abc123 5 10
```

### Direct Workflow Execution

```python
from temporalio.client import Client
from src.workflows.scheduled_capacity_change import ScheduledCapacityChangeWorkflow
from src.models.types import ScheduledCapacityChangeInput
from datetime import datetime, timedelta

client = await Client.connect(...)

# Set namespace to 10 TRUs, revert in 4 hours
result = await client.execute_workflow(
    ScheduledCapacityChangeWorkflow.run,
    ScheduledCapacityChangeInput(
        namespace="my-namespace.abc123",
        desired_trus=10,
        end_time=datetime.now() + timedelta(hours=4),
    ),
    id="scheduled-capacity-change-my-namespace",
    task_queue="capacity-management",
)

print(f"Result: {result}")
```

## Input Parameters

### `ScheduledCapacityChangeInput`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `namespace` | `str` | Yes | The namespace to modify |
| `desired_trus` | `int` | Yes | Number of TRUs to provision |
| `end_time` | `datetime` | No | When to revert to on-demand (optional) |

## Output

### `ScheduledCapacityChangeResult`

| Field | Type | Description |
|-------|------|-------------|
| `namespace` | `str` | The namespace that was modified |
| `initial_change_success` | `bool` | Whether provisioning was enabled successfully |
| `verification_success` | `bool` | Whether the initial change was verified |
| `reverted_to_on_demand` | `bool` | Whether revert was attempted (only if end_time provided) |
| `revert_verification_success` | `bool` | Whether the revert was verified |
| `errors` | `list[str]` | List of errors encountered during execution |

## Slack Notifications

The workflow sends notifications at key points:

- **Critical (🔴)**: Initial provisioning failed or revert failed
- **Error (⚠️)**: Verification failed (but operation may have succeeded)
- **Info (✅)**: Successful revert completion

Configure Slack notifications by setting the `SLACK_WEBHOOK_URL` environment variable.

## Use Cases

### 1. Planned Traffic Spike
Schedule a capacity increase before a known high-traffic event:
- Start: 1 hour before event
- TRUs: Based on expected load
- End: 1 hour after event

### 2. Batch Processing Window
Provision capacity for nightly batch jobs:
- Start: 11 PM
- TRUs: Sufficient for batch workload
- End: 2 AM

### 3. Development Testing
Test provisioned capacity for a short period:
- Start: Immediately
- TRUs: 2-5 (as needed)
- End: 30 minutes later

### 4. Permanent Capacity Increase
Set provisioned capacity without automatic revert:
- Start: Immediately or scheduled
- TRUs: Desired permanent capacity
- End: Not specified (no revert)

## Monitoring

You can monitor workflow execution in the Temporal Web UI:

1. Navigate to your Temporal Cloud namespace
2. Go to the Workflows tab
3. Search for workflow ID starting with `scheduled-capacity-change-`
4. View execution history, logs, and current state

## Error Handling

The workflow includes comprehensive error handling:

- **Retry Policy**: Activities retry up to 3 times with exponential backoff
- **Graceful Degradation**: If verification fails, the workflow continues and alerts
- **Early Exit**: If initial provisioning fails, workflow exits early
- **Detailed Logging**: All steps are logged for troubleshooting

## Best Practices

1. **Test First**: Use the script to test with a short duration before scheduling production changes
2. **Monitor Alerts**: Ensure Slack webhook is configured so you receive failure notifications
3. **Verify Results**: Check the Temporal Web UI to confirm workflow completion
4. **Plan Ahead**: Schedule capacity changes well before the expected traffic increase
5. **Use Appropriate TRUs**: Calculate required TRUs based on expected actions per second
6. **Consider Overlap**: Add buffer time before/after events for safety

## Limitations

- Minimum sleep duration: 2 minutes (for verification)
- Maximum workflow execution time: Limited by Temporal's workflow timeout
- Revert verification: Currently marks as successful without detailed API check (can be enhanced)

## Future Enhancements

Potential improvements to consider:

- Add activity to verify on-demand state (instead of just logging success)
- Support gradual capacity changes (ramp up/down)
- Add query methods to check workflow status in real-time
- Support multiple namespace changes in a single workflow
- Add signals to modify end_time while workflow is running

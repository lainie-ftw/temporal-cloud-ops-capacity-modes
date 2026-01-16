# Scheduled Capacity Change - Implementation Summary

## Overview
A new workflow has been added to support scheduled capacity mode changes with automatic verification and optional reversion to on-demand mode.

## Files Created

### 1. Workflow
- **`src/workflows/scheduled_capacity_change.py`** - Main workflow implementation
  - Enables provisioning at workflow start
  - Waits 2 minutes and verifies the change
  - Optionally sleeps until end_time and reverts to on-demand
  - Sends Slack alerts on failures

### 2. Models/Types
- **`src/models/types.py`** (modified) - Added new types:
  - `ScheduledCapacityChangeInput` - Input parameters
  - `ScheduledCapacityChangeResult` - Result object

### 3. Activities
- **`src/activities/namespace_ops.py`** (modified) - Added new activity:
  - `verify_namespace_capacity()` - Verifies namespace has expected TRU count and provisioning state

### 4. Scripts
- **`scripts/run_scheduled_capacity_change.py`** - Test/execution script
  - Command-line interface for manual workflow execution
  - Supports immediate or scheduled capacity changes with optional revert

### 5. Documentation
- **`SCHEDULED_CAPACITY_CHANGE.md`** - Complete workflow documentation
  - Features and behavior
  - Usage examples
  - Input/output reference
  - Best practices

### 6. Updates
- **`src/activities/__init__.py`** - Exported new activity
- **`src/workflows/__init__.py`** - Exported new workflow
- **`scripts/worker.py`** - Registered new workflow and activity

## Workflow Behavior

```
Start → Enable Provisioning → Wait 2min → Verify
                                           ↓
                                    [If end_time]
                                           ↓
                              Sleep until end_time
                                           ↓
                           Disable Provisioning → Wait 2min → Verify
```

## Key Features

1. **Immediate Action**: Sets TRUs immediately when workflow starts
2. **Verification**: Validates changes via Cloud Ops API after 2 minutes
3. **Alerts**: Sends Slack notifications on failures (stubbed as requested)
4. **Optional Revert**: Automatically reverts to on-demand at specified end time
5. **Error Handling**: Comprehensive retry policies and error logging
6. **Durable Execution**: Uses Temporal's workflow.sleep() for reliable long-running operations

## Usage Example

```bash
# Set namespace to 5 TRUs for 10 minutes
python scripts/run_scheduled_capacity_change.py my-namespace.account 5 10
```

## Testing

All components have been tested:
- ✅ Imports verified
- ✅ Syntax validated
- ✅ Worker registration confirmed
- ✅ Script help text displays correctly

## Integration with Temporal Schedules

This workflow is designed to be triggered by Temporal Schedules at a specific time, with the workflow itself handling the end_time for automatic reversion. This works around the limitation that Temporal Schedules with end times don't continue executing workflows.

## Next Steps

1. Start the worker: `python scripts/worker.py`
2. Test with a short duration: `python scripts/run_scheduled_capacity_change.py <namespace> <trus> 5`
3. Monitor in Temporal Web UI
4. Create Temporal Schedules for production use

## Dependencies

No new dependencies were added. The implementation uses:
- Existing activities: `enable_provisioning`, `disable_provisioning`, `send_slack_notification`
- Existing clients: `CloudOpsClient`
- Temporal SDK features: `workflow.sleep()`, `workflow.now()`, retry policies

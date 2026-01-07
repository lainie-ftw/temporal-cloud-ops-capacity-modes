# Temporal Cloud Provisioned Capacity Automation

A Python-based Temporal workflow that automatically manages provisioned capacity for Temporal Cloud namespaces to help optimize costs and avoid paying for unused capacity.

## Overview

This project provides an automated solution for managing Temporal Cloud's provisioned capacity (Temporal Resource Units - TRUs) across multiple namespaces. The workflow:

1. **Monitors usage**: Checks all namespaces for their action rates and throttling status
2. **Disables unused capacity**: Automatically disables provisioned capacity when usage falls below a threshold
3. **Enables capacity when needed**: Automatically enables provisioned capacity when namespaces are being throttled
4. **Notifies on failures**: Sends Slack notifications when issues occur

### How It Works

The workflow runs on a schedule (default: 45 minutes past every hour) and performs two main checks:

- **Turn Off Check**: For namespaces with provisioned capacity enabled, if actions per hour fall below the minimum threshold, provisioning is disabled to save costs
- **Turn On Check**: For namespaces without provisioned capacity, if throttling is detected, provisioning is enabled with a specified number of TRUs

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Temporal Schedule                         │
│              (Triggers at :45 every hour)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Capacity Management Workflow                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. List all namespaces                                │ │
│  │  2. Check enabled namespaces → Disable if underused   │ │
│  │  3. Check disabled namespaces → Enable if throttled   │ │
│  │  4. Send notifications on failures                     │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Activities (Idempotent)                    │
│  • list_namespaces() - Get all namespaces                   │
│  • check_throttling() - Check metrics & throttling          │
│  • disable_provisioning() - Disable APS via Cloud Ops API   │
│  • enable_provisioning() - Enable APS via Cloud Ops API     │
│  • send_slack_notification() - Send alerts                  │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager 
- Temporal Cloud account with:
  - Namespace API key (recommended) OR mTLS certificates for authentication - this should be for the namespace where THIS workflow will run
  - Cloud Ops API key for getting info about the namespaces in the account and potentially changing capacity modes. This should be tied to a service account with Global Admin account-level access. [documentation](https://docs.temporal.io/ops)
  - Metrics Read Only API key for getting APS utilization information about namespaces. This should be tied to a service account with Metrics Read Only access. [documentation](https://docs.temporal.io/production-deployment/cloud/metrics/openmetrics/api-reference)
- (Optional) Slack webhook for notifications

## Installation

1. **Clone the repository:**

```bash
git clone https://github.com/your-org/temporal-cloud-ops-capacity-modes.git
cd temporal-cloud-ops-capacity-modes
```

2. **Install dependencies:**

Using uv (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -e .
```

3. **Configure environment variables:**

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

**Option 1: API Key Authentication (Recommended - Simpler)**
```bash
# Required settings
TEMPORAL_ADDRESS=your-namespace.account.tmprl.cloud:7233
TEMPORAL_NAMESPACE=your-namespace
TEMPORAL_API_KEY=your-namespace-api-key
TEMPORAL_CLOUD_OPS_API_KEY=your-cloud-ops-api-key

# Optional settings
DEFAULT_TRU_COUNT=5
MIN_ACTIONS_THRESHOLD=100
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
DRY_RUN_MODE=false
```

**Option 2: mTLS Certificate Authentication (Alternative)**
```bash
# Required settings
TEMPORAL_ADDRESS=your-namespace.account.tmprl.cloud:7233
TEMPORAL_NAMESPACE=your-namespace
TEMPORAL_CERT_PATH=/path/to/client.pem
TEMPORAL_KEY_PATH=/path/to/client-key.pem
TEMPORAL_CLOUD_OPS_API_KEY=your-cloud-ops-api-key

# Optional settings
DEFAULT_TRU_COUNT=5
MIN_ACTIONS_THRESHOLD=100
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
DRY_RUN_MODE=false
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TEMPORAL_ADDRESS` | Yes | - | Temporal Cloud address (e.g., namespace.account.tmprl.cloud:7233) |
| `TEMPORAL_NAMESPACE` | Yes | - | Namespace where this workflow runs |
| `TEMPORAL_CERT_PATH` | Yes | - | Path to mTLS certificate file |
| `TEMPORAL_KEY_PATH` | Yes | - | Path to mTLS private key file |
| `TEMPORAL_CLOUD_OPS_API_KEY` | Yes | - | Cloud Ops API key |
| `CLOUD_OPS_API_BASE_URL` | No | https://saas-api.tmprl.cloud | Cloud Ops API base URL |
| `DEFAULT_TRU_COUNT` | No | 5 | TRUs to enable when turning on capacity |
| `MIN_ACTIONS_THRESHOLD` | No | 100 | Min actions/hour to keep capacity enabled |
| `SLACK_WEBHOOK_URL` | No | - | Slack webhook for notifications |
| `DRY_RUN_MODE` | No | false | Preview mode without making changes |
| `NAMESPACE_ALLOWLIST` | No | - | Comma-separated list of namespaces to manage |
| `NAMESPACE_DENYLIST` | No | - | Comma-separated list of namespaces to exclude |
| `TASK_QUEUE` | No | capacity-management-task-queue | Task queue name |

### Getting Cloud Ops API Credentials

1. Go to [cloud.temporal.io](https://cloud.temporal.io)
2. Navigate to Settings → API Keys
3. Create a new API key with appropriate permissions
4. Save the key securely (you won't be able to see it again)

### Getting mTLS Certificates

Follow the [Temporal Cloud documentation](https://docs.temporal.io/cloud/certificates) to generate or download your mTLS certificates.

## Usage

### 1. Start the Worker

The worker processes workflow and activity tasks. It must be running for the automation to work:

```bash
python scripts/worker.py
```

The worker will connect to Temporal Cloud and wait for tasks. Keep it running in a terminal or deploy it as a service.

### 2. Create the Schedule

Create the Temporal Schedule that triggers the workflow every hour:

```bash
python scripts/create_schedule.py
```

This creates a schedule that runs at 45 minutes past every hour (e.g., 1:45, 2:45, 3:45, etc.).

### 3. Monitor Execution

You can monitor workflow executions in the Temporal Cloud UI:

1. Go to [cloud.temporal.io](https://cloud.temporal.io)
2. Select your namespace
3. Look for workflows with ID `capacity-management-workflow`

## Testing Safely

### Dry Run Mode

Before running in production, test with dry run mode enabled:

```bash
# In .env file
DRY_RUN_MODE=true
```

In dry run mode, the workflow will:
- Check all namespaces and make decisions
- Log what actions it would take
- **NOT** actually enable or disable provisioning
- **NOT** send real Slack notifications

### Using Namespace Filters

Test on specific namespaces first:

```bash
# Only manage these namespaces
NAMESPACE_ALLOWLIST=test-namespace-1,test-namespace-2

# Or exclude production namespaces
NAMESPACE_DENYLIST=prod-namespace-1,prod-namespace-2
```

### Query the Workflow

Use queries to inspect workflow state without affecting execution:

```bash
# Query current decisions
temporal workflow query \
  --workflow-id capacity-management-workflow \
  --type preview_actions

# Query workflow status
temporal workflow query \
  --workflow-id capacity-management-workflow \
  --type get_status
```

## Customization

### Adjusting Decision Logic

To customize when capacity is enabled/disabled, modify the thresholds:

```bash
# More conservative (keep capacity enabled longer)
MIN_ACTIONS_THRESHOLD=500  # Higher threshold

# More aggressive (disable capacity sooner)
MIN_ACTIONS_THRESHOLD=50   # Lower threshold
```

### Customizing TRU Count

Adjust the number of TRUs enabled:

```bash
# Start with more capacity
DEFAULT_TRU_COUNT=10

# Start with less capacity
DEFAULT_TRU_COUNT=3
```

### Modifying the Schedule

To change when the workflow runs, edit `scripts/create_schedule.py`:

```python
# Run every 30 minutes
calendars=[
    ScheduleCalendarSpec(
        minute="0,30",
        hour="*",
    )
]

# Run only during business hours
calendars=[
    ScheduleCalendarSpec(
        minute="45",
        hour="9-17",  # 9 AM to 5 PM
    )
]
```

## Cost Savings Example

### Scenario

- You have 10 namespaces
- Each has 5 TRUs enabled ($X per TRU per hour)
- Namespaces are only actively used 8 hours per day

### Without Automation

- Cost: 10 namespaces × 5 TRUs × 24 hours × $X = 1,200 TRU-hours per day

### With Automation

- Active usage: 10 namespaces × 5 TRUs × 8 hours × $X = 400 TRU-hours per day
- **Savings: 800 TRU-hours per day (67% reduction)**

### Annual Savings

Assuming $0.50 per TRU-hour:
- Daily savings: 800 × $0.50 = $400
- Monthly savings: ~$12,000
- Annual savings: ~$146,000

*Note: Actual costs depend on your Temporal Cloud pricing plan.*

## Features

### Idempotent Operations

All activities check current state before making changes, making them safe to retry:

```python
# Before disabling, checks if already disabled
# Before enabling, checks if already enabled at correct TRU level
```

### Comprehensive Logging

Every decision includes detailed rationale:

```
[namespace-1] Disable: Actions per hour (45) below threshold (100)
[namespace-2] No action: Actions per hour (250) above threshold
[namespace-3] Enable with 5 TRUs: Namespace is throttled (12.5%)
```

### Error Handling

- Automatic retries with exponential backoff
- Slack notifications on failures
- Workflow continues even if individual namespaces fail
- All errors logged with context

### Queries and Signals

- **Query**: `preview_actions()` - See what the workflow would do
- **Query**: `get_status()` - Get current workflow status
- **Signal**: `trigger_evaluation()` - Manually trigger evaluation

## Security Considerations

### API Key Management

- Store API keys securely (use environment variables or secrets manager)
- Rotate API keys regularly
- Use least-privilege access (only required permissions)
- Never commit `.env` files to version control

### mTLS Certificates

- Protect certificate private keys (restrict file permissions)
- Rotate certificates before expiration
- Store certificates securely (encrypted storage)

### Network Security

- Run workers in secure environments
- Use VPCs or private networks when possible
- Enable audit logging for all API calls

### Monitoring and Alerts

- Monitor workflow execution status
- Set up alerts for repeated failures
- Review logs regularly for anomalies
- Track provisioning changes over time

## Troubleshooting

### Worker Won't Start

```
Failed to connect to Temporal
```

**Solution**: Check your Temporal Cloud address, namespace, and certificates:
```bash
# Test connection
temporal workflow list --namespace your-namespace
```

### Activities Failing

```
Failed to list namespaces: 401 Unauthorized
```

**Solution**: Verify your Cloud Ops API key is valid and has correct permissions.

### Schedule Not Triggering

```
No workflows are being executed
```

**Solution**: 
1. Check schedule exists: `temporal schedule list`
2. Verify worker is running and listening on correct task queue
3. Check schedule is not paused

### Dry Run Mode Not Working

**Solution**: Ensure `DRY_RUN_MODE=true` is set in `.env` and restart the worker.

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest
```

### Project Structure

```
temporal-cloud-ops-capacity-modes/
├── src/
│   ├── activities/          # Activity implementations
│   ├── workflows/           # Workflow definitions
│   ├── models/              # Data models
│   ├── config.py            # Configuration management
│   └── cloud_ops_client.py  # Cloud Ops API client
├── scripts/
│   ├── worker.py            # Worker script
│   └── create_schedule.py   # Schedule creation script
├── tests/                   # Tests
├── .env.example             # Example configuration
└── README.md                # This file
```

## References

- [Temporal Cloud Capacity Modes](https://docs.temporal.io/cloud/capacity-modes)
- [Cloud Ops API Documentation](https://saas-api.tmprl.cloud/docs/httpapi.html)
- [Temporal Python SDK](https://docs.temporal.io/dev-guide/python)
- [Temporal Schedules](https://docs.temporal.io/workflows#schedule)

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or pull request.

## Support

For issues or questions:
- Open a GitHub issue
- Contact your Temporal account team
- Visit [community.temporal.io](https://community.temporal.io)

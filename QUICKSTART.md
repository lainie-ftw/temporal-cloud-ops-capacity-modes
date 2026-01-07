# Quick Start Guide

Get up and running with Temporal Cloud Capacity Management in 5 minutes!

## Prerequisites Checklist

- [ ] Python 3.12+ installed
- [ ] Temporal Cloud account
- [ ] Temporal namespace API key (recommended) OR mTLS certificates
- [ ] Cloud Ops API key created
- [ ] (Optional) Slack webhook URL

## Step-by-Step Setup

### 1. Install Dependencies

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 2. Configure Environment

```bash
# Copy the example configuration
cp .env.example .env
```

**Option 1: API Key Auth (Recommended - Simpler):**
```bash
TEMPORAL_ADDRESS=your-namespace.account.tmprl.cloud:7233
TEMPORAL_NAMESPACE=your-namespace
TEMPORAL_API_KEY=your-namespace-api-key
TEMPORAL_CLOUD_OPS_API_KEY=your-cloud-ops-api-key
```

**Option 2: mTLS Certificate Auth (Alternative):**
```bash
TEMPORAL_ADDRESS=your-namespace.account.tmprl.cloud:7233
TEMPORAL_NAMESPACE=your-namespace
TEMPORAL_CERT_PATH=/path/to/your/client.pem
TEMPORAL_KEY_PATH=/path/to/your/client-key.pem
TEMPORAL_CLOUD_OPS_API_KEY=your-cloud-ops-api-key
```

### 3. Test in Dry Run Mode

Enable dry run mode to test without making changes:

```bash
# In .env file, set:
DRY_RUN_MODE=true
```

### 4. Start the Worker

Open a terminal and run:

```bash
uv run python scripts/worker.py
```

Keep this running! You should see:
```
Connected to Temporal at your-namespace.account.tmprl.cloud:7233
Worker started, waiting for tasks...
```

### 5. Test Manually (Optional)

In a **new terminal**, run a one-time execution:

```bash
uv run python scripts/run_workflow_once.py
```

This will execute the workflow once and show you the results.

### 6. Create the Schedule

Once you're happy with the dry run results:

```bash
# Disable dry run mode
# In .env, set: DRY_RUN_MODE=false

# Create the schedule
uv run python scripts/create_schedule.py
```

## Verification

### Check the Schedule

```bash
temporal schedule list
```

You should see `capacity-management-schedule` in the list.

### Monitor Workflows

1. Go to [cloud.temporal.io](https://cloud.temporal.io)
2. Select your namespace
3. Look for workflows with ID starting with `capacity-management-workflow`

### Query Workflow Status

```bash
temporal workflow query \
  --workflow-id capacity-management-workflow \
  --type get_status
```

## Common First-Time Issues

### Issue: Worker fails to connect

```
Failed to connect to Temporal
```

**Solution:** Check your `TEMPORAL_ADDRESS` and certificate paths.

### Issue: Activities fail with 401

```
Failed to list namespaces: 401 Unauthorized
```

**Solution:** Verify your `TEMPORAL_CLOUD_OPS_API_KEY` is correct.

### Issue: Certificate not found

```
File not found: /path/to/client.pem
```

**Solution:** Update `TEMPORAL_CERT_PATH` and `TEMPORAL_KEY_PATH` with correct paths.

## Next Steps

Once everything is working:

1. **Adjust thresholds** - Fine-tune `MIN_ACTIONS_THRESHOLD` and `DEFAULT_TRU_COUNT`
2. **Set up Slack** - Add `SLACK_WEBHOOK_URL` for failure notifications
3. **Add filters** - Use `NAMESPACE_ALLOWLIST` or `NAMESPACE_DENYLIST` as needed
4. **Deploy worker** - Run the worker as a service/container in production

## Production Deployment Tips

### Run as a Service (systemd)

Create `/etc/systemd/system/temporal-capacity-worker.service`:

```ini
[Unit]
Description=Temporal Capacity Management Worker
After=network.target

[Service]
Type=simple
User=temporal
WorkingDirectory=/opt/temporal-capacity-management
Environment="PATH=/opt/temporal-capacity-management/.venv/bin"
ExecStart=/opt/temporal-capacity-management/.venv/bin/python scripts/worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable temporal-capacity-worker
sudo systemctl start temporal-capacity-worker
```

### Run in Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN pip install uv && uv sync

CMD ["python", "scripts/worker.py"]
```

### Run in Kubernetes

Use a Deployment with the worker container and mount secrets for certificates and API keys.

## Getting Help

- Check the [README.md](README.md) for detailed documentation
- Review logs: The worker outputs detailed logs about all decisions
- Use dry run mode to debug issues
- Query the workflow to see current decisions

## Security Reminders

- [ ] Never commit `.env` files
- [ ] Protect certificate private keys (chmod 600)
- [ ] Rotate API keys regularly
- [ ] Use secrets management in production
- [ ] Enable audit logging

---

**Ready to save costs?** Start the worker and let automation handle your capacity management! 🚀

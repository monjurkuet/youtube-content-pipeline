# Prometheus & Grafana Setup Guide for WSL2

This guide provides comprehensive instructions for setting up Prometheus and Grafana monitoring for the YouTube Transcription Pipeline API on Windows Subsystem for Linux (WSL2).

## Table of Contents

- [Introduction](#introduction)
- [Prerequisites](#prerequisites)
- [Option A: Docker Installation (Recommended)](#option-a-docker-installation-recommended)
- [Option B: Native WSL Installation](#option-b-native-wsl-installation)
- [Prometheus Configuration](#prometheus-configuration)
- [Grafana Setup](#grafana-setup)
- [Example Queries](#example-queries)
- [Alerting Rules](#alerting-rules)
- [Troubleshooting](#troubleshooting)

---

## Introduction

### What is Prometheus?

Prometheus is an open-source systems monitoring and alerting toolkit. It collects metrics from configured targets at given intervals, evaluates rule expressions, displays results, and can trigger alerts when specified conditions are met.

### Why Monitor the Transcription Pipeline?

Monitoring provides visibility into:

- **API Performance**: Request rates, latency, and error rates
- **Transcription Jobs**: Job duration, success/failure rates, queue depth
- **Resource Utilization**: Database and Redis operation metrics
- **System Health**: Component availability and uptime

### Metrics Exposed by the API

The API exposes the following Prometheus metrics at `/metrics`:

| Metric Name | Type | Description |
|-------------|------|-------------|
| `api_requests_total` | Counter | Total API requests by method, endpoint, status |
| `api_request_duration_seconds` | Histogram | API request latency |
| `transcription_jobs_total` | Counter | Total transcription jobs submitted |
| `transcription_jobs_in_progress` | Gauge | Currently processing jobs |
| `transcription_duration_seconds` | Histogram | Transcription job duration |
| `transcription_errors_total` | Counter | Transcription failures by error type |
| `mongodb_operations_total` | Counter | MongoDB operations by type and collection |
| `mongodb_operation_duration_seconds` | Histogram | MongoDB operation latency |
| `redis_operations_total` | Counter | Redis operations by type |
| `redis_operation_duration_seconds` | Histogram | Redis operation latency |
| `app_info` | Gauge | Application version and environment |

---

## Prerequisites

### Required Software

1. **WSL2** installed on Windows 10/11
   - Check version: `wsl --version`
   - Update: `wsl --update`

2. **Basic Linux command line knowledge**
   - Navigating directories
   - Editing files
   - Running services

### Option A: Docker Desktop (Recommended)

- Docker Desktop for Windows with WSL2 integration enabled
- Docker Compose (included with Docker Desktop)

### Option B: Native Installation

- wget or curl for downloading binaries
- Basic systemd knowledge (optional, for service management)

---

## Option A: Docker Installation (Recommended)

This is the easiest and most maintainable approach.

### Step 1: Install Docker Desktop

1. Download Docker Desktop from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)

2. Install and enable WSL2 integration:
   - Open Docker Desktop Settings
   - Go to **Resources > WSL Integration**
   - Enable integration with your WSL2 distribution

3. Verify installation:
   ```bash
   docker --version
   docker-compose --version
   ```

### Step 2: Create Project Directory

```bash
# Create monitoring directory
mkdir -p ~/monitoring
cd ~/monitoring
```

### Step 3: Create Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.47.0
    container_name: prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"
    networks:
      - monitoring

  grafana:
    image: grafana/grafana:10.1.0
    container_name: grafana
    restart: unless-stopped
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    ports:
      - "3000:3000"
    networks:
      - monitoring
    depends_on:
      - prometheus

networks:
  monitoring:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
```

### Step 4: Create Prometheus Configuration

Create directory and config file:

```bash
mkdir -p grafana/provisioning
mkdir -p prometheus
```

Create `prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'transcription-pipeline'

# Alertmanager configuration (optional)
# alerting:
#   alertmanagers:
#     - static_configs:
#         - targets:
#           - alertmanager:9093

# Rule files (optional)
rule_files:
  - "alerts.yml"

# Scrape configurations
scrape_configs:
  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Transcription Pipeline API
  - job_name: 'transcription-pipeline'
    static_configs:
      # For WSL2: Use host.docker.internal to reach Windows host
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
    
    # Relabel to add meaningful labels
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        regex: '(.+):(.+)'
        replacement: 'transcription-api'

  # Alternative: Direct WSL2 network access
  # - job_name: 'transcription-pipeline-wsl'
  #   static_configs:
  #     - targets: ['172.28.16.1:8000']  # WSL2 host IP
  #   metrics_path: '/metrics'
```

### Step 5: Create Alert Rules (Optional)

Create `prometheus/alerts.yml`:

```yaml
groups:
  - name: transcription_pipeline_alerts
    interval: 30s
    rules:
      # High error rate alert
      - alert: HighErrorRate
        expr: |
          sum(rate(api_requests_total{status=~"5.."}[5m])) 
          / sum(rate(api_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High API error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} over the last 5 minutes"

      # Slow transcription jobs
      - alert: SlowTranscriptionJobs
        expr: |
          histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m])) > 300
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Transcription jobs are slow"
          description: "95th percentile duration is {{ $value }} seconds"

      # Too many failed jobs
      - alert: HighJobFailureRate
        expr: |
          sum(rate(transcription_errors_total[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High transcription failure rate"
          description: "{{ $value }} failures per second"

      # API down
      - alert: APIDown
        expr: up{job="transcription-pipeline"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Transcription API is down"
          description: "API has been unreachable for more than 1 minute"
```

### Step 6: Start Services

```bash
# Start Prometheus and Grafana
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

### Step 7: Access Web Interfaces

- **Prometheus**: [http://localhost:9090](http://localhost:9090)
- **Grafana**: [http://localhost:3000](http://localhost:3000)
  - Username: `admin`
  - Password: `admin`

### Step 8: Configure Grafana Data Source

1. Log into Grafana
2. Go to **Configuration > Data Sources**
3. Click **Add data source**
4. Select **Prometheus**
5. Configure:
   - **URL**: `http://prometheus:9090`
   - **Access**: Server (default)
6. Click **Save & Test**

---

## Option B: Native WSL Installation

Use this option if you prefer not to use Docker.

### Step 1: Download Prometheus

```bash
# Create installation directory
sudo mkdir -p /opt/prometheus
sudo mkdir -p /var/lib/prometheus

# Download latest stable version
cd /tmp
wget https://github.com/prometheus/prometheus/releases/download/v2.47.0/prometheus-2.47.0.linux-amd64.tar.gz

# Extract
tar xvfz prometheus-2.47.0.linux-amd64.tar.gz

# Move binaries
sudo cp prometheus-2.47.0.linux-amd64/prometheus /opt/prometheus/
sudo cp prometheus-2.47.0.linux-amd64/promtool /opt/prometheus/

# Copy configuration
sudo cp -r prometheus-2.47.0.linux-amd64/consoles /opt/prometheus/
sudo cp -r prometheus-2.47.0.linux-amd64/console_libraries /opt/prometheus/

# Set permissions
sudo chown -R $USER:$USER /opt/prometheus
sudo chown -R $USER:$USER /var/lib/prometheus
```

### Step 2: Configure Prometheus

Create `/opt/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'transcription-pipeline'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Step 3: Run Prometheus

```bash
# Test configuration
/opt/prometheus/promtool check config /opt/prometheus/prometheus.yml

# Start Prometheus
/opt/prometheus/prometheus \
  --config.file=/opt/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.console.libraries=/opt/prometheus/consoles \
  --web.console.templates=/opt/prometheus/console_libraries \
  --web.enable-lifecycle
```

Access at: [http://localhost:9090](http://localhost:9090)

### Step 4: Download and Install Grafana

```bash
# Add Grafana repository
sudo apt-get install -y apt-transport-https
sudo apt-get install -y software-properties-common wget

wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -

echo "deb https://packages.grafana.com/oss/deb stable main" | \
  sudo tee -a /etc/apt/sources.list.d/grafana.list

# Install Grafana
sudo apt-get update
sudo apt-get install -y grafana

# Start Grafana
sudo systemctl start grafana-server
sudo systemctl enable grafana-server

# Check status
sudo systemctl status grafana-server
```

Access at: [http://localhost:3000](http://localhost:3000)

---

## Prometheus Configuration Reference

### Complete Configuration Example

```yaml
global:
  scrape_interval: 15s        # How often to scrape targets
  evaluation_interval: 15s    # How often to evaluate rules
  scrape_timeout: 10s         # Timeout for scraping
  external_labels:
    environment: production
    monitor: transcription-pipeline

# Alertmanager (optional)
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

# Rule files
rule_files:
  - "alerts.yml"
  - "recording_rules.yml"

# Scrape configurations
scrape_configs:
  - job_name: 'transcription-pipeline'
    
    # Static targets
    static_configs:
      - targets: ['host.docker.internal:8000']
        labels:
          service: api
          team: backend
    
    # Metrics endpoint
    metrics_path: '/metrics'
    
    # Scrape settings
    scrape_interval: 15s
    scrape_timeout: 10s
    
    # Scheme (http or https)
    scheme: http
    
    # TLS config (if using HTTPS)
    # tls_config:
    #   ca_file: /path/to/ca.crt
    #   cert_file: /path/to/client.crt
    #   key_file: /path/to/client.key
    #   insecure_skip_verify: false
    
    # Basic auth (if required)
    # basic_auth:
    #   username: prometheus
    #   password: secret
    
    # Bearer token (if required)
    # bearer_token: your_token_here
    
    # Relabel configurations
    relabel_configs:
      # Add instance label
      - source_labels: [__address__]
        target_label: instance
        regex: '(.+):(.+)'
        replacement: 'transcription-api'
      
      # Drop metrics we don't need
      - source_labels: [__name__]
        regex: 'go_.*'
        action: drop
    
    # Metric relabel configurations (after scraping)
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'api_requests_total'
        target_label: metric_type
        replacement: 'http_request'
```

---

## Grafana Setup

### Add Prometheus Data Source

1. Log into Grafana (http://localhost:3000)
2. Navigate to **Configuration > Data Sources**
3. Click **Add data source**
4. Select **Prometheus**
5. Configure:
   - **Name**: Prometheus
   - **URL**: `http://prometheus:9090` (Docker) or `http://localhost:9090` (Native)
   - **Access**: Server
   - **Auth**: Disabled (unless you configured auth)
6. Click **Save & Test**

### Import Dashboard

Grafana has pre-built dashboards. To import:

1. Go to **Dashboards > Import**
2. Enter dashboard ID or upload JSON file
3. Select Prometheus data source
4. Click **Import**

### Key Metrics to Visualize

Create panels for these metrics:

#### Request Rate
```promql
rate(api_requests_total[5m])
```

#### Error Rate
```promql
sum(rate(api_requests_total{status=~"5.."}[5m])) 
/ 
sum(rate(api_requests_total[5m]))
```

#### Job Duration (95th percentile)
```promql
histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m]))
```

#### Active Jobs
```promql
transcription_jobs_in_progress
```

#### MongoDB Operations
```promql
rate(mongodb_operations_total[5m])
```

#### Redis Operations
```promql
rate(redis_operations_total[5m])
```

### Dashboard JSON Export

Save your dashboard as JSON for version control:

1. Open dashboard
2. Click dashboard settings (gear icon)
3. Select **JSON Model**
4. Copy JSON content
5. Save to `grafana/dashboards/transcription-pipeline.json`

---

## Example Queries

### API Performance

| Query | Description |
|-------|-------------|
| `rate(api_requests_total[5m])` | Requests per second over 5 minutes |
| `histogram_quantile(0.50, rate(api_request_duration_seconds_bucket[5m]))` | Median request latency |
| `histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m]))` | 95th percentile latency |
| `histogram_quantile(0.99, rate(api_request_duration_seconds_bucket[5m]))` | 99th percentile latency |

### Error Analysis

| Query | Description |
|-------|-------------|
| `sum(rate(api_requests_total{status=~"5.."}[5m]))` | Server errors per second |
| `sum(rate(api_requests_total{status=~"4.."}[5m]))` | Client errors per second |
| `api_requests_total{status="500"}` | Total 500 errors |
| `sum by(endpoint) (rate(api_requests_total{status=~"5.."}[5m]))` | Errors by endpoint |

### Transcription Jobs

| Query | Description |
|-------|-------------|
| `transcription_jobs_in_progress` | Currently processing jobs |
| `rate(transcription_jobs_total[5m])` | Jobs submitted per second |
| `histogram_quantile(0.50, rate(transcription_duration_seconds_bucket[5m]))` | Median job duration |
| `histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m]))` | 95th percentile duration |
| `rate(transcription_errors_total[5m])` | Job failures per second |

### Database Operations

| Query | Description |
|-------|-------------|
| `rate(mongodb_operations_total[5m])` | MongoDB operations per second |
| `rate(mongodb_operations_total{operation="insert"}[5m])` | Insert operations per second |
| `histogram_quantile(0.95, rate(mongodb_operation_duration_seconds_bucket[5m]))` | 95th percentile DB latency |

### Redis Operations

| Query | Description |
|-------|-------------|
| `rate(redis_operations_total[5m])` | Redis operations per second |
| `rate(redis_operations_total{operation="get"}[5m])` | GET operations per second |
| `rate(redis_operations_total{operation="set"}[5m])` | SET operations per second |

---

## Alerting Rules

### Complete Alert Configuration

Create `prometheus/alerts.yml`:

```yaml
groups:
  - name: transcription_pipeline
    interval: 30s
    rules:
      # Critical: API is down
      - alert: APIDown
        expr: up{job="transcription-pipeline"} == 0
        for: 1m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "Transcription API is down"
          description: "The API has been unreachable for more than 1 minute"
          runbook_url: "https://wiki.example.com/runbooks/api-down"

      # Critical: High error rate
      - alert: HighErrorRate
        expr: |
          sum(rate(api_requests_total{status=~"5.."}[5m])) 
          / 
          sum(rate(api_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High API error rate"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"

      # Warning: Slow transcription jobs
      - alert: SlowTranscriptionJobs
        expr: |
          histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m])) > 300
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Transcription jobs are slow"
          description: "95th percentile duration is {{ $value }}s (threshold: 300s)"

      # Warning: High job failure rate
      - alert: HighJobFailureRate
        expr: |
          sum(rate(transcription_errors_total[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High transcription failure rate"
          description: "{{ $value }} failures per second"

      # Warning: MongoDB slow operations
      - alert: MongoDBSlowOperations
        expr: |
          histogram_quantile(0.95, rate(mongodb_operation_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "MongoDB operations are slow"
          description: "95th percentile latency is {{ $value }}s"

      # Warning: Redis connection issues
      - alert: RedisConnectionIssues
        expr: |
          rate(redis_operations_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis connection issues detected"
          description: "{{ $value }} Redis errors per second"

      # Info: High traffic
      - alert: HighTraffic
        expr: |
          sum(rate(api_requests_total[5m])) > 100
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "High API traffic"
          description: "{{ $value }} requests per second"
```

### Configure Alertmanager (Optional)

Create `docker-compose.yml` addition:

```yaml
  alertmanager:
    image: prom/alertmanager:v0.26.0
    container_name: alertmanager
    restart: unless-stopped
    volumes:
      - ./alertmanager:/etc/alertmanager
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    ports:
      - "9093:9093"
    networks:
      - monitoring
```

Create `alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alertmanager@example.com'
  smtp_auth_username: 'alertmanager@example.com'
  smtp_auth_password: 'password'

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'email-notifications'
  routes:
    - match:
        severity: critical
      receiver: 'critical-email'
    - match:
        severity: warning
      receiver: 'warning-email'

receivers:
  - name: 'email-notifications'
    email_configs:
      - to: 'team@example.com'
        send_resolved: true

  - name: 'critical-email'
    email_configs:
      - to: 'oncall@example.com'
        send_resolved: true
        html: |
          <h2>Critical Alert</h2>
          <p>{{ range .Alerts }}
            <strong>Alert:</strong> {{ .Annotations.summary }}<br>
            <strong>Description:</strong> {{ .Annotations.description }}<br>
          {{ end }}
```

---

## Troubleshooting

### Cannot Access Metrics from Prometheus

**Symptom**: Target shows as DOWN in Prometheus UI

**Solutions**:

1. **Check API is running**:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **Verify Prometheus configuration**:
   ```bash
   docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
   ```

3. **Check firewall**:
   ```bash
   # On WSL2
   sudo ufw status
   
   # On Windows
   # Check Windows Defender Firewall
   ```

4. **Test connectivity from container**:
   ```bash
   docker-compose exec prometheus wget -qO- http://host.docker.internal:8000/metrics
   ```

### WSL2 Networking Issues

**Problem**: Cannot reach Windows host from Docker container

**Solutions**:

1. **Use correct hostname**:
   - In Docker Desktop: `host.docker.internal`
   - In native WSL: `localhost` or WSL host IP

2. **Find WSL2 host IP**:
   ```bash
   # From WSL2
   cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
   
   # Or
   ip route | grep default | awk '{print $3}'
   ```

3. **Update /etc/hosts in container**:
   ```yaml
   # In docker-compose.yml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```

### Docker Networking Issues

**Problem**: Containers cannot communicate

**Solutions**:

1. **Verify network**:
   ```bash
   docker network ls
   docker network inspect monitoring
   ```

2. **Test container connectivity**:
   ```bash
   docker-compose exec grafana wget -qO- http://prometheus:9090/-/healthy
   ```

3. **Restart network**:
   ```bash
   docker-compose down
   docker network prune
   docker-compose up -d
   ```

### Firewall Configuration

**Windows Firewall**:

1. Open Windows Defender Firewall
2. Click "Advanced settings"
3. Add inbound rules for:
   - Port 8000 (API)
   - Port 9090 (Prometheus)
   - Port 3000 (Grafana)

**WSL2 Firewall**:

```bash
# Check status
sudo ufw status

# Allow ports
sudo ufw allow 8000/tcp
sudo ufw allow 9090/tcp
sudo ufw allow 3000/tcp

# Enable (optional)
sudo ufw enable
```

### Prometheus Not Scraping

**Check target status**:

1. Open Prometheus UI: http://localhost:9090
2. Go to **Status > Targets**
3. Check target state

**Common issues**:

| Issue | Solution |
|-------|----------|
| `server returned HTTP status 503` | API not running or overloaded |
| `connection refused` | Wrong host/port or firewall blocking |
| `context deadline exceeded` | Scrape timeout too short |
| `no metrics found` | Wrong metrics_path |

**Debug scraping**:

```bash
# Manual scrape test
curl -v http://localhost:8000/metrics

# Check Prometheus logs
docker-compose logs prometheus | grep scrape
```

### Grafana Cannot Connect to Prometheus

**Solutions**:

1. **Verify data source URL**:
   - Docker: `http://prometheus:9090`
   - Native: `http://localhost:9090`

2. **Check Prometheus is accessible**:
   ```bash
   docker-compose exec grafana wget -qO- http://prometheus:9090/-/healthy
   ```

3. **Check Grafana logs**:
   ```bash
   docker-compose logs grafana | grep -i prometheus
   ```

### Memory Issues

**Prometheus using too much memory**:

```yaml
# In prometheus.yml
global:
  scrape_interval: 30s  # Increase interval
  
# Add retention settings
command:
  - '--storage.tsdb.retention.time=15d'
  - '--storage.tsdb.retention.size=5GB'
```

**Grafana using too much memory**:

```yaml
# In docker-compose.yml
environment:
  - GF_CACHE_ENABLED=true
  - GF_CACHE_CAPACITY=1000
```

---

## Quick Reference

### Common Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f

# Restart Prometheus
docker-compose restart prometheus

# Reload Prometheus config (without restart)
curl -X POST http://localhost:9090/-/reload

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Query Prometheus API
curl -G http://localhost:9090/api/v1/query --data-urlencode "query=up"
```

### Important URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Prometheus | http://localhost:9090 | Metrics UI |
| Grafana | http://localhost:3000 | Dashboards |
| API Metrics | http://localhost:8000/metrics | Raw metrics |
| API Health | http://localhost:8000/health | Health check |
| API Docs | http://localhost:8000/docs | Swagger UI |

### File Locations

| File | Docker | Native |
|------|--------|--------|
| Prometheus config | `./prometheus/prometheus.yml` | `/opt/prometheus/prometheus.yml` |
| Alert rules | `./prometheus/alerts.yml` | `/opt/prometheus/alerts.yml` |
| Prometheus data | `prometheus_data` volume | `/var/lib/prometheus` |
| Grafana data | `grafana_data` volume | `/var/lib/grafana` |

---

## Next Steps

1. **Create custom dashboards** for your specific use cases
2. **Set up alerting** with email, Slack, or PagerDuty integration
3. **Configure recording rules** for complex queries
4. **Set up long-term storage** with Thanos or Cortex
5. **Add application-specific metrics** for deeper insights

For more information:
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)

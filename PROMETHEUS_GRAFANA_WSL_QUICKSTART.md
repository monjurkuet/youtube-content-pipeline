# Prometheus & Grafana WSL2 - Quick Start Guide

## ✅ Installation Complete!

Your native Prometheus and Grafana setup on WSL2 is now **running and healthy**.

---

## 🎯 Service Status

| Service | Status | Port | URL |
|---------|--------|------|-----|
| **Prometheus** | ✅ Running | 9090 | http://localhost:9090 |
| **Grafana** | ✅ Running | 3000 | http://localhost:3000 |

---

## 🚀 Quick Access

### Prometheus
- **UI**: http://localhost:9090
- **Health**: http://localhost:9090/-/healthy
- **Targets**: http://localhost:9090/api/v1/targets
- **Metrics**: http://localhost:9090/metrics

### Grafana
- **UI**: http://localhost:3000
- **Login**: `admin` / `admin` (change on first login!)
- **Health**: http://localhost:3000/api/health

---

## 📊 What's Configured

### Prometheus Targets
1. **Prometheus Self-Monitoring** (`localhost:9090`)
2. **Transcription Pipeline API** (`10.255.255.254:8000`)

### Alert Rules
- High error rate (>5%)
- Long job duration (>5 minutes)
- High active jobs (>100)
- Redis connection lost
- Database connection lost
- API down

### Grafana Dashboard
- **Name**: "YouTube Transcription Pipeline"
- **Panels**:
  - Total API Requests
  - Error Rate
  - Active Transcription Jobs
  - P95 Job Duration
  - Request Rate (5m avg)
  - API Request Latency (P50, P90, P95, P99)
  - Error Rate by Status Code
  - Transcription Jobs (Success/Failed)

---

## 🔧 Managing Services

### Start/Stop/Restart

```bash
# Prometheus
sudo systemctl start prometheus
sudo systemctl stop prometheus
sudo systemctl restart prometheus
sudo systemctl status prometheus

# Grafana
sudo systemctl start grafana-server
sudo systemctl stop grafana-server
sudo systemctl restart grafana-server
sudo systemctl status grafana-server
```

### Enable/Disable Auto-Start

```bash
# Both services are already enabled
sudo systemctl enable prometheus
sudo systemctl enable grafana-server

# To disable
sudo systemctl disable prometheus
sudo systemctl disable grafana-server
```

### View Logs

```bash
# Prometheus logs
sudo journalctl -u prometheus -f
sudo journalctl -u prometheus --since "1 hour ago"

# Grafana logs
sudo journalctl -u grafana-server -f
sudo journalctl -u grafana-server --since "1 hour ago"
```

---

## 📝 Configuration Files

| File | Purpose |
|------|---------|
| `/opt/monitoring/config/prometheus.yml` | Prometheus scrape config |
| `/opt/monitoring/config/alerts.yml` | Alert rules |
| `/opt/monitoring/config/grafana-dashboards/` | Grafana dashboards |
| `/etc/grafana/provisioning/datasources/prometheus.yml` | Prometheus datasource |
| `/etc/systemd/system/prometheus.service` | Prometheus systemd service |
| `/etc/systemd/system/grafana-server.service` | Grafana systemd service |

### Data Storage

| Service | Data Directory |
|---------|---------------|
| Prometheus | `/opt/monitoring/data/prometheus` |
| Grafana | `/opt/monitoring/data/grafana` |

**Retention**: Prometheus keeps 15 days of metrics by default.

---

## 🔗 Connecting Your API

### Option 1: API Running on Windows Host (Default)

Your API is already configured to scrape from Windows:
- **Target**: `10.255.255.254:8000`
- **Metrics Path**: `/metrics`

Make sure your API is running on Windows and accessible.

### Option 2: API Running in WSL

Edit `/opt/monitoring/config/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'transcription-pipeline'
    static_configs:
      - targets: ['localhost:8000']  # Change to localhost
```

Then reload Prometheus:
```bash
curl -X POST http://localhost:9090/-/reload
```

### Testing API Metrics

```bash
# Test from WSL
curl http://localhost:8000/metrics

# Test from Windows (replace with your API URL)
curl http://10.255.255.254:8000/metrics
```

---

## 📈 Useful PromQL Queries

Open Prometheus UI (http://localhost:9090) and try these queries:

### Request Rate
```promql
rate(api_requests_total[5m])
```

### Error Rate
```promql
sum(rate(api_requests_total{status_code=~"5.."}[5m])) / sum(rate(api_requests_total[5m]))
```

### Job Duration (P95)
```promql
histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m]))
```

### Active Jobs
```promql
transcription_jobs_created
```

### API Latency Percentiles
```promql
histogram_quantile(0.50, rate(api_request_duration_seconds_bucket[5m]))  # P50
histogram_quantile(0.90, rate(api_request_duration_seconds_bucket[5m]))  # P90
histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m]))  # P95
histogram_quantile(0.99, rate(api_request_duration_seconds_bucket[5m]))  # P99
```

---

## 🎨 Grafana Tips

### First Login
1. Go to http://localhost:3000
2. Login with `admin` / `admin`
3. **Change the password immediately!**
4. The Prometheus datasource is already configured
5. The dashboard is already imported

### Import Additional Dashboards
1. Go to **Dashboards** → **Import**
2. Enter dashboard ID from https://grafana.com/grafana/dashboards/
3. Select Prometheus datasource
4. Click **Import**

### Recommended Dashboards
- **Node Exporter Full** (ID: 1860) - System metrics
- **Prometheus Stats** (ID: 2) - Prometheus itself
- **API Dashboard** - Create custom for your API

---

## 🔔 Alerting

### View Alerts in Grafana
1. Go to **Alerting** → **Alert Rules**
2. See all configured alerts

### Alert Channels
To receive alerts via email/Slack/etc:
1. Go to **Alerting** → **Contact points**
2. Add contact point (email, Slack, webhook, etc.)
3. Create notification policy

### Test Alerts
Trigger a test alert:
```bash
# Generate some errors (if API is running)
for i in {1..100}; do curl http://localhost:8000/nonexistent; done
```

---

## 🛠️ Troubleshooting

### Prometheus Not Starting
```bash
# Check config validity
/opt/monitoring/prometheus/promtool check config /opt/monitoring/config/prometheus.yml

# Check logs
sudo journalctl -u prometheus -n 50 --no-pager

# Check permissions
ls -la /opt/monitoring/data/prometheus
```

### Grafana Not Starting
```bash
# Check logs
sudo journalctl -u grafana-server -n 50 --no-pager

# Check permissions
sudo chown -R grafana:grafana /opt/monitoring/data/grafana
sudo chmod -R 755 /opt/monitoring/data/grafana

# Restart
sudo systemctl restart grafana-server
```

### Can't Access from Windows Browser
1. **Firewall**: Allow ports 3000 and 9090 on Windows
```powershell
New-NetFirewallRule -DisplayName "Grafana WSL" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Prometheus WSL" -Direction Inbound -LocalPort 9090 -Protocol TCP -Action Allow
```

2. **Use WSL IP**: Access via `http://<WSL-IP>:3000` instead of localhost
   - Find WSL IP: `ip addr show eth0 | grep "inet\b" | awk '{print $2}' | cut -d/ -f1`

### Metrics Not Showing
1. **Check API is running**: `curl http://localhost:8000/metrics`
2. **Check Prometheus targets**: http://localhost:9090/targets
3. **Check scrape config**: `cat /opt/monitoring/config/prometheus.yml`
4. **Reload Prometheus**: `curl -X POST http://localhost:9090/-/reload`

---

## 📚 Additional Resources

- **Prometheus Docs**: https://prometheus.io/docs/
- **Grafana Docs**: https://grafana.com/docs/
- **PromQL Tutorial**: https://prometheus.io/docs/prometheus/latest/querying/examples/
- **Grafana Dashboards**: https://grafana.com/grafana/dashboards/

---

## 🔄 Updates

### Update Prometheus
```bash
cd /tmp
curl -LO https://github.com/prometheus/prometheus/releases/download/v2.48.0/prometheus-2.48.0.linux-amd64.tar.gz
tar xzf prometheus-2.48.0.linux-amd64.tar.gz
sudo systemctl stop prometheus
cp prometheus-2.48.0.linux-amd64/prometheus /opt/monitoring/prometheus/
sudo systemctl start prometheus
```

### Update Grafana
```bash
sudo apt-get update
sudo apt-get install grafana
sudo systemctl restart grafana-server
```

---

## 🎉 Next Steps

1. **Start your API**: Make sure your transcription pipeline API is running
2. **Access Grafana**: http://localhost:3000 (login: admin/admin)
3. **View Dashboard**: Click on "YouTube Transcription Pipeline" dashboard
4. **Set up Alerts**: Configure notification channels in Grafana
5. **Customize**: Modify dashboard panels to your needs

---

**Setup completed successfully!** 🚀

For detailed documentation, see:
- `PROMETHEUS_WSL_SETUP.md` - Full setup guide
- `API_USAGE_GUIDE.md` - API usage examples
- `CONFIGURATION_REFERENCE.md` - All configuration options

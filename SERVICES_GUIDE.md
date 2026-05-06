# Services Quick Start Guide

## 🚀 Launch All Services

```bash
# Start all services (API, Prometheus, Grafana)
./scripts/launch-services.sh start

# Stop all services
./scripts/launch-services.sh stop

# Restart all services
./scripts/launch-services.sh restart

# Check service status
./scripts/launch-services.sh status
```

## 🌐 Access URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://localhost:18080 | - |
| **Swagger UI** | http://localhost:18080/docs | - |
| **Prometheus** | http://localhost:19090 | - |
| **Grafana** | http://localhost:13000 | admin / admin |

## ⚙️ Configuration

Edit `ports.yaml` in the project root to customize ports:

```yaml
api:
  port: 18080  # API server port

prometheus:
  port: 19090  # Prometheus port

grafana:
  port: 13000  # Grafana port
```

## ✅ Service Status

All services are currently:
- ✅ API: Running on port 18080
- ✅ Prometheus: Running on port 19090
- ✅ Grafana: Running on port 13000

## 🔍 Health Checks

```bash
# API Health
curl http://localhost:18080/health

# Prometheus Health
curl http://localhost:19090/-/healthy

# Grafana Health
curl http://localhost:13000/api/health
```

## 📊 Monitoring

### Prometheus Metrics
- **URL**: http://localhost:19090
- **Targets**: Automatically scraping API on port 18080
- **Queries**: Use PromQL at http://localhost:19090/graph

### Grafana Dashboards
- **URL**: http://localhost:13000
- **Login**: admin / admin (change on first login!)
- **Dashboard**: "YouTube Transcription Pipeline" (auto-loaded)

## 🛑 Troubleshooting

### Port Already in Use
The script automatically clears ports before starting. If issues persist:

```bash
# Manually kill processes on ports
./scripts/launch-services.sh stop

# Or kill specific port
lsof -ti:18080 | xargs kill -9
```

### Service Not Starting
Check logs:
```bash
# API logs
tail -f /tmp/transcription_api.log

# Prometheus logs
tail -f /tmp/prometheus.log

# Grafana logs
tail -f /tmp/grafana.log
```

### Prometheus Lock File Issues
```bash
sudo rm -f /opt/monitoring/data/prometheus/lock
./scripts/launch-services.sh restart
```

## 📝 Notes

- **Uncommon Ports**: Using ports 18080, 19090, 13000 to avoid conflicts
- **Auto-Cleanup**: Script clears ports before starting
- **Graceful Shutdown**: Services are properly stopped
- **Configuration**: All ports configurable via `ports.yaml`

### CDP Cookie Extractor

Standalone CLI for extracting YouTube auth cookies from Chrome instances via Chrome DevTools Protocol.

```bash
# Check available auth cookies (no write)
python scripts/cdp_cookie_extractor.py --dry-run

# Extract and write to yt-dlp cookies file
python scripts/cdp_cookie_extractor.py --output ~/.config/yt-dlp/cookies.txt

# Use specific Chrome CDP port
python scripts/cdp_cookie_extractor.py --port 9222

# Output as cookie header string (for API injection)
python scripts/cdp_cookie_extractor.py --format string
```

**When to use:** Before transcription batches if YouTube API returns IP-block/403 errors. Also via cron before scheduled transcription runs.

**Prerequisites:** Chrome must be running with `--remote-debugging-port` enabled and logged into YouTube.

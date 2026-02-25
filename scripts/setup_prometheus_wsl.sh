#!/bin/bash
# =============================================================================
# Prometheus & Grafana Native WSL2 Setup Script
# =============================================================================
# This script installs and configures Prometheus and Grafana natively on WSL2
# for monitoring the YouTube Transcription Pipeline API.
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROMETHEUS_VERSION="2.48.0"
GRAFANA_VERSION="10.2.3"
INSTALL_DIR="/opt/monitoring"
PROMETHEUS_DIR="${INSTALL_DIR}/prometheus"
GRAFANA_DIR="${INSTALL_DIR}/grafana"
CONFIG_DIR="${INSTALL_DIR}/config"
DATA_DIR="${INSTALL_DIR}/data"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (use sudo)"
        exit 1
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for required tools
    for cmd in curl tar systemctl; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is not installed. Please install it first."
            exit 1
        fi
    done
    
    # Check disk space (need at least 2GB)
    available_space=$(df -m /opt | awk 'NR==2 {print $4}')
    if [ "$available_space" -lt 2048 ]; then
        log_error "Insufficient disk space. Need at least 2GB free."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# =============================================================================
# Installation Functions
# =============================================================================

create_directories() {
    log_info "Creating directories..."
    mkdir -p "$PROMETHEUS_DIR"
    mkdir -p "$GRAFANA_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR/prometheus"
    mkdir -p "$DATA_DIR/grafana"
    chown -R muham:muham "$INSTALL_DIR"
    log_success "Directories created"
}

install_prometheus() {
    log_info "Downloading Prometheus ${PROMETHEUS_VERSION}..."
    
    cd /tmp
    
    # Download Prometheus
    curl -LO "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz"
    
    log_info "Extracting Prometheus..."
    tar xzf "prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz"
    
    # Copy binaries
    cp "prometheus-${PROMETHEUS_VERSION}.linux-amd64/prometheus" "$PROMETHEUS_DIR/"
    cp "prometheus-${PROMETHEUS_VERSION}.linux-amd64/promtool" "$PROMETHEUS_DIR/"
    
    # Copy example configs
    cp "prometheus-${PROMETHEUS_VERSION}.linux-amd64/prometheus.yml" "$CONFIG_DIR/"
    cp -r "prometheus-${PROMETHEUS_VERSION}.linux-amd64/consoles" "$PROMETHEUS_DIR/"
    cp -r "prometheus-${PROMETHEUS_VERSION}.linux-amd64/console_libraries" "$PROMETHEUS_DIR/"
    
    # Set permissions
    chmod +x "$PROMETHEUS_DIR/prometheus"
    chmod +x "$PROMETHEUS_DIR/promtool"
    chown -R muham:muham "$PROMETHEUS_DIR"
    
    # Cleanup
    rm -rf "prometheus-${PROMETHEUS_VERSION}.linux-amd64"*
    
    log_success "Prometheus installed to $PROMETHEUS_DIR"
}

install_grafana() {
    log_info "Installing Grafana ${GRAFANA_VERSION}..."
    
    # Add Grafana APT repository
    sudo apt-get install -y apt-transport-https software-properties-common wget
    
    # Import GPG key
    wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
    
    # Add repository
    echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
    
    # Update and install
    sudo apt-get update
    sudo apt-get install -y grafana
    
    log_success "Grafana installed"
}

# =============================================================================
# Configuration Functions
# =============================================================================

configure_prometheus() {
    log_info "Configuring Prometheus..."
    
    cat > "$CONFIG_DIR/prometheus.yml" << 'EOF'
# Prometheus configuration for YouTube Transcription Pipeline
# Location: /opt/monitoring/config/prometheus.yml

global:
  scrape_interval: 15s          # How often to scrape targets
  evaluation_interval: 15s      # How often to evaluate rules
  external_labels:
    monitor: 'youtube-transcription-pipeline'
    environment: 'development'

# Alertmanager configuration (optional)
# alerting:
#   alertmanagers:
#     - static_configs:
#         - targets: ['localhost:9093']

# Rule files (optional)
rule_files:
  - "/opt/monitoring/config/alerts.yml"

# Scrape configurations
scrape_configs:
  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'

  # YouTube Transcription Pipeline API
  - job_name: 'transcription-pipeline'
    static_configs:
      - targets: ['host.docker.internal:8000']
        labels:
          service: 'api'
          environment: 'development'
    metrics_path: '/metrics'
    scrape_interval: 10s
    
    # If running API on WSL host (Windows), use Windows IP
    # Replace with your Windows host IP if needed
    # relabel_configs:
    #   - source_labels: [__address__]
    #     target_label: __address__
    #     regex: 'host\.docker\.internal:8000'
    #     replacement: '172.28.16.1:8000'

  # If API runs on same WSL instance, use localhost
  - job_name: 'transcription-pipeline-local'
    static_configs:
      - targets: ['localhost:8000']
        labels:
          service: 'api'
          environment: 'development'
    metrics_path: '/metrics'
    scrape_interval: 10s
    # Enable only if API runs on same WSL instance
    enabled: false

  # Node Exporter for system metrics (optional)
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
    enabled: false
EOF

    chown muham:muham "$CONFIG_DIR/prometheus.yml"
    log_success "Prometheus configured"
}

configure_grafana() {
    log_info "Configuring Grafana..."
    
    # Create Grafana provisioning directory
    mkdir -p /etc/grafana/provisioning/datasources
    mkdir -p /etc/grafana/provisioning/dashboards
    
    # Create Prometheus datasource
    cat > /etc/grafana/provisioning/datasources/prometheus.yml << 'EOF'
# Grafana datasource provisioning for Prometheus
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://localhost:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: "15s"
      httpMethod: POST
EOF

    # Create dashboard provisioning
    cat > /etc/grafana/provisioning/dashboards/dashboards.yml << 'EOF'
# Grafana dashboard provisioning
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    folderUid: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /opt/monitoring/config/grafana-dashboards
EOF

    # Create dashboards directory
    mkdir -p /opt/monitoring/config/grafana-dashboards
    chown -R grafana:grafana /opt/monitoring/config/grafana-dashboards
    
    log_success "Grafana configured"
}

create_alert_rules() {
    log_info "Creating alert rules..."
    
    cat > "$CONFIG_DIR/alerts.yml" << 'EOF'
# Prometheus alert rules for YouTube Transcription Pipeline
groups:
  - name: transcription_pipeline_alerts
    interval: 30s
    rules:
      # High error rate alert
      - alert: HighErrorRate
        expr: rate(api_requests_total{status_code=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec over the last 5 minutes"

      # Job duration too long
      - alert: LongJobDuration
        expr: histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m])) > 300
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Transcription jobs taking too long"
          description: "95th percentile job duration is {{ $value }} seconds"

      # Too many active jobs
      - alert: HighActiveJobs
        expr: transcription_jobs_created > 100
        for: 5m
        labels:
          severity: info
        annotations:
          summary: "High number of active transcription jobs"
          description: "{{ $value }} jobs currently active"

      # Redis connection lost
      - alert: RedisConnectionLost
        expr: redis_operations_total{status="error"} > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Redis connection errors detected"
          description: "Redis operations are failing"

      # Database connection lost
      - alert: DatabaseConnectionLost
        expr: mongodb_operations_total{status="error"} > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Database connection errors detected"
          description: "MongoDB operations are failing"

      # API down
      - alert: APIDown
        expr: up{job="transcription-pipeline"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Transcription Pipeline API is down"
          description: "API has been down for more than 1 minute"
EOF

    chown muham:muham "$CONFIG_DIR/alerts.yml"
    log_success "Alert rules created"
}

create_grafana_dashboard() {
    log_info "Creating Grafana dashboard..."
    
    cat > /opt/monitoring/config/grafana-dashboards/transcription-pipeline.json << 'EOF'
{
  "annotations": {
    "list": []
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "10.2.3",
      "targets": [
        {
          "expr": "sum(api_requests_total)",
          "legendFormat": "Total Requests",
          "refId": "A"
        }
      ],
      "title": "Total API Requests",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 0.05
              }
            ]
          },
          "unit": "percentunit"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 6,
        "y": 0
      },
      "id": 2,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "10.2.3",
      "targets": [
        {
          "expr": "sum(rate(api_requests_total{status_code=~\"5..\"}[5m])) / sum(rate(api_requests_total[5m]))",
          "legendFormat": "Error Rate",
          "refId": "A"
        }
      ],
      "title": "Error Rate",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 12,
        "y": 0
      },
      "id": 3,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "10.2.3",
      "targets": [
        {
          "expr": "transcription_jobs_created",
          "legendFormat": "Active Jobs",
          "refId": "A"
        }
      ],
      "title": "Active Transcription Jobs",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 18,
        "y": 0
      },
      "id": 4,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {
          "calcs": ["mean"],
          "fields": "",
          "values": false
        },
        "textMode": "auto"
      },
      "pluginVersion": "10.2.3",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(transcription_duration_seconds_bucket[5m]))",
          "legendFormat": "P95 Duration",
          "refId": "A"
        }
      ],
      "title": "P95 Job Duration",
      "type": "stat"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "reqps"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 4
      },
      "id": 5,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "targets": [
        {
          "expr": "rate(api_requests_total[5m])",
          "legendFormat": "{{method}} {{endpoint}}",
          "refId": "A"
        }
      ],
      "title": "Request Rate (5m avg)",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 4
      },
      "id": 6,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "targets": [
        {
          "expr": "histogram_quantile(0.50, rate(api_request_duration_seconds_bucket[5m]))",
          "legendFormat": "P50",
          "refId": "A"
        },
        {
          "expr": "histogram_quantile(0.90, rate(api_request_duration_seconds_bucket[5m]))",
          "legendFormat": "P90",
          "refId": "B"
        },
        {
          "expr": "histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m]))",
          "legendFormat": "P95",
          "refId": "C"
        },
        {
          "expr": "histogram_quantile(0.99, rate(api_request_duration_seconds_bucket[5m]))",
          "legendFormat": "P99",
          "refId": "D"
        }
      ],
      "title": "API Request Latency",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 0.05
              }
            ]
          },
          "unit": "percentunit"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 12
      },
      "id": 7,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "targets": [
        {
          "expr": "sum(rate(api_requests_total{status_code=~\"4..\"}[5m])) by (status_code) / sum(rate(api_requests_total[5m]))",
          "legendFormat": "4xx Error Rate",
          "refId": "A"
        },
        {
          "expr": "sum(rate(api_requests_total{status_code=~\"5..\"}[5m])) by (status_code) / sum(rate(api_requests_total[5m]))",
          "legendFormat": "5xx Error Rate",
          "refId": "B"
        }
      ],
      "title": "Error Rate by Status Code",
      "type": "timeseries"
    },
    {
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "legend": false,
              "tooltip": false,
              "viz": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 12
      },
      "id": 8,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "single",
          "sort": "none"
        }
      },
      "targets": [
        {
          "expr": "transcription_jobs_total{status=\"success\"}",
          "legendFormat": "Successful Jobs",
          "refId": "A"
        },
        {
          "expr": "transcription_jobs_total{status=\"failed\"}",
          "legendFormat": "Failed Jobs",
          "refId": "B"
        }
      ],
      "title": "Transcription Jobs",
      "type": "timeseries"
    }
  ],
  "refresh": "10s",
  "schemaVersion": 38,
  "style": "dark",
  "tags": ["transcription", "youtube", "api"],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "browser",
  "title": "YouTube Transcription Pipeline",
  "uid": "transcription-pipeline",
  "version": 1,
  "weekStart": ""
}
EOF

    chown grafana:grafana /opt/monitoring/config/grafana-dashboards/transcription-pipeline.json
    log_success "Grafana dashboard created"
}

# =============================================================================
# Startup Scripts
# =============================================================================

create_startup_scripts() {
    log_info "Creating startup scripts..."
    
    # Create Prometheus startup script
    cat > "$INSTALL_DIR/start-prometheus.sh" << EOF
#!/bin/bash
# Start Prometheus
cd $PROMETHEUS_DIR
exec $PROMETHEUS_DIR/prometheus \\
    --config.file=$CONFIG_DIR/prometheus.yml \\
    --storage.tsdb.path=$DATA_DIR/prometheus \\
    --storage.tsdb.retention.time=15d \\
    --web.console.libraries=$PROMETHEUS_DIR/console_libraries \\
    --web.console.templates=$PROMETHEUS_DIR/consoles \\
    --web.enable-lifecycle \\
    --web.enable-admin-api
EOF
    
    chmod +x "$INSTALL_DIR/start-prometheus.sh"
    
    # Create Grafana startup script (if not using systemd)
    cat > "$INSTALL_DIR/start-grafana.sh" << EOF
#!/bin/bash
# Start Grafana
exec grafana-server \\
    --config=/etc/grafana/grafana.ini \\
    --homepath=/usr/share/grafana \\
    cfg:default.paths.data=$DATA_DIR/grafana \\
    cfg:default.paths.logs=/var/log/grafana \\
    cfg:default.paths.plugins=/var/lib/grafana/plugins \\
    cfg:default.paths.provisioning=/etc/grafana/provisioning
EOF
    
    chmod +x "$INSTALL_DIR/start-grafana.sh"
    
    chown -R muham:muham "$INSTALL_DIR"
    
    log_success "Startup scripts created"
}

create_systemd_services() {
    log_info "Creating systemd services..."
    
    # Create Prometheus systemd service
    cat > /etc/systemd/system/prometheus.service << EOF
[Unit]
Description=Prometheus Monitoring System
Documentation=https://prometheus.io/docs/introduction/overview/
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=muham
Group=muham
ExecReload=/bin/kill -HUP \$MAINPID
ExecStart=$INSTALL_DIR/start-prometheus.sh
PIDFile=/run/prometheus.pid
Restart=on-failure
RestartSec=5

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR/prometheus

[Install]
WantedBy=multi-user.target
EOF

    # Create Grafana systemd service (if not already created by apt)
    if [ ! -f /etc/systemd/system/grafana-server.service ]; then
        cat > /etc/systemd/system/grafana-server.service << EOF
[Unit]
Description=Grafana Server
Documentation=https://grafana.com/docs/
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
User=grafana
Group=grafana
ExecStart=/usr/sbin/grafana-server --config=/etc/grafana/grafana.ini cfg:default.paths.data=$DATA_DIR/grafana
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    fi
    
    # Reload systemd
    systemctl daemon-reload
    
    log_success "Systemd services created"
}

# =============================================================================
# WSL-Specific Configuration
# =============================================================================

configure_wsl_networking() {
    log_info "Configuring WSL networking..."
    
    # Get Windows host IP
    WINDOWS_HOST_IP=$(grep -oP '(?<=nameserver ).+' /etc/resolv.conf 2>/dev/null | head -1 || echo "172.28.16.1")
    
    log_info "Windows host IP: $WINDOWS_HOST_IP"
    
    # Update Prometheus config with Windows host IP
    sed -i "s/host.docker.internal/${WINDOWS_HOST_IP}/g" "$CONFIG_DIR/prometheus.yml"
    
    # Create WSL networking guide
    cat > "$INSTALL_DIR/WSL_NETWORKING.md" << EOF
# WSL Networking Configuration

## Windows Host IP

Your Windows host IP is: **$WINDOWS_HOST_IP**

## Accessing API from WSL

If your API is running on Windows (not in WSL), update your Prometheus config:

\`\`\`yaml
scrape_configs:
  - job_name: 'transcription-pipeline'
    static_configs:
      - targets: ['${WINDOWS_HOST_IP}:8000']
\`\`\`

## Firewall Configuration

On Windows, allow incoming connections:

\`\`\`powershell
# Allow Prometheus (WSL to Windows)
New-NetFirewallRule -DisplayName "Prometheus WSL" -Direction Inbound -LocalPort 9090 -Protocol TCP -Action Allow

# Allow Grafana
New-NetFirewallRule -DisplayName "Grafana WSL" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow

# Allow API metrics (if needed)
New-NetFirewallRule -DisplayName "API Metrics" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
\`\`\`

## Accessing from Windows Browser

- Prometheus: http://$WINDOWS_HOST_IP:9090
- Grafana: http://$WINDOWS_HOST_IP:3000
EOF
    
    log_success "WSL networking configured"
}

# =============================================================================
# Main Installation Function
# =============================================================================

main() {
    echo "=============================================="
    echo "Prometheus & Grafana WSL2 Setup"
    echo "=============================================="
    echo ""
    
    check_root
    check_prerequisites
    create_directories
    install_prometheus
    install_grafana
    configure_prometheus
    configure_grafana
    create_alert_rules
    create_grafana_dashboard
    create_startup_scripts
    create_systemd_services
    configure_wsl_networking
    
    echo ""
    echo "=============================================="
    echo "Installation Complete!"
    echo "=============================================="
    echo ""
    echo "Next Steps:"
    echo "1. Start Prometheus:"
    echo "   sudo systemctl start prometheus"
    echo "   sudo systemctl enable prometheus"
    echo ""
    echo "2. Start Grafana:"
    echo "   sudo systemctl start grafana-server"
    echo "   sudo systemctl enable grafana-server"
    echo ""
    echo "3. Access the services:"
    echo "   - Prometheus: http://localhost:9090"
    echo "   - Grafana: http://localhost:3000"
    echo "     (Default login: admin/admin)"
    echo ""
    echo "4. Check status:"
    echo "   sudo systemctl status prometheus"
    echo "   sudo systemctl status grafana-server"
    echo ""
    echo "5. View logs:"
    echo "   journalctl -u prometheus -f"
    echo "   journalctl -u grafana-server -f"
    echo ""
    echo "Documentation: See $INSTALL_DIR/WSL_NETWORKING.md"
    echo ""
}

# Run main function
main "$@"

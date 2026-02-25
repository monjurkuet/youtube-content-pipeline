#!/bin/bash
# =============================================================================
# YouTube Transcription Pipeline - Service Launcher
# =============================================================================
# This script starts all services (API, Prometheus, Grafana) with configurable
# ports from config/ports.yaml. It ensures ports are clear before starting.
#
# Usage:
#   ./scripts/launch-services.sh [start|stop|restart|status]
#
# Examples:
#   ./scripts/launch-services.sh start      # Start all services
#   ./scripts/launch-services.sh stop       # Stop all services
#   ./scripts/launch-services.sh restart    # Restart all services
#   ./scripts/launch-services.sh status     # Check service status
# =============================================================================

set -e  # Exit on error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/ports.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# =============================================================================
# Configuration Loading
# =============================================================================

load_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "Configuration file not found: $CONFIG_FILE"
        exit 1
    fi
    
    log_info "Loading configuration from $CONFIG_FILE"
    
    # Parse YAML using Python (more reliable than bash YAML parsers)
    API_PORT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['api']['port'])")
    API_HOST=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['api']['host'])")
    
    PROMETHEUS_PORT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['prometheus']['port'])")
    PROMETHEUS_CONFIG=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['prometheus']['config_path'])")
    PROMETHEUS_DATA=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['prometheus']['storage_path'])")
    
    GRAFANA_PORT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['grafana']['port'])")
    GRAFANA_DATA=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['grafana']['data_path'])")
    
    log_success "Configuration loaded successfully"
    log_info "API Port: $API_PORT"
    log_info "Prometheus Port: $PROMETHEUS_PORT"
    log_info "Grafana Port: $GRAFANA_PORT"
}

# =============================================================================
# Port Management
# =============================================================================

check_port_in_use() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

get_pid_on_port() {
    local port=$1
    lsof -t -i :$port 2>/dev/null | head -1
}

kill_process_on_port() {
    local port=$1
    local pid=$(get_pid_on_port $port)
    
    if [ -n "$pid" ]; then
        log_warning "Port $port is in use by PID $pid, killing..."
        kill -9 $pid 2>/dev/null || true
        sleep 1
        
        # Verify it's dead
        if check_port_in_use $port; then
            log_error "Failed to kill process on port $port"
            return 1
        else
            log_success "Killed process on port $port"
            return 0
        fi
    else
        return 0
    fi
}

clear_all_ports() {
    log_info "Clearing all service ports..."
    
    local ports=($API_PORT $PROMETHEUS_PORT $GRAFANA_PORT)
    local failed=0
    
    for port in "${ports[@]}"; do
        if ! kill_process_on_port $port; then
            failed=1
        fi
    done
    
    if [ $failed -eq 0 ]; then
        log_success "All ports cleared"
    else
        log_error "Some ports could not be cleared"
        return 1
    fi
}

# =============================================================================
# Service Management
# =============================================================================

start_api() {
    log_info "Starting YouTube Transcription API on port $API_PORT..."
    
    cd "$PROJECT_DIR"
    
    # Start API in background
    nohup uv run uvicorn src.api.app:app \
        --host "$API_HOST" \
        --port "$API_PORT" \
        > /tmp/transcription_api.log 2>&1 &
    
    API_PID=$!
    echo $API_PID > /tmp/transcription_api.pid
    
    # Wait for startup
    sleep 5
    
    # Check if running
    if ps -p $API_PID > /dev/null 2>&1; then
        log_success "API started (PID: $API_PID)"
        return 0
    else
        log_error "API failed to start. Check /tmp/transcription_api.log"
        tail -20 /tmp/transcription_api.log
        return 1
    fi
}

start_prometheus() {
    log_info "Starting Prometheus on port $PROMETHEUS_PORT..."
    
    # Clear any stale lock files
    if [ -f "$PROMETHEUS_DATA/lock" ]; then
        log_warning "Removing stale Prometheus lock file"
        sudo rm -f "$PROMETHEUS_DATA/lock"
    fi
    
    # Update Prometheus config with new port
    if [ -f "$PROMETHEUS_CONFIG" ]; then
        # Update scrape target port
        sed -i "s/:8000/:$API_PORT/g" "$PROMETHEUS_CONFIG"
        sed -i "s/:9090/:$PROMETHEUS_PORT/g" "$PROMETHEUS_CONFIG"
        log_info "Updated Prometheus config for port $PROMETHEUS_PORT"
    fi
    
    # Start Prometheus
    nohup /opt/monitoring/prometheus/prometheus \
        --config.file="$PROMETHEUS_CONFIG" \
        --storage.tsdb.path="$PROMETHEUS_DATA" \
        --storage.tsdb.retention.time=15d \
        --web.listen-address=":$PROMETHEUS_PORT" \
        --web.enable-lifecycle \
        > /tmp/prometheus.log 2>&1 &
    
    PROMETHEUS_PID=$!
    echo $PROMETHEUS_PID > /tmp/prometheus.pid
    
    # Wait for startup
    sleep 3
    
    # Check if running
    if ps -p $PROMETHEUS_PID > /dev/null 2>&1; then
        log_success "Prometheus started (PID: $PROMETHEUS_PID)"
        return 0
    else
        log_error "Prometheus failed to start. Check /tmp/prometheus.log"
        tail -20 /tmp/prometheus.log
        return 1
    fi
}

start_grafana() {
    log_info "Starting Grafana on port $GRAFANA_PORT..."
    
    # Ensure data directory exists and has correct permissions
    sudo mkdir -p "$GRAFANA_DATA"
    sudo chown -R grafana:grafana "$GRAFANA_DATA"
    
    # Start Grafana with custom port
    nohup sudo /usr/sbin/grafana-server \
        --config=/etc/grafana/grafana.ini \
        --homepath=/usr/share/grafana \
        cfg:default.paths.data="$GRAFANA_DATA" \
        cfg:default.server.http_port="$GRAFANA_PORT" \
        > /tmp/grafana.log 2>&1 &
    
    GRAFANA_PID=$!
    echo $GRAFANA_PID > /tmp/grafana.pid
    
    # Wait for startup
    sleep 5
    
    # Check if running
    if ps -p $GRAFANA_PID > /dev/null 2>&1; then
        log_success "Grafana started (PID: $GRAFANA_PID)"
        return 0
    else
        log_error "Grafana failed to start. Check /tmp/grafana.log"
        tail -20 /tmp/grafana.log
        return 1
    fi
}

stop_service() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            log_info "Stopping $name (PID: $pid)..."
            kill $pid 2>/dev/null || true
            sleep 2
            
            # Force kill if still running
            if ps -p $pid > /dev/null 2>&1; then
                kill -9 $pid 2>/dev/null || true
            fi
            
            rm -f "$pid_file"
            log_success "$name stopped"
        else
            log_warning "$name is not running"
            rm -f "$pid_file"
        fi
    else
        log_warning "$name PID file not found"
    fi
}

stop_all_services() {
    log_info "Stopping all services..."
    
    stop_service "API" "/tmp/transcription_api.pid"
    stop_service "Prometheus" "/tmp/prometheus.pid"
    stop_service "Grafana" "/tmp/grafana.pid"
    
    # Also kill by port as backup
    clear_all_ports
    
    log_success "All services stopped"
}

check_service_status() {
    local name=$1
    local port=$2
    local pid_file=$3
    
    echo -n "  $name: "
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            if curl -s "http://localhost:$port" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Running${NC} (PID: $pid, Port: $port)"
                return 0
            else
                echo -e "${YELLOW}⚠ Running but not responding${NC} (PID: $pid)"
                return 1
            fi
        else
            echo -e "${RED}✗ Not running${NC} (stale PID file)"
            return 1
        fi
    else
        if check_port_in_use $port; then
            local pid=$(get_pid_on_port $port)
            echo -e "${YELLOW}⚠ Running (external)${NC} (PID: $pid, Port: $port)"
            return 0
        else
            echo -e "${RED}✗ Not running${NC}"
            return 1
        fi
    fi
}

status_all_services() {
    echo ""
    echo "=============================================="
    echo "Service Status"
    echo "=============================================="
    echo ""
    
    check_service_status "API" "$API_PORT" "/tmp/transcription_api.pid"
    check_service_status "Prometheus" "$PROMETHEUS_PORT" "/tmp/prometheus.pid"
    check_service_status "Grafana" "$GRAFANA_PORT" "/tmp/grafana.pid"
    
    echo ""
    echo "=============================================="
    echo "Access URLs"
    echo "=============================================="
    echo "  API:         http://localhost:$API_PORT"
    echo "  Swagger UI:  http://localhost:$API_PORT/docs"
    echo "  Prometheus:  http://localhost:$PROMETHEUS_PORT"
    echo "  Grafana:     http://localhost:$GRAFANA_PORT (admin/admin)"
    echo ""
}

health_check() {
    log_info "Running health checks..."
    
    echo ""
    
    # API Health
    echo -n "API Health: "
    if curl -s "http://localhost:$API_PORT/health" | grep -q "healthy"; then
        echo -e "${GREEN}✓ Healthy${NC}"
    else
        echo -e "${RED}✗ Unhealthy${NC}"
    fi
    
    # Prometheus Health
    echo -n "Prometheus Health: "
    if curl -s "http://localhost:$PROMETHEUS_PORT/-/healthy" | grep -q "Prometheus Server is Healthy"; then
        echo -e "${GREEN}✓ Healthy${NC}"
    else
        echo -e "${RED}✗ Unhealthy${NC}"
    fi
    
    # Grafana Health
    echo -n "Grafana Health: "
    if curl -s "http://localhost:$GRAFANA_PORT/api/health" | grep -q '"database".*"ok"'; then
        echo -e "${GREEN}✓ Healthy${NC}"
    else
        echo -e "${RED}✗ Unhealthy${NC}"
    fi
    
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    local command=${1:-"start"}
    
    echo "=============================================="
    echo "YouTube Transcription Pipeline"
    echo "Service Manager"
    echo "=============================================="
    echo ""
    
    # Load configuration
    load_config
    
    case $command in
        start)
            clear_all_ports
            start_api
            start_prometheus
            start_grafana
            sleep 3
            status_all_services
            health_check
            ;;
        stop)
            stop_all_services
            status_all_services
            ;;
        restart)
            stop_all_services
            sleep 2
            clear_all_ports
            start_api
            start_prometheus
            start_grafana
            sleep 3
            status_all_services
            health_check
            ;;
        status)
            status_all_services
            health_check
            ;;
        *)
            echo "Usage: $0 {start|stop|restart|status}"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"

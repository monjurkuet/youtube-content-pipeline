#!/bin/bash
# =============================================================================
# YouTube Transcription Pipeline - API Launcher
# =============================================================================
# This script starts ONLY the API service. Prometheus and Grafana are expected
# to run as system services.
#
# Usage:
#   ./scripts/start-api.sh [start|stop|restart|status]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/ports.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load port config
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        API_PORT=$(grep "api_port:" "$CONFIG_FILE" | awk '{print $2}')
        [ -z "$API_PORT" ] && API_PORT=18080
    else
        log_warning "Config file not found, using defaults"
        API_PORT=18080
    fi
}

get_pid() {
    lsof -t -i :$API_PORT 2>/dev/null | head -1
}

start_api() {
    load_config
    
    log_info "Starting YouTube Transcription API on port $API_PORT..."
    
    # Check if already running
    if [ -n "$(get_pid)" ]; then
        log_warning "API already running on port $API_PORT"
        return 0
    fi
    
    cd "$PROJECT_DIR"
    uv run uvicorn src.api.app:app --host 0.0.0.0 --port $API_PORT &
    
    # Wait for startup
    sleep 3
    
    if [ -n "$(get_pid)" ]; then
        log_success "API started (PID: $(get_pid), Port: $API_PORT)"
    else
        log_error "Failed to start API"
        exit 1
    fi
}

stop_api() {
    load_config
    
    log_info "Stopping API on port $API_PORT..."
    
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        kill $PID 2>/dev/null || true
        sleep 2
        if [ -n "$(get_pid)" ]; then
            kill -9 $PID 2>/dev/null || true
        fi
        log_success "API stopped"
    else
        log_warning "API not running"
    fi
}

status_api() {
    load_config
    
    echo ""
    echo "=============================================="
    echo "YouTube Transcription API Status"
    echo "=============================================="
    echo ""
    
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        echo -e "  API: ${GREEN}✓ Running${NC} (PID: $PID, Port: $API_PORT)"
    else
        echo -e "  API: ${RED}✗ Not running${NC} (Port: $API_PORT)"
    fi
    echo ""
}

case "${1:-start}" in
    start)
        start_api
        ;;
    stop)
        stop_api
        ;;
    restart)
        stop_api
        sleep 2
        start_api
        ;;
    status)
        status_api
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

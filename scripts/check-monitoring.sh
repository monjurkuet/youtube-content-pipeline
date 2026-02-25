#!/bin/bash
# =============================================================================
# Prometheus & Grafana Health Check Script
# =============================================================================

echo "=============================================="
echo "Prometheus & Grafana Health Check"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check Prometheus
echo -n "Checking Prometheus... "
if curl -s http://localhost:9090/-/healthy | grep -q "Prometheus Server is Healthy"; then
    echo -e "${GREEN}✓ HEALTHY${NC}"
    echo "  URL: http://localhost:9090"
    
    # Check targets
    targets=$(curl -s http://localhost:9090/api/v1/targets | grep -o '"activeTargets":\[[^]]*\]' | grep -o '"active":true' | wc -l)
    echo "  Active Targets: $targets"
else
    echo -e "${RED}✗ DOWN${NC}"
fi
echo ""

# Check Grafana
echo -n "Checking Grafana... "
if curl -s http://localhost:3000/api/health | grep -q '"database":"ok"'; then
    echo -e "${GREEN}✓ HEALTHY${NC}"
    echo "  URL: http://localhost:3000"
    version=$(curl -s http://localhost:3000/api/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
    echo "  Version: $version"
else
    echo -e "${RED}✗ DOWN${NC}"
fi
echo ""

# Check systemd services
echo "Service Status:"
echo -n "  Prometheus: "
systemctl is-active prometheus 2>/dev/null && echo -e "${GREEN}✓ running${NC}" || echo -e "${RED}✗ stopped${NC}"

echo -n "  Grafana: "
systemctl is-active grafana-server 2>/dev/null && echo -e "${GREEN}✓ running${NC}" || echo -e "${RED}✗ stopped${NC}"
echo ""

# Check data directories
echo "Data Directories:"
if [ -d "/opt/monitoring/data/prometheus" ]; then
    size=$(du -sh /opt/monitoring/data/prometheus 2>/dev/null | cut -f1)
    echo -e "  Prometheus: ${GREEN}✓${NC} ($size)"
else
    echo -e "  Prometheus: ${RED}✗ not found${NC}"
fi

if [ -d "/opt/monitoring/data/grafana" ]; then
    size=$(du -sh /opt/monitoring/data/grafana 2>/dev/null | cut -f1)
    echo -e "  Grafana: ${GREEN}✓${NC} ($size)"
else
    echo -e "  Grafana: ${RED}✗ not found${NC}"
fi
echo ""

# Check configuration
echo "Configuration:"
if [ -f "/opt/monitoring/config/prometheus.yml" ]; then
    echo -e "  Prometheus Config: ${GREEN}✓${NC}"
else
    echo -e "  Prometheus Config: ${RED}✗ not found${NC}"
fi

if [ -f "/opt/monitoring/config/alerts.yml" ]; then
    echo -e "  Alert Rules: ${GREEN}✓${NC}"
else
    echo -e "  Alert Rules: ${RED}✗ not found${NC}"
fi

if [ -d "/opt/monitoring/config/grafana-dashboards" ]; then
    dashboards=$(ls /opt/monitoring/config/grafana-dashboards/*.json 2>/dev/null | wc -l)
    echo -e "  Grafana Dashboards: ${GREEN}✓${NC} ($dashboards dashboards)"
else
    echo -e "  Grafana Dashboards: ${RED}✗ not found${NC}"
fi
echo ""

# Quick access URLs
echo "=============================================="
echo "Quick Access"
echo "=============================================="
echo "Prometheus UI:  http://localhost:9090"
echo "Grafana UI:     http://localhost:3000"
echo "Grafana Login:  admin / admin"
echo ""
echo "=============================================="

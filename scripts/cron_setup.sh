#!/bin/bash
#
# Reddit Radar Cron Setup Script
# Configures automated scanning at specified intervals
#
# Usage:
#   ./scripts/cron_setup.sh [OPTIONS]
#
# Options:
#   --interval HOURS    Set scan interval (default: 4)
#   --remove            Remove Reddit Radar from crontab
#   --show              Show current cron configuration
#   --dry-run           Show what would be added without making changes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Defaults
INTERVAL_HOURS=4
ACTION="install"

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOG_FILE="$PROJECT_ROOT/logs/scanner.log"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            INTERVAL_HOURS="$2"
            shift 2
            ;;
        --remove)
            ACTION="remove"
            shift
            ;;
        --show)
            ACTION="show"
            shift
            ;;
        --dry-run)
            ACTION="dry-run"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Generate cron expression
get_cron_expression() {
    local hours=$1
    if [ "$hours" -eq 1 ]; then
        echo "0 * * * *"
    elif [ "$hours" -eq 24 ]; then
        echo "0 8 * * *"
    else
        echo "0 */$hours * * *"
    fi
}

# Cron job identifier
CRON_ID="# Reddit Radar Scanner"

# Show current configuration
show_cron() {
    echo -e "${YELLOW}Current Reddit Radar cron configuration:${NC}"
    crontab -l 2>/dev/null | grep -A1 "$CRON_ID" || echo "No Reddit Radar cron job found."
}

# Remove from crontab
remove_cron() {
    echo -e "${YELLOW}Removing Reddit Radar from crontab...${NC}"
    crontab -l 2>/dev/null | grep -v "$CRON_ID" | grep -v "reddit-radar" | crontab -
    echo -e "${GREEN}Reddit Radar removed from crontab.${NC}"
}

# Install cron job
install_cron() {
    local dry_run=$1
    local cron_expr=$(get_cron_expression $INTERVAL_HOURS)

    # Create logs directory
    mkdir -p "$PROJECT_ROOT/logs"

    # Build cron line
    CRON_LINE="$cron_expr cd $PROJECT_ROOT && $VENV_PYTHON -m src.scanner --classify --respond >> $LOG_FILE 2>&1"

    if [ "$dry_run" = "true" ]; then
        echo -e "${YELLOW}Dry run - would add to crontab:${NC}"
        echo "$CRON_ID"
        echo "$CRON_LINE"
        echo ""
        echo -e "${YELLOW}Cron expression: $cron_expr (every $INTERVAL_HOURS hours)${NC}"
        return
    fi

    # Check for Python venv
    if [ ! -f "$VENV_PYTHON" ]; then
        echo -e "${RED}Error: Virtual environment not found at $VENV_PYTHON${NC}"
        echo "Please run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    fi

    # Remove existing entry if present
    crontab -l 2>/dev/null | grep -v "$CRON_ID" | grep -v "reddit-radar" > /tmp/crontab_temp || true

    # Add new entry
    echo "$CRON_ID" >> /tmp/crontab_temp
    echo "$CRON_LINE" >> /tmp/crontab_temp

    # Install new crontab
    crontab /tmp/crontab_temp
    rm /tmp/crontab_temp

    echo -e "${GREEN}Reddit Radar cron job installed!${NC}"
    echo ""
    echo "Configuration:"
    echo "  Interval: Every $INTERVAL_HOURS hours"
    echo "  Expression: $cron_expr"
    echo "  Log file: $LOG_FILE"
    echo ""
    echo "Commands:"
    echo "  View logs: tail -f $LOG_FILE"
    echo "  Show cron: ./scripts/cron_setup.sh --show"
    echo "  Remove: ./scripts/cron_setup.sh --remove"
}

# Main
case $ACTION in
    show)
        show_cron
        ;;
    remove)
        remove_cron
        ;;
    dry-run)
        install_cron "true"
        ;;
    install)
        install_cron "false"
        ;;
esac

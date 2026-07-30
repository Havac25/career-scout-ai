#!/bin/bash

# Database backup script
# Usage:
#   ./backup.sh --stash    : Backup data/career_scout.db to data/career_scout.db.bkp
#   ./backup.sh --pop      : Restore data/career_scout.db from data/career_scout.db.bkp

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DB_PATH="$PROJECT_ROOT/data/career_scout.db"
BKP_PATH="$PROJECT_ROOT/data/career_scout.db.bkp"

usage() {
    echo "Usage: $0 [--stash|--pop]"
    echo ""
    echo "Options:"
    echo "  --stash    Create backup: data/career_scout.db → data/career_scout.db.bkp"
    echo "  --pop      Restore from backup: data/career_scout.db.bkp → data/career_scout.db"
    exit 1
}

stash() {
    if [ ! -f "$DB_PATH" ]; then
        echo "Error: Database not found at $DB_PATH"
        exit 1
    fi
    
    if [ -f "$BKP_PATH" ]; then
        echo "Error: Backup already exists at $BKP_PATH"
        echo "Use --pop to restore the existing backup first"
        exit 1
    fi
    
    mv "$DB_PATH" "$BKP_PATH"
    echo "✓ Database backed up to $BKP_PATH"
}

pop() {
    if [ ! -f "$BKP_PATH" ]; then
        echo "Error: Backup not found at $BKP_PATH"
        exit 1
    fi
    
    rm -f "$DB_PATH"
    mv "$BKP_PATH" "$DB_PATH"
    echo "✓ Database restored from backup"
}

if [ $# -eq 0 ]; then
    usage
fi

case "$1" in
    --stash)
        stash
        ;;
    --pop)
        pop
        ;;
    *)
        echo "Error: Unknown option '$1'"
        usage
        ;;
esac

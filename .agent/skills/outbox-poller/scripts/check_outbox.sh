#!/usr/bin/env bash
# check_outbox.sh — List pending outbox tasks for the Antigravity agent
#
# Usage: ./check_outbox.sh [project_root]
#
# Scans .claude/outbox/pending/ for task files and outputs a summary.
# This script is deterministic and read-only — it never modifies files.

set -euo pipefail

PROJECT_ROOT="${1:-.}"
OUTBOX_DIR="${PROJECT_ROOT}/.claude/outbox/pending"

if [ ! -d "$OUTBOX_DIR" ]; then
    echo "NO_TASKS: Outbox directory does not exist at ${OUTBOX_DIR}"
    exit 0
fi

TASK_COUNT=$(find "$OUTBOX_DIR" -name "OBX-*.md" -type f 2>/dev/null | wc -l | tr -d ' ')

if [ "$TASK_COUNT" -eq 0 ]; then
    echo "NO_TASKS: No pending outbox tasks found"
    exit 0
fi

echo "PENDING_TASKS: ${TASK_COUNT}"
echo "---"

# List each task with key frontmatter fields
for task_file in "$OUTBOX_DIR"/OBX-*.md; do
    [ -f "$task_file" ] || continue

    filename=$(basename "$task_file")

    # Extract frontmatter fields using grep (portable, no yq dependency)
    id=$(grep -m1 '^id:' "$task_file" | sed 's/^id: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || echo "unknown")
    task_type=$(grep -m1 '^task_type:' "$task_file" | sed 's/^task_type: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || echo "unknown")
    priority=$(grep -m1 '^priority:' "$task_file" | sed 's/^priority: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || echo "normal")
    created=$(grep -m1 '^created:' "$task_file" | sed 's/^created: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || echo "unknown")
    commissioner=$(grep -m1 '^commissioner:' "$task_file" | sed 's/^commissioner: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' || echo "unknown")

    # Extract task title from first markdown heading
    title=$(grep -m1 '^# Task:' "$task_file" | sed 's/^# Task: *//' || echo "No title")

    echo "FILE: ${filename}"
    echo "  ID: ${id}"
    echo "  TYPE: ${task_type}"
    echo "  PRIORITY: ${priority}"
    echo "  CREATED: ${created}"
    echo "  COMMISSIONER: ${commissioner}"
    echo "  TITLE: ${title}"
    echo "---"
done

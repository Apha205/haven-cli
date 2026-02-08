#!/bin/bash

# =============================================================================
# Haven TUI Sprint Orchestration Script
# =============================================================================
# This script orchestrates the sequential execution of all sprint tasks
# using kimi CLI. Each task runs in its own isolated context.
#
# Usage: ./run_sprints.sh [OPTIONS] [start_from_task]
#
# Run this script from the parent directory (haven-cli/), not from sprints/.
#
# Options:
#   --foundation, -f      Run only Sprint 1: Foundation (tasks 1-3)
#   --dry-run, -d         Preview tasks without running kimi
#   --list, -l            List all tasks
#   --help, -h            Show this help message
#
# Arguments:
#   start_from_task       Optional: Start from a specific task number (1-28)
#
# Progress is tracked in SPRINT_PROGRESS.md
# =============================================================================

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRESS_FILE="${SCRIPT_DIR}/SPRINT_PROGRESS.md"
SPRINTS_DIR="${SCRIPT_DIR}/sprints"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Global variables
START_TASK_ARG=""

# =============================================================================
# Task Definitions (in sequential order)
# Format: sprint_dir:task_file:task_name:is_optional
# =============================================================================

# Task definitions - now using individual task files in tasks/ subdirectories
declare -a ALL_TASKS=(
    # Sprint 1: Foundation (Tasks 1-6)
    "sprint-01-foundation:tasks/task-01-setup-haven-tui-package.md:Setup Haven TUI Package:false"
    "sprint-01-foundation:tasks/task-02-pipeline-interface.md:Pipeline Interface:false"
    "sprint-01-foundation:tasks/task-03-state-manager.md:State Manager:false"
    "sprint-01-foundation:tasks/task-04-metrics-collector.md:Metrics Collector:false"
    "sprint-01-foundation:tasks/task-05-unified-downloads-and-retry.md:Unified Downloads and Retry:false"
    "sprint-01-foundation:tasks/task-06-integration-testing.md:Integration Testing:false"
    
    # Sprint 2: Core Architecture (Tasks 4-8)
    "sprint-02-architecture:tasks/task-2.1-project-setup-dependencies.md:Project Setup and Dependencies:false"
    "sprint-02-architecture:tasks/task-2.2-configuration-system.md:Configuration System:false"
    "sprint-02-architecture:tasks/task-2.3-data-access-layer.md:Data Access Layer (Repository Pattern):false"
    "sprint-02-architecture:tasks/task-2.4-event-consumer.md:Event Consumer / Real-time Updates:false"
    "sprint-02-architecture:tasks/task-2.5-refresh-strategy.md:Refresh Strategy / Data Sync:false"
    
    # Sprint 3: Pipeline Visualization (Tasks 9-12)
    "sprint-03-pipeline-viz:tasks/task-3.1-main-video-list-view.md:Main Video List View:false"
    "sprint-03-pipeline-viz:tasks/task-3.2-stage-specific-progress-indicators.md:Stage-Specific Progress Indicators:false"
    "sprint-03-pipeline-viz:tasks/task-3.3-speed-graph-component.md:Speed Graph Component:false"
    "sprint-03-pipeline-viz:tasks/task-3.4-video-detail-view.md:Video Detail View:false"
    
    # Sprint 4: Data Layer (Tasks 13-16)
    "sprint-04-data-layer:tasks/task-4.1-unified-download-progress-interface.md:Unified Download Progress Interface:false"
    "sprint-04-data-layer:tasks/task-4.2-integrate-youtube-plugin.md:YouTube Plugin Integration:false"
    "sprint-04-data-layer:tasks/task-4.3-integrate-bittorrent-plugin.md:BitTorrent Plugin Integration:false"
    "sprint-04-data-layer:tasks/task-4.4-download-speed-aggregator.md:Download Speed Aggregator:false"
    
    # Sprint 5: TUI Components (Tasks 17-20)
    "sprint-05-tui-components:tasks/task-5.1-layout-system.md:Layout System:false"
    "sprint-05-tui-components:tasks/task-5.2-header-component.md:Header Component:false"
    "sprint-05-tui-components:tasks/task-5.3-footer-status-bar.md:Footer/Status Bar:false"
    "sprint-05-tui-components:tasks/task-5.4-right-pane-speed-graph.md:Right Pane (Speed Graph):false"
    
    # Sprint 6: Advanced Features (Tasks 21-25)
    "sprint-06-advanced-features:tasks/task-6.1-filter-search-system.md:Filter and Search System:false"
    "sprint-06-advanced-features:tasks/task-6.2-sorting-options.md:Sorting Options:false"
    "sprint-06-advanced-features:tasks/task-6.3-batch-operations.md:Batch Operations:true"
    "sprint-06-advanced-features:tasks/task-6.4-pipeline-analytics-dashboard.md:Pipeline Analytics Dashboard:true"
    "sprint-06-advanced-features:tasks/task-6.5-event-log-view.md:Event Log View:false"
    
    # Sprint 7: Polish & Release (Tasks 26-29)
    "sprint-07-polish-release:tasks/task-7.1-testing-qa.md:Testing and QA:false"
    "sprint-07-polish-release:tasks/task-7.2-documentation.md:Documentation:false"
    "sprint-07-polish-release:tasks/task-7.3-packaging.md:Packaging:false"
    "sprint-07-polish-release:tasks/task-7.4-release.md:Release:false"
)

# Foundation sprint only (tasks 1-6)
declare -a FOUNDATION_TASKS=(
    "sprint-01-foundation:tasks/task-01-setup-haven-tui-package.md:Setup Haven TUI Package:false"
    "sprint-01-foundation:tasks/task-02-pipeline-interface.md:Pipeline Interface:false"
    "sprint-01-foundation:tasks/task-03-state-manager.md:State Manager:false"
    "sprint-01-foundation:tasks/task-04-metrics-collector.md:Metrics Collector:false"
    "sprint-01-foundation:tasks/task-05-unified-downloads-and-retry.md:Unified Downloads and Retry:false"
    "sprint-01-foundation:tasks/task-06-integration-testing.md:Integration Testing:false"
)

# Default to all tasks
TASKS=("${ALL_TASKS[@]}")
TOTAL_TASKS=${#TASKS[@]}

# Flag for foundation-only mode
RUN_FOUNDATION_ONLY=false

# =============================================================================
# Utility Functions
# =============================================================================

print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║  $1"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# =============================================================================
# Progress File Management
# =============================================================================

init_progress() {
    if [ ! -f "$PROGRESS_FILE" ]; then
        local start_time=$(date '+%Y-%m-%d %H:%M:%S')
        cat > "$PROGRESS_FILE" << EOF
# Haven TUI Sprint Progress

This file tracks the progress of all sprint tasks.

## Overall Progress

- **Started**: ${start_time}
- **Current Task**: 0 / ${TOTAL_TASKS}
- **Completed**: 0 / ${TOTAL_TASKS}
- **Status**: Not Started

## Task Status

| # | Sprint | Task | Status | Completed At | Optional |
|---|--------|------|--------|--------------|----------|
EOF
        print_info "Created new progress file: $PROGRESS_FILE"
    fi
}

update_progress() {
    local task_num=$1
    local status=$2
    local sprint=$3
    local task_name=$4
    local is_optional=$5
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Update overall progress
    sed -i "s/Current Task: [0-9]*/Current Task: ${task_num} \/ ${TOTAL_TASKS}/" "$PROGRESS_FILE"
    
    if [ "$status" = "Complete" ]; then
        local completed_count=$(grep -c "| Complete |" "$PROGRESS_FILE" 2>/dev/null)
        completed_count=$((completed_count + 1))
        sed -i "s/Completed: [0-9]*/Completed: ${completed_count} \/ ${TOTAL_TASKS}/" "$PROGRESS_FILE"
    fi
    
    if [ "$task_num" -eq "$TOTAL_TASKS" ] && [ "$status" = "Complete" ]; then
        sed -i "s/Status: .*/Status: Complete/" "$PROGRESS_FILE"
    elif [ "$task_num" -gt 0 ]; then
        sed -i "s/Status: .*/Status: In Progress/" "$PROGRESS_FILE"
    fi
    
    # Add or update task row
    local row="| ${task_num} | ${sprint} | ${task_name} | ${status} | ${timestamp} | ${is_optional} |"
    
    if grep -q "| ${task_num} |" "$PROGRESS_FILE"; then
        # Update existing row
        sed -i "s/| ${task_num} |.*/${row}/" "$PROGRESS_FILE"
    else
        # Append new row
        echo "$row" >> "$PROGRESS_FILE"
    fi
}

mark_in_progress() {
    local task_num=$1
    local sprint=$2
    local task_name=$3
    local is_optional=$4
    update_progress "$task_num" "In Progress" "$sprint" "$task_name" "$is_optional"
}

mark_complete() {
    local task_num=$1
    local sprint=$2
    local task_name=$3
    local is_optional=$4
    update_progress "$task_num" "Complete" "$sprint" "$task_name" "$is_optional"
}

mark_failed() {
    local task_num=$1
    local sprint=$2
    local task_name=$3
    local is_optional=$4
    update_progress "$task_num" "Failed" "$sprint" "$task_name" "$is_optional"
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_kimi() {
    if ! command -v kimi &> /dev/null; then
        print_error "kimi CLI is not installed or not in PATH"
        echo "Please install kimi CLI first:"
        echo "  uv tool install kimi-cli"
        exit 1
    fi
    print_success "kimi CLI found"
}

check_sprints_directory() {
    if [ ! -d "$SPRINTS_DIR" ]; then
        print_error "Sprints directory not found: $SPRINTS_DIR"
        echo "Please run this script from the parent directory (haven-cli/)"
        echo "Current directory: $(pwd)"
        exit 1
    fi
    print_success "Sprints directory found: $SPRINTS_DIR"
}

# =============================================================================
# Task Execution
# =============================================================================

run_task() {
    local task_num=$1
    local sprint_dir=$2
    local task_file=$3
    local task_name=$4
    local is_optional=$5
    
    local task_path="${SPRINTS_DIR}/${sprint_dir}/${task_file}"
    
    # Extract sprint name for display
    local sprint_name=$(echo "$sprint_dir" | sed 's/sprint-//' | tr '-' ' ' | awk '{for(i=1;i<=NF;i++)sub(toupper(substr($i,1,1)),substr($i,1,1));print}')
    
    print_header "Task ${task_num} of ${TOTAL_TASKS}: ${task_name}"
    print_info "Sprint: ${sprint_name}"
    
    if [ "$is_optional" = "true" ]; then
        print_warning "This is an OPTIONAL task"
    fi
    
    print_info "Task File: ${task_path}"
    
    # Verify task file exists
    if [ ! -f "$task_path" ]; then
        print_error "Task file not found: $task_path"
        mark_failed "$task_num" "$sprint_name" "$task_name" "$is_optional"
        return 1
    fi
    
    # Mark as in progress
    mark_in_progress "$task_num" "$sprint_name" "$task_name" "$is_optional"
    
    print_info "Launching kimi --yolo for this task"
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  The following prompt will be sent to kimi --yolo${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # Read and display the task file
    cat "$task_path"
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # Define completion marker file
    local completion_marker="${SCRIPT_DIR}/.task_${task_num}_complete"
    rm -f "$completion_marker"
    
    # Prepare the prompt
    local temp_prompt=$(mktemp)
    
    cat > "$temp_prompt" << EOF
CONTEXT: Haven TUI Development Task

You are working on the Haven TUI project. This is task ${task_num} of ${TOTAL_TASKS}.
Sprint: ${sprint_name}
Task: ${task_name}

Task File: ${task_path}

$(cat "$task_path")

IMPORTANT INSTRUCTIONS:

1. This is a SEQUENTIAL task - complete it fully before the next task begins.
2. Check SPRINT_PROGRESS.md for completed work context.
3. Check the existing codebase for current implementation.
4. Run tests after implementation to verify your changes.
5. Update any relevant documentation.
6. Update SPRINT_PROGRESS.md to mark this task as complete.

CRITICAL - TASK COMPLETION SIGNAL:

When you have FULLY completed this task, including all tests and documentation updates,
you MUST create a completion marker file to signal that the orchestrator can proceed.

Run this EXACT command to signal completion:

    touch ${completion_marker}

IMPORTANT: Do NOT create this file until you are TRULY done with ALL acceptance criteria.
Do NOT exit until you have created this file. The orchestrator cannot continue without this signal.

Begin working on this task now.
EOF

    # Run kimi with the task prompt
    local marker_filename=$(basename "$completion_marker")
    print_info "Starting kimi --yolo session"
    print_info "Task will signal completion by creating: ${marker_filename}"
    echo ""
    
    # Read the prompt content
    local prompt_content
    prompt_content=$(cat "$temp_prompt")
    
    # Run kimi in yolo mode with the prompt
    kimi --yolo -p "$prompt_content" &
    local kimi_pid=$!
    
    # Wait for the completion marker file to appear
    print_info "Waiting for task completion signal..."
    local wait_start=$(date +%s)
    local timeout=3600  # 1 hour timeout
    local spin_idx=0
    local spinner=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    
    while [ ! -f "$completion_marker" ]; do
        # Check if kimi process is still running
        if ! kill -0 $kimi_pid 2>/dev/null; then
            # Process ended but no marker file - task failed
            wait $kimi_pid
            local exit_code=$?
            print_error "kimi process exited without creating completion marker (exit code: $exit_code)"
            rm -f "$temp_prompt"
            return 1
        fi
        
        # Check for timeout
        local now=$(date +%s)
        local elapsed=$((now - wait_start))
        if [ $elapsed -gt $timeout ]; then
            print_error "Timeout waiting for task completion (${timeout}s)"
            kill $kimi_pid 2>/dev/null || true
            rm -f "$temp_prompt"
            return 1
        fi
        
        # Show spinner with elapsed time
        printf "\r%s Waiting... %02d:%02d" "${spinner[$spin_idx]}" $((elapsed / 60)) $((elapsed % 60))
        spin_idx=$(((spin_idx + 1) % 10))
        
        sleep 1
    done
    
    # Clear the spinner line
    printf "\r%-50s\r" ""
    
    # Wait for kimi process to fully exit
    wait $kimi_pid 2>/dev/null || true
    local exit_code=$?
    
    # Clean up completion marker
    rm -f "$completion_marker"
    
    if [ $exit_code -eq 0 ]; then
        echo ""
        print_success "Task ${task_num} completed successfully"
        mark_complete "$task_num" "$sprint_name" "$task_name" "$is_optional"
        rm -f "$temp_prompt"
        return 0
    else
        echo ""
        print_error "Task ${task_num} failed or was interrupted (exit code: $exit_code)"
        mark_failed "$task_num" "$sprint_name" "$task_name" "$is_optional"
        rm -f "$temp_prompt"
        return 1
    fi
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    print_header "Haven TUI Sprint Orchestrator"
    print_info "Total Tasks: ${TOTAL_TASKS}"
    print_info "Progress File: ${PROGRESS_FILE}"
    print_info "Sprints Directory: ${SPRINTS_DIR}"
    
    # Check prerequisites
    check_kimi
    check_sprints_directory
    
    # Initialize progress tracking
    init_progress
    
    # Determine starting task
    local start_task=1
    local task_arg="${START_TASK_ARG:-1}"
    
    # Check if running foundation only
    if [ "$RUN_FOUNDATION_ONLY" = true ]; then
        print_info "Running foundation sprint only (tasks 1-3)"
        print_info "Total tasks to execute: ${TOTAL_TASKS}"
        task_arg="1"  # Force start from task 1
    elif [ -n "$task_arg" ]; then
        if [[ "$task_arg" =~ ^[0-9]+$ ]] && [ "$task_arg" -ge 1 ] && [ "$task_arg" -le "$TOTAL_TASKS" ]; then
            start_task=$task_arg
            print_info "Starting from task ${start_task}"
        else
            print_error "Invalid task number: $task_arg (must be 1-${TOTAL_TASKS}) for current mode"
            exit 1
        fi
    fi
    
    # Process tasks sequentially
    local current_task=$start_task
    
    while [ $current_task -le $TOTAL_TASKS ]; do
        # Parse task info
        IFS=':' read -r sprint_dir task_file task_name is_optional <<< "${TASKS[$((current_task - 1))]}"
        
        echo ""
        print_header "Starting Task ${current_task} of ${TOTAL_TASKS}"
        
        # Run the task
        if run_task "$current_task" "$sprint_dir" "$task_file" "$task_name" "$is_optional"; then
            print_success "Task ${current_task} completed - moving to next task"
        else
            print_error "Task ${current_task} failed"
            echo ""
            print_warning "Task failed - continuing to next task in 5 seconds"
            print_info "To stop execution, press Ctrl+C"
            sleep 5
        fi
        
        current_task=$((current_task + 1))
        
        # Brief pause between tasks (except after the last one)
        if [ $current_task -le $TOTAL_TASKS ]; then
            echo ""
            echo -e "${CYAN}"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "   Task complete. Preparing for next..."
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo -e "${NC}"
            echo ""
            print_info "Auto-continuing to task ${current_task} in 3 seconds..."
            print_info "Press Ctrl+C to stop execution"
            sleep 3
        fi
    done
    
    # All tasks complete
    echo ""
    print_header "ALL SPRINTS COMPLETE"
    print_success "All ${TOTAL_TASKS} tasks have been completed"
    print_info "Progress tracked in: ${PROGRESS_FILE}"
    
    # Update final status
    sed -i "s/Status: .*/Status: Complete/" "$PROGRESS_FILE"
    sed -i "s/Completed: [0-9]*/Completed: ${TOTAL_TASKS} \/ ${TOTAL_TASKS}/" "$PROGRESS_FILE"
}

# =============================================================================
# Command Handlers
# =============================================================================

show_help() {
    cat << EOF
Haven TUI Sprint Orchestration Script

This script orchestrates the sequential execution of all sprint tasks
using kimi CLI with --yolo mode. Each task runs in its own isolated context.

IMPORTANT: Run this script from the parent directory (haven-cli/), not from sprints/.

USAGE:
    ./run_sprints.sh [OPTIONS] [START_TASK]

OPTIONS:
    --foundation, -f      Run only Sprint 1: Foundation (tasks 1-3)
    --dry-run, -d         Preview all tasks without running kimi
    --list, -l            List all tasks with their status
    --help, -h            Show this help message

ARGUMENTS:
    START_TASK        Optional: Start from a specific task number
                        (Ignored when using --foundation)

EXAMPLES:
    ./run_sprints.sh                  # Run all tasks from the beginning
    ./run_sprints.sh --foundation     # Run only foundation sprint (tasks 1-3)
    ./run_sprints.sh 5                # Start from task 5
    ./run_sprints.sh --dry-run        # Preview all tasks
    ./run_sprints.sh --list           # List all tasks

PROGRESS TRACKING:
    Progress is saved to SPRINT_PROGRESS.md in the current directory.

TASK STRUCTURE (using individual task files):
    Sprint 1: Foundation (Tasks 1-3)
    Sprint 2: Core Architecture (Tasks 4-8)
    Sprint 3: Pipeline Visualization (Tasks 9-12)
    Sprint 4: Data Layer (Tasks 13-16)
    Sprint 5: TUI Components (Tasks 17-20)
    Sprint 6: Advanced Features (Tasks 21-25)
    Sprint 7: Polish & Release (Tasks 26-29)

DIRECTORY STRUCTURE:
    sprints/
    ├── sprint-01-foundation/
    │   └── tasks/
    │       ├── task-1.1-pipeline-core-interface.md
    │       ├── task-1.2-real-time-state-manager.md
    │       └── task-1.3-speed-history-metrics.md
    ├── sprint-02-architecture/
    │   └── tasks/
    │       ├── task-2.1-project-setup-dependencies.md
    │       └── ...
    └── ...
EOF
}

list_tasks() {
    echo ""
    print_header "Haven TUI Sprint Tasks"
    printf "%-4s %-30s %-35s %-15s %-10s\n" "#" "Sprint" "Task" "Status" "Optional"
    echo ""
    printf '%.0s─' {1..100}; echo ""
    
    local i=1
    for task_info in "${TASKS[@]}"; do
        IFS=':' read -r sprint_dir task_file task_name is_optional <<< "$task_info"
        local sprint_name=$(echo "$sprint_dir" | sed 's/sprint-//' | tr '-' ' ' | awk '{for(i=1;i<=NF;i++)$i=toupper(substr($i,1,1))substr($i,2);print}')
        
        # Check if task is in progress file
        local status="Pending"
        if [ -f "$PROGRESS_FILE" ] && grep -q "| $i |" "$PROGRESS_FILE" 2>/dev/null; then
            if grep "| $i |" "$PROGRESS_FILE" | grep -q "Complete"; then
                status="Complete"
            elif grep "| $i |" "$PROGRESS_FILE" | grep -q "In Progress"; then
                status="In Progress"
            elif grep "| $i |" "$PROGRESS_FILE" | grep -q "Failed"; then
                status="Failed"
            fi
        fi
        
        local optional_flag=""
        [ "$is_optional" = "true" ] && optional_flag="Yes"
        
        printf "%-4s %-30s %-35s %-15s %-10s\n" "$i" "$sprint_name" "$task_name" "$status" "$optional_flag"
        i=$((i + 1))
    done
    echo ""
}

dry_run() {
    echo ""
    print_header "DRY RUN - Task Preview"
    print_info "The following tasks would be executed in order:"
    echo ""
    
    local i=1
    for task_info in "${TASKS[@]}"; do
        IFS=':' read -r sprint_dir task_file task_name is_optional <<< "$task_info"
        local sprint_name=$(echo "$sprint_dir" | sed 's/sprint-//' | tr '-' ' ' | awk '{for(i=1;i<=NF;i++)$i=toupper(substr($i,1,1))substr($i,2);print}')
        local task_path="${SPRINTS_DIR}/${sprint_dir}/${task_file}"
        
        echo -e "${CYAN}Task $i${NC}: ${task_name}"
        echo "   Sprint: ${sprint_name}"
        echo "   File: ${task_path}"
        
        if [ "$is_optional" = "true" ]; then
            echo -e "   ${YELLOW}Optional: Yes${NC}"
        fi
        
        if [ -f "$task_path" ]; then
            # Extract acceptance criteria or first few lines
            echo "   Preview:"
            head -n 5 "$task_path" | sed 's/^/      /'
            echo ""
        else
            echo -e "   ${RED}  File not found${NC}"
        fi
        echo ""
        
        i=$((i + 1))
    done
    
    print_success "Dry run complete - ${TOTAL_TASKS} tasks would be executed"
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --list|-l)
                init_progress 2>/dev/null || true
                list_tasks
                exit 0
                ;;
            --dry-run|-d)
                dry_run
                exit 0
                ;;
            --foundation|-f)
                RUN_FOUNDATION_ONLY=true
                TASKS=("${FOUNDATION_TASKS[@]}")
                TOTAL_TASKS=${#TASKS[@]}
                shift
                ;;
            [0-9]*)
                START_TASK_ARG="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# =============================================================================
# Signal Handlers
# =============================================================================

trap 'echo ""; print_warning "Interrupted by user"; exit 0' INT TERM

# =============================================================================
# Entry Point
# =============================================================================

# Parse arguments first
parse_args "$@"

# Run main function
main

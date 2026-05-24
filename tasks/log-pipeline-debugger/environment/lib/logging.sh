#!/bin/bash
# Logging helper functions

LOG_LEVEL="${LOG_LEVEL:-INFO}"

log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $*" >&2; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $*" >&2; }
log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo "[DEBUG] $(date '+%H:%M:%S') $*" >&2
}

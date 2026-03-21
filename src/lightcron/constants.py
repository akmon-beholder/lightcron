"""Shared timing and threshold constants for Lightcron.

All numeric constants used by the scheduler and worker agent are defined here.
Do NOT hardcode these values elsewhere — always import from this module.

Future: these may be overridable via a DB configuration table.
"""

# Scheduler background loops
READY_TRANSITION_INTERVAL_SECONDS: int = 10
"""How often the scheduler checks pending → ready transitions."""

HEALTH_CHECK_INTERVAL_SECONDS: int = 30
"""How often the scheduler checks worker liveness."""

# Worker agent loops
CLAIM_POLL_INTERVAL_SECONDS: int = 5
"""How often a worker agent polls for ready jobs to claim."""

JOB_STATUS_POLL_INTERVAL_SECONDS: int = 5
"""How often a worker agent checks for cancel/lost status on running jobs."""

LAST_SEEN_UPDATE_INTERVAL_SECONDS: int = 30
"""How often a worker agent updates worker_status.last_seen."""

# Worker liveness thresholds
WORKER_HEALTH_PROBE_THRESHOLD_SECONDS: int = 60
"""Stage 1: call GET /health on worker if last_seen is this stale."""

WORKER_OFFLINE_THRESHOLD_SECONDS: int = 90
"""Stage 2: mark worker offline + jobs lost if last_seen exceeds this age."""

# Process lifecycle
SIGTERM_GRACE_PERIOD_SECONDS: int = 30
"""Seconds to wait after SIGTERM before sending SIGKILL."""

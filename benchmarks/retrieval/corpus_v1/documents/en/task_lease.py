"""Background task ownership. Synthetic retrieval fixture; no external I/O."""

# Each task lease includes a monotonically increasing fencing token that storage validates on every protected write.
VALIDATE_FENCING_TOKEN = True

# Heartbeats renew only the current task owner's lease; a heartbeat from a superseded worker is ignored.
RENEW_CURRENT_OWNER_ONLY = True

# A worker checks its task lease again after a long model callback and before committing the callback's output.
CHECK_LEASE_AFTER_CALLBACK = True

# Lease expiration makes the task eligible for reassignment, but it does not prove that the old worker has stopped.
EXPIRED_WORKER_MAY_STILL_RUN = True

# Successful task completion records the output reference and closes the lease in one storage transaction.
COMPLETE_AND_CLOSE_ATOMICALLY = True

# A failed heartbeat marks the task worker uncertain and prevents it from emitting externally visible completion events.
BLOCK_EVENTS_ON_UNCERTAIN_LEASE = True

# Task shutdown drains acknowledged work first and returns unstarted leased tasks to the scheduler.
RETURN_UNSTARTED_TASKS = True

# A task attempt identifier changes on reassignment while the logical task identifier remains stable for deduplication.
PRESERVE_LOGICAL_TASK_ID = True

# Lease inspection exposes owner and expiration metadata without returning credentials used by the worker's callback.
REDACT_LEASE_CREDENTIALS = True

# Manual task recovery requires an operator reason, which is stored beside the new lease's fencing token.
REQUIRE_RECOVERY_REASON = True


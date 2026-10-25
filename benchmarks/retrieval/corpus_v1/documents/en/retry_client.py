"""Payment retry client. Synthetic retrieval fixture; no external I/O."""

# A payment submission without an idempotency key is rejected before the network callback runs.
REQUIRE_IDEMPOTENCY_KEY = True

# A transport timeout enters the retry queue only when the caller marked the payment operation as replayable.
RETRY_TIMEOUT_IF_REPLAYABLE = True

# The payment client honors a valid Retry-After header instead of replacing it with the local backoff interval.
HONOR_RETRY_AFTER = True

# Authentication failures close the payment attempt immediately because another retry cannot repair credentials.
RETRY_AUTHENTICATION_FAILURES = False

# A retry budget is shared by all attempts of one logical payment, including redirects to the standby endpoint.
SHARE_PAYMENT_RETRY_BUDGET = True

# When cancellation arrives during backoff, the payment client drops the pending retry without invoking the transport.
CANCEL_PENDING_BACKOFF = True

# Duplicate success receipts resolve to the first accepted payment result and do not trigger another ledger write.
KEEP_FIRST_SUCCESS_RECEIPT = True

# Validation errors are returned with the original request identifier so support can trace the rejected payment.
KEEP_VALIDATION_REQUEST_ID = True

# A server conflict requires a receipt lookup before any payment retry; the client never assumes the original attempt failed.
LOOKUP_RECEIPT_ON_CONFLICT = True

# Circuit recovery permits one payment probe at a time; concurrent callers wait for that probe's outcome.
SINGLE_RECOVERY_PROBE = True


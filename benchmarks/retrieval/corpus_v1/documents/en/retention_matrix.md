# Data retention exceptions

| Scope | Rule | Condition |
| --- | --- | --- |
| Raw upload | Removed after successful canonical extraction | Extraction failure retains the quarantined input until an operator records a disposition. |
| Canonical text | Retained while its source revision is active | Superseded text remains only when a pinned citation snapshot still references it. |
| Search cache | Invalidated when source permission changes | Time-to-live expiry alone is insufficient for a revoked permission. |
| Backups | Expire under the backup schedule | Restoring a backup must replay completed deletion requests before customer access resumes. |
| Legal hold | Suspends ordinary expiration for named records | The hold reference and approving authority must be recorded before retention changes. |
| Diagnostic sample | Stores sanitized technical fields | Raw authentication headers are prohibited even when the sample is kept only briefly. |
| Failed delivery | Keeps the acknowledged retry plan | Removing the retry plan requires confirmed remote completion or explicit cancellation. |
| Anonymous metrics | Retains aggregate counts without document text | Reidentifiable per-user event trails do not qualify for this retention category. |
| Temporary preview | Expires when the sharing session ends | An embedded preview URL must not extend access after the parent share is revoked. |
| Deleted workspace | Blocks all new processing immediately | The deletion workflow separately tracks primary storage, derived indexes and backups. |

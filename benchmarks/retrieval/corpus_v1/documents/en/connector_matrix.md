# Source connector consistency

| Scope | Rule | Condition |
| --- | --- | --- |
| Object storage | Listing continuation tokens belong to one scan | A failed page restarts from the saved token and does not mark unseen objects deleted. |
| Source control | File identity includes repository and revision | Identical filenames in separate repositories cannot overwrite each other's indexing state. |
| Shared drive | Permission changes emit metadata-only updates | Unchanged document text does not excuse retaining stale reader permissions. |
| Wiki pages | A move preserves the logical page identifier | The connector updates citation location without unnecessarily recomputing unchanged embeddings. |
| Support tickets | Private notes retain their visibility boundary | Combining public comments and private notes into one universally visible chunk is prohibited. |
| Mail archives | Attachments carry the parent message lineage | Detached attachment text must preserve its source and permission reference. |
| Database rows | Snapshot reads use a recorded transaction boundary | A partially completed incremental scan cannot advance the committed source watermark. |
| Event streams | Consumer progress advances after index acknowledgement | A published but unacknowledged batch stays eligible for replay after restart. |
| Web crawler | Canonical URLs are normalized before identity assignment | Redirect targets remain subject to the source allowlist and robots policy. |
| Calendar source | Cancelled events create explicit removal work | Hiding a cancelled event in the source UI alone cannot remove its stale retrieval vectors. |

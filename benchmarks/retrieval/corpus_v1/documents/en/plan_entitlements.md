# Workspace plan entitlements

| Scope | Rule | Condition |
| --- | --- | --- |
| Starter search | Shared lexical index only | Vector retrieval must be enabled by an administrator after the workspace upgrades. |
| Team exports | Workspace owners may request JSON exports | A suspended member cannot start an export even if an old browser session remains open. |
| Business audit | Audit records retain actor and action metadata | Search query text is excluded from the audit feed unless content logging is explicitly enabled. |
| Enterprise keys | Customer-managed keys require a verified key endpoint | An unreachable endpoint pauses new encrypted writes instead of falling back to a vendor key. |
| Trial connectors | Trial imports stop at the declared source quota | Existing indexed documents remain readable after the trial import quota is reached. |
| Education guests | Invited guests read explicitly shared collections | Guest membership never grants workspace-wide collection discovery. |
| Enterprise regions | Region changes create a reviewed migration request | Region selection in the UI alone does not move persisted customer data. |
| Business billing | Billing administrators see invoices and payment state | Billing privileges do not grant access to the underlying document contents. |
| Team restoration | Deleted collections use the documented restoration window | A legal deletion request bypasses ordinary collection restoration availability. |
| Enterprise support | Support access is time-bounded and customer-approved | Support entitlement does not authorize staff to browse collections without approval. |

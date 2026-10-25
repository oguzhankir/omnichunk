# Embedding model rollout

An embedding model rollout builds a separate index generation; it does not mix new model vectors with the active generation's old vectors.

The rollout manifest records model revision, tokenizer revision and preprocessing digest so identical vector dimensions cannot disguise incompatible embeddings.

The evaluation set is frozen before model tuning and includes deletion, multilingual and ambiguous-query cases alongside ordinary answer retrieval.

A shadow query sends traffic to both generations for measurement while only the current generation supplies customer answers.

The model rollout compares relevant-source recall at a fixed retrieved token budget to avoid rewarding a candidate that simply returns longer context.

A rollout candidate with lower average latency can still be rejected when its tail latency makes interactive queries miss the declared deadline.

The cutover record names both the new generation and the prior generation retained for rollback, with the validation report linked.

If the embedding provider changes model behavior without a revision update, the rollout pauses and invalidates the reproducibility assumption.

A source deletion observed during model rollout is applied to both the active and candidate generations before either can serve that source again.

After the observation window, the owner removes the old generation only after confirming no worker or query router still references it.


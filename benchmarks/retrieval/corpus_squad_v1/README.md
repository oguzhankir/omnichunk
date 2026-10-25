# SQuAD 1.1 retrieval subset

This independent corpus retains unmodified paragraphs, questions and answer
annotations from the Stanford Question Answering Dataset (SQuAD) 1.1. Attribution:
Pranav Rajpurkar, Jian Zhang, Konstantin Lopyrev and Percy Liang, and the Wikipedia
contributors identified by each document's article title and attribution URL.
See [LICENSE](LICENSE) for CC BY-SA 4.0 attribution and ShareAlike terms. These
terms apply to this corpus separately from the OmniChunk software license.

The frozen source `dev-v1.1.json` has SHA256
`95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9`.
The importer selects 16 articles, two paragraphs per article and three questions
per paragraph in SHA256 order. It uses no chunker output or retrieval scores for
selection. Normalized duplicate paragraphs and questions are excluded. Eight
articles belong to development and eight to test, giving **32 documents and 96
queries**, with 48 queries in each split. Splits refer to this retrieval experiment;
both originate from the upstream SQuAD development dataset.

Each question uses the first answer annotation that matches its declared character
position. The importer converts that position into an exact half-open UTF-8 byte
span. It preserves original text, adds IDs, hashes, attribution and disjoint splits,
and records these changes and the selection policy in `manifest.json`.
Wikipedia links provide article attribution; the pinned SQuAD file provides the
exact text snapshot, rather than the current live Wikipedia article revision.

Rebuild from a previously downloaded source file into a new directory:

```bash
python benchmarks/import_squad.py --input /path/to/dev-v1.1.json \
  --output /tmp/squad-retrieval
python benchmarks/run_retrieval.py --corpus /tmp/squad-retrieval --split dev \
  --tools omnichunk,fixed --chunk-sizes 128 256 --output /tmp/squad-dev.json
```

The importer performs no network requests and rejects a source checksum mismatch.
It produces the manifest, source documents and license notice; this README is
maintained separately. The complete upstream download URL is in the manifest.

This small English Wikipedia prose sample supplies independently authored labels,
not a representative enterprise workload or a multilingual/code/table comparison.
Answers have not had an additional OmniChunk-specific human review. Select settings
on development data, freeze them, and inspect test once; comparing many settings
on test makes that split another development set.

# Gutenberg Corpus Benchmark

## Overview

Benchmark using NLTK's Gutenberg Corpus:
- 18 public domain books
- ~11.8M characters
- ~3.0M tokens (GPT-4 tokenizer)
- 512-token target chunks

## Run

```bash
python benchmarks/run_gutenberg.py
```

## Notes

- Uses tiktoken GPT-4 for token counting.
- Omnichunk uses token-aware sizing (size_unit="tokens").
- Langchain uses RecursiveCharacterTextSplitter.from_tiktoken_encoder.
- Semantic-text-splitter remains character-based; included for completeness.
- Throughput reported as MBps (megabytes of characters per second).
- Fewer chunks usually indicate better semantic grouping.

## Sample output

| Tool | Texts | Chars | Tokens | Chunks | Seconds | ThroughputMBps | Status | Detail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| omnichunk | 18 | 11793318 | 3001260 | 4562 | 5.260 | 2.138 | ok | |
| langchain_recursive | 18 | 11793318 | 3001260 | 6689 | 7.209 | 1.560 | ok | |
| semantic_text_splitter | 18 | 11793318 | 3001260 | 29807 | 18.870 | 0.596 | ok | |

Interpretation:
- Omnichunk: 4562 chunks, 2.14 MBps throughput
- Langchain: 6689 chunks, 1.56 MBps throughput
- Semantic-text-splitter: 29807 chunks, 0.60 MBps throughput

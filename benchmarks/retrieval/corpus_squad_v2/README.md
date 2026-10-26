# SQuAD article-level structural evaluation v2

This is a frozen, attributed subset of SQuAD 1.1 for source-evidence retrieval,
not an official SQuAD leaderboard. Its questions and answer annotations are
human-authored. Exact short answers have not been independently audited as
complete supporting evidence for downstream answer generation.

The checksum-pinned upstream is
`https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/dataset/dev-v1.1.json`,
SHA-256 `95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9`.
The previous corpus's 16 articles are excluded. Namespace-SHA ordering selected
the remaining 32 articles, three paragraphs per article and three questions per
paragraph without retrieval scores. Sixteen whole articles belong to development
and sixteen to validation: **144 questions per split**. Normalized contexts and
questions do not cross the split or duplicate the earlier corpora.

Each view has one document per article, so source-component bootstrap samples
are whole articles. The `article-text` view concatenates the selected unmodified
paragraphs in original order. `article-markdown` adds the article title as a
heading. Answer UTF-8 byte offsets are rebased exactly. Both views contain the
same questions and paragraphs: they are correlated representations, not twice
as many independent examples. Their manifests preserve original paragraph hashes,
Wikipedia attribution links, upstream question IDs and transformation details.

Directories are `development/{article-text,article-markdown}` with split `dev`
and `validation/{article-text,article-markdown}` with split `test`. Pass the view
directory to `benchmarks/prepare_dense.py` and `benchmarks/run_retrieval.py`.
The [experiment record](../reports/structural-quality-v2/README.md) provides the
frozen source/model/configuration, commands, full reports and limitations.

Validation was encrypted before development scores were inspected and released
only after the final source/model/configuration freeze and review. Custody was
within the same agent workspace, not an independent external custodian. These
now-published validation outcomes must not be treated as an unseen future test.
Article separation does not establish novelty relative to model pretraining.

Source text and reproduced source passages retain **CC-BY-SA-4.0** licensing and
attribution to Wikipedia contributors and SQuAD authors Pranav Rajpurkar, Jian
Zhang, Konstantin Lopyrev and Percy Liang. See each manifest's provenance and
document attribution. Software for importing and evaluating the data remains
MIT-licensed. No model weights or private validation key are distributed here.

<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Proposal: Semantic Aggregation Candidate Recommendation

## Purpose

This proposal introduces a semantic recommendation mechanism for determining which existing aggregation is the most appropriate candidate for a newly ingested record.

The system will maintain a continuously updated semantic profile for each aggregation. That profile will be derived from the aggregation’s metadata, the metadata of its descendants, and the textual or visual content of descendant records. When a new record is added, the system will compare the record’s embedding with the profiles of eligible aggregations and present the most similar aggregation to the user for acceptance or rejection.

The system will recommend an aggregation; it will not make an irreversible filing decision automatically.

## Core concept

An aggregation’s semantic profile represents the observed character of the aggregation as a whole.

```text
Aggregation profile =
    aggregation metadata
  + descendant metadata
  + descendant record content
```

The profile is intentionally dynamic. As descendants are added, updated, or removed, the profile changes. This change is desirable because the descendants constitute the aggregation’s practical identity.

For example, an aggregation that contains predominantly invoices will gradually develop a profile associated with:

- Invoice terminology.
- Particular suppliers.
- Account or project references.
- Currency and tax language.
- Product or service descriptions.
- Recurring document templates.
- Relevant dates and periods.

A new invoice containing similar characteristics should therefore become a strong candidate for that aggregation.

## User interaction

When a new record is ingested, the system will:

1. Extract metadata from the record.
2. Extract native text where available.
3. Perform OCR or visual analysis when necessary.
4. Generate an embedding representing the record.
5. Retrieve semantically similar eligible aggregations.
6. Rank the candidate aggregations.
7. Present the leading candidate and confidence information to the user.
8. Allow the user to accept, reject, or select another aggregation.
9. Store the user’s decision for auditing and future evaluation.

The user interface might present:

```text
Suggested aggregation:
Acme Corporation — Invoices — 2024

Confidence:
High — 87%

Why this was suggested:
- Similar supplier and invoice terminology.
- Similar project reference.
- Aggregation contains 31 accepted invoice records.
- No classification or security-rule conflicts detected.

[Accept] [Reject] [Choose another]
```


## Processing model

The process consists of two independent asynchronous activities:

```text
Aggregation profile maintenance
    and
New-record candidate recommendation
```


### Aggregation profile maintenance

An aggregation profile is refreshed when:

- The aggregation is created.
- Aggregation metadata changes.
- A child aggregation is created, updated, or removed.
- A child record is added, updated, or removed.
- A descendant’s metadata changes.
- A descendant’s extracted text or OCR result changes.
- The embedding model or embedding configuration changes.

These changes should enqueue an asynchronous profile-refresh job rather than blocking the user’s transaction.

### New-record recommendation

When a new record is received:

```text
record ingestion
  → metadata extraction
  → native text extraction or OCR
  → record embedding generation
  → eligible aggregation search
  → candidate ranking
  → confidence calculation
  → user recommendation
```

The recommendation can be generated before the record is finally assigned to an aggregation.

## Document processing

The system should first attempt native text extraction for digitally generated documents.

```text
PDF with text layer → native PDF extraction
DOCX                 → DOCX parser
Email                → MIME/email parser
Spreadsheet           → spreadsheet parser
HTML                  → HTML parser
```

If native extraction produces insufficient text, the system should use OCR or visual document processing.

```text
scanned PDF/image
  → OCR or vision-language model
  → extracted text and/or visual features
```

The resulting content can then be used to generate the record embedding.

The system should retain the extraction method:

```json
{
  "text_extraction_method": "native",
  "ocr_engine": null
}
```

or:

```json
{
  "text_extraction_method": "ocr",
  "ocr_engine": "paddleocr"
}
```

This makes the semantic recommendation process auditable.

## Embedding inputs

The aggregation profile should be generated from a deterministic semantic projection rather than an uncontrolled concatenation of every descendant.

### Aggregation metadata

Possible inputs include:

```text
- Aggregation title.
- Aggregation description.
- Aggregation type.
- Classification or business category.
- Organizational unit.
- Parties.
- Project, case, or matter identifiers.
- Date range.
- Reference numbers.
- Declared keywords.
```


### Descendant metadata

Possible inputs include:

```text
- Descendant type.
- Descendant title.
- Descendant classification.
- Parties.
- Dates.
- Reference numbers.
- Workflow state.
- Selected metadata fields.
```


### Descendant content

Possible inputs include:

```text
- Extracted record text.
- OCR text.
- Generated record title.
- Generated short summary.
- Important headings.
- Distinctive named entities.
- Selected content excerpts.
```

The content projection should be bounded and reproducible. The system should not create an unbounded prompt containing the entire history of a large aggregation.

## Aggregation profile representation

The simplest implementation stores one current embedding per aggregation:

```text
aggregation
    └── current semantic profile
```

A more complete implementation can maintain:

```text
- Aggregation profile embedding.
- Profile version.
- Embedding model name.
- Embedding model version.
- Source content hash.
- Descendant count.
- Last refresh timestamp.
- Profile generation status.
```

Example table:

```sql
CREATE TABLE aggregation_embedding (
    aggregation_id       bigint PRIMARY KEY
        REFERENCES aggregation(id),

    model_name            text NOT NULL,
    model_version         text NOT NULL,

    embedding             vector(1024) NOT NULL,

    profile_version       bigint NOT NULL,
    source_hash           text NOT NULL,
    descendant_count      integer NOT NULL DEFAULT 0,

    generated_at          timestamptz NOT NULL DEFAULT now()
);
```

The vector dimension must match the selected embedding model.

## Profile generation strategies

### Full recomputation

The system gathers the current aggregation metadata and descendant content, generates the profile input, and creates a new embedding.

```text
profile = embed(current aggregation projection)
```

Advantages:

- Simple conceptual behavior.
- Easy to reproduce.
- Correct after additions, removals, and content changes.

Disadvantages:

- Potentially expensive for large aggregations.
- Requires reading many descendants.
- May require batching or summarization.


### Incremental profile

The system maintains a weighted aggregate of descendant embeddings.

```text
profile =
    normalize(
        aggregation_embedding
        + sum(weight_i × descendant_embedding_i)
    )
```

When a descendant is added, its contribution is added to the profile. When it is updated or removed, the previous contribution can be subtracted if it has been retained.

Advantages:

- Efficient for frequent changes.
- Avoids repeatedly processing all descendants.
- Well suited to large aggregations.

Disadvantages:

- More complex update logic.
- Requires storing previous contributions.
- Must handle embedding-model changes and content corrections.


### Recommended approach

Use both:

```text
incremental refresh for normal changes
periodic full rebuild for correction and consistency
```

A full rebuild should also be triggered when:

- The embedding model changes.
- OCR output is corrected.
- Metadata normalization changes.
- The profile detects a source inconsistency.
- An administrator requests recalculation.


## Weighted descendants

Not all descendants need to contribute equally.

Example weighting:

```text
authoritative record       1.0
normal record              1.0
generated summary          0.8
administrative note        0.5
weak OCR result            0.4
duplicate or superseded    0.1
```

The weights should be configurable and evaluated using real filing decisions.

The profile may be calculated as:

$$
p =
\operatorname{normalize}
\left(
w_a a +
\frac{\sum_{i=1}^{n} w_i e_i}
     {\sum_{i=1}^{n} w_i}
\right)
$$

Where:

- $a$ is the aggregation metadata embedding.
- $e_i$ is a descendant embedding.
- $w_i$ is the descendant’s contribution weight.
- $w_a$ is the aggregation metadata weight.
- $p$ is the resulting profile.

If the intended identity should primarily reflect descendants, descendant weights should dominate the aggregation metadata weight.

## New-record embedding

The new record’s embedding should be generated from the same semantic conventions used for aggregation profiles.

Example input:

```text
Filename:
2024-11-18_acme_invoice_4821.pdf

Record metadata:
Type: Invoice
Supplier: Acme Corporation
Date: 2024-11-18
Reference: INV-4821
Project: ERP Modernization

Content:
Invoice for software implementation and support services...
```

The record should use the same embedding model and compatible preprocessing as the aggregation profiles.

The model name and version must be retained with every embedding. Profiles generated with incompatible models should not be compared directly.

## Candidate retrieval

The system should search only aggregations that are valid candidates for the record.

Potential eligibility conditions include:

```text
- Same tenant.
- User has access.
- Aggregation is active.
- Aggregation accepts new records.
- Record class is compatible.
- Security scope is compatible.
- Date restrictions are satisfied.
- Parent and child rules permit assignment.
- Aggregation is not closed or disposed.
```

Example query:

```sql
SELECT
    a.id,
    a.title,
    1 - (ae.embedding <=> :record_embedding) AS similarity
FROM aggregation_embedding ae
JOIN aggregation a
  ON a.id = ae.aggregation_id
WHERE a.tenant_id = :tenant_id
  AND a.accepts_records = true
  AND a.deleted_at IS NULL
  AND a.record_class_id = :record_class_id
ORDER BY ae.embedding <=> :record_embedding
LIMIT 10;
```

pgvector supports cosine distance with the `<=>` operator, and cosine similarity can be calculated as `1 - distance`. It supports exact nearest-neighbor search as well as approximate indexes such as HNSW and IVFFlat.[^1]

For initial testing, exact search should be preferred because it provides a reliable baseline. An HNSW index can be added later when the number of aggregations requires approximate search for performance. HNSW trades some recall for faster retrieval.[^1]

Example index:

```sql
CREATE INDEX aggregation_embedding_hnsw_idx
ON aggregation_embedding
USING hnsw (embedding vector_cosine_ops);
```


## Ranking and reranking

Vector similarity should be the primary candidate-retrieval signal, but it should not be the only ranking factor.

A composite candidate score may include:

```text
- Semantic similarity.
- Metadata agreement.
- Record-type compatibility.
- Party or supplier match.
- Project, case, or matter match.
- Reference-number match.
- Date compatibility.
- Full-text similarity.
- Hierarchical specificity.
- Historical acceptance behavior.
```

Example:

$$
S =
w_v S_v +
w_m S_m +
w_t S_t +
w_p S_p +
w_h S_h -
w_c P_c
$$

Where:

- $S_v$: embedding similarity.
- $S_m$: metadata agreement.
- $S_t$: lexical or full-text similarity.
- $S_p$: party, project, or reference agreement.
- $S_h$: hierarchy compatibility.
- $P_c$: penalty for business-rule conflicts.

Vector search retrieves candidates; deterministic rules prevent invalid candidates from being recommended.

## Hierarchical aggregations

Where aggregations form a hierarchy, the system should account for specificity.

Possible strategies include:

### Global search

Search all eligible aggregations and choose the highest-ranked candidate.

### Level-by-level search

```text
1. Select a likely top-level aggregation.
2. Search its eligible child aggregations.
3. Continue down the hierarchy.
4. Stop when no child is sufficiently stronger.
```


### Parent-child reranking

Search all candidates, then prefer a child over its parent when the child is a sufficiently good match.

For example:

```text
if child_similarity >= parent_similarity - tolerance:
    prefer the child
```

The selected policy should reflect the filing behavior expected by the ERMS.

## Confidence presentation

The system should not present raw cosine similarity as a probability.

A similarity value such as `0.84` is a geometric score whose interpretation depends on the embedding model and the corpus. It should be transformed into a user-facing confidence level using thresholds calibrated against historical user decisions.

Initial confidence features may include:

```text
- Top candidate similarity.
- Difference between first and second candidate.
- Metadata agreement.
- Number of similar accepted descendants.
- Candidate eligibility.
- Historical acceptance rate.
- Number of descendants supporting the profile.
- Presence of rule conflicts.
```

Example heuristic:

$$
C =
\alpha S_1 +
\beta(S_1 - S_2) +
\gamma M
$$

Where:

- $S_1$ is the top candidate score.
- $S_2$ is the second candidate score.
- $M$ is the metadata agreement score.

The system can initially display:

```text
High confidence
Medium confidence
Low confidence
```

Later, historical decisions can be used to calibrate a more reliable confidence model.

## New and sparsely populated aggregations

An aggregation with no descendants cannot have a meaningful empirical descendant profile.

The system should distinguish between:

```text
Metadata-only profile:
    no descendants

Emerging profile:
    a small number of descendants

Established profile:
    sufficient descendant history
```

This status can influence confidence presentation:

```text
Suggested aggregation:
New Customer Correspondence

Confidence:
Low — profile is based only on aggregation metadata
```

This is not a reason to exclude empty aggregations entirely. They may be valid candidates based on their declared metadata.

## Asynchronous consistency

Profile updates should be eventually consistent.

When a descendant changes:

```text
transaction:
    persist descendant change
    increment aggregation semantic_version
    enqueue profile refresh
commit
```

The background worker then:

1. Reads the latest aggregation version.
2. Builds the profile from the latest valid sources.
3. Generates the embedding.
4. Writes the embedding only if the source version is still current.
5. Retries or schedules another refresh if the aggregation changed during processing.

Example:

```text
profile refresh starts for version 42
descendant is added
aggregation becomes version 43
worker finishes version-42 profile
worker discards or marks it stale
worker refreshes version 43
```

This prevents an older asynchronous result from replacing a newer profile.

Profile-refresh jobs should be coalesced. Ten descendant changes within a short period should normally result in one refresh job rather than ten independent model calls.

## User decisions as feedback

Every recommendation should be retained as an event.

Example schema:

```sql
CREATE TABLE aggregation_suggestion (
    id                         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    record_id                  bigint NOT NULL,
    suggested_aggregation_id   bigint NOT NULL,

    profile_version            bigint NOT NULL,
    embedding_model            text NOT NULL,

    rank                       integer NOT NULL,
    similarity_score           double precision NOT NULL,
    confidence_level           text NOT NULL,

    evidence                   jsonb NOT NULL,

    decision                   text,
    decided_by                 bigint,
    decided_at                 timestamptz,

    created_at                 timestamptz NOT NULL DEFAULT now()
);
```

Possible decisions include:

```text
accepted
rejected
accepted_different_aggregation
dismissed
expired
```

The system can evaluate:

```text
- Top-1 acceptance rate.
- Top-3 acceptance rate.
- Acceptance rate by confidence level.
- Rejection rate by aggregation.
- Rejection rate by record type.
- Similarity-margin effectiveness.
- Performance for new versus established aggregations.
```

User decisions can eventually support a learned reranker or confidence-calibration model.

## Auditability

Because the recommendation may influence records-management behavior, the system should preserve the evidence used to produce it.

An audit record should contain:

```json
{
  "record_id": 9876,
  "suggested_aggregation_id": 1234,
  "profile_version": 18,
  "embedding_model": "embedding-model-name",
  "similarity_score": 0.86,
  "confidence_level": "high",
  "rank": 1,
  "supporting_factors": {
    "record_type_match": true,
    "supplier_match": true,
    "project_match": true,
    "similar_descendant_count": 31
  },
  "decision": "accepted"
}
```

The system should preserve the original record, extracted text, OCR metadata, embedding version, profile version, recommendation, user decision, and final assignment.

## Security and eligibility

Vector search must be performed only over records and aggregations the current user or process is authorized to see.

The search must apply:

```text
- Tenant filtering.
- Access-control filtering.
- Security classification.
- Organizational boundaries.
- Legal holds.
- Lifecycle restrictions.
- Aggregation eligibility.
```

Embeddings can reveal semantic information, so they should be treated as protected derived data. Access to the vector column and vector-search API must follow the same security model as the underlying records.

## Risks and mitigations

### Profile over-generalization

A very large aggregation may represent many different document types.

Mitigation:

```text
- Keep the aggregation profile dynamic.
- Show supporting evidence.
- Use child-level or record-level similarity for reranking.
- Allow users to reject suggestions.
```


### Weak profile for new aggregations

An empty aggregation has no descendant evidence.

Mitigation:

```text
- Use metadata-only profiles.
- Show lower confidence.
- Distinguish emerging and established profiles.
```


### Incompatible embeddings

Profiles generated by different models cannot be reliably compared.

Mitigation:

```text
- Store model name and version.
- Rebuild profiles when the model changes.
- Maintain separate embedding namespaces if necessary.
```


### OCR errors

Incorrect OCR may distort the record profile.

Mitigation:

```text
- Preserve extraction method.
- Store OCR quality information where available.
- Weight uncertain OCR content lower.
- Allow native text to override OCR when present.
```


### Incorrect automatic interpretation

Semantic similarity can identify a plausible candidate but cannot prove filing correctness.

Mitigation:

```text
- Use the system for recommendation.
- Require explicit user acceptance.
- Apply hard eligibility rules before similarity search.
- Preserve the user’s final decision.
```


## Initial implementation

A minimal first version can use:

```text
1. One embedding per eligible aggregation.
2. One embedding per new record.
3. Metadata and authorization filters.
4. Exact pgvector search.
5. Top-five candidate retrieval.
6. Similarity and margin display.
7. User acceptance or rejection.
8. Recommendation-event logging.
9. Asynchronous profile refresh.
```

The first version should not attempt to solve every ranking problem. Its purpose is to generate real user decisions and establish measurable performance.

## Later improvements

After collecting sufficient usage data, the system can add:

```text
- Composite metadata and vector scoring.
- Child-level evidence.
- Learned reranking.
- Calibrated confidence.
- Aggregation-specific thresholds.
- Record-type-specific profiles.
- Duplicate and near-duplicate detection.
- Multilingual embeddings.
- Periodic profile rebuilds.
- Human feedback loops.
```


## Proposed specification statement

> The system shall maintain an asynchronously updated semantic profile for each aggregation. The profile shall be derived from the aggregation’s metadata and the metadata and content of its descendants. When a new record is ingested, the system shall generate a compatible embedding for that record and retrieve eligible aggregations whose semantic profiles are most similar. The system shall present one or more candidate aggregations, together with a confidence level and supporting evidence, for user acceptance or rejection. The system shall not treat semantic similarity as an automatic filing decision. User decisions shall be retained as auditable events and may be used to evaluate and improve candidate ranking and confidence calibration.

## Recommendation

This is a sound design for **human-in-the-loop aggregation recommendation**.

The central principle should be:

```text
The aggregation profile represents the observed totality of its descendants.
```

The profile is therefore expected to evolve as the aggregation evolves. That evolution is not an unwanted side effect; it is the mechanism by which the system learns what kind of records belong in that aggregation.

PostgreSQL with pgvector is a suitable implementation foundation because it allows vector storage, similarity search, relational filtering, joins, and transactionally managed application data in the same database.[^2][^1]

<span style="display:none">[^10][^3][^4][^5][^6][^7][^8][^9]</span>

<div align="center">⁂</div>

[^1]: https://github.com/pgvector/pgvector

[^2]: https://machinelearningmastery.com/building-vector-similarity-search-in-postgresql-with-pgvector/

[^3]: https://arxiv.org/abs/2311.08874v2

[^4]: https://cloudberry.apache.org/docs/advanced-analytics/pgvector-search/

[^5]: https://neon.com/docs/extensions/pgvector

[^6]: https://postgresml.org/docs/open-source/pgml/guides/vector-database

[^7]: https://kihiujohn.github.io/blog/pgvector-postgres/

[^8]: https://jkatz.github.io/post/postgres/pgvector-overview-0.5.0/

[^9]: https://www.grizzlypeaksoftware.com/library/pgvector-vector-search-in-postgresql-j96fbhd9

[^10]: https://cloud.google.com/blog/products/databases/faster-similarity-search-performance-with-pgvector-indexes




Yes. **Pre-computing descendant embeddings is the main way to make aggregation-profile generation faster.** Instead of re-embedding the full aggregation content whenever anything changes, generate and persist the embedding for each aggregation and record as soon as its own semantic inputs are available, then combine those existing vectors when rebuilding ancestor profiles.

The optimization changes the work from:

```text
ancestor changes
  → collect all descendant content
  → re-embed all descendant content
  → generate ancestor embedding
```

to:

```text
descendant changes
  → update only the changed descendant embedding
  → update affected aggregation profiles from stored vectors
```

Vector averages are incrementally maintainable because a mean can be represented as a sum and a count; a changed contribution can be removed and a new contribution added without scanning the complete dataset.[1]

## Proposed embedding hierarchy

Maintain embeddings at every relevant level:

```text
record
  └── record embedding

child aggregation
  ├── metadata embedding
  ├── profile embedding
  └── descendant profile

parent aggregation
  ├── metadata embedding
  └── profile embedding derived from child profiles and direct records
```

For a record:

```text
record profile =
    embedding(record metadata + extracted content)
```

For an aggregation:

```text
aggregation profile =
    embedding(
        aggregation metadata
        + weighted descendant aggregation profiles
        + weighted direct record profiles
    )
```

This lets a parent use the already-computed profile of a child aggregation instead of reprocessing every record below that child.

## Two kinds of pre-computation

### Leaf-level embeddings

Generate embeddings for direct records and child aggregations:

```text
record embedding
child aggregation embedding
```

These are generated only when that object’s own semantic content changes.

### Derived aggregation profiles

Generate profiles for parent aggregations by combining stored descendant embeddings:

```text
parent profile =
    aggregation metadata
  + direct record embeddings
  + child aggregation embeddings
```

No language-model embedding call is required if the profile is calculated as a mathematical combination of compatible vectors.

This is the major performance benefit: a hierarchy of already-embedded descendants can be propagated upward using database-side arithmetic or a lightweight worker.

## Incremental profile formula

For a simple weighted centroid, maintain:

```text
weighted_embedding_sum
total_weight
descendant_count
```

Then calculate:

\[
p =
\operatorname{normalize}
\left(
\frac{\sum_{i=1}^{n} w_i e_i}
     {\sum_{i=1}^{n} w_i}
\right)
\]

Where:

- \(e_i\) is a descendant embedding.
- \(w_i\) is its contribution weight.
- \(p\) is the aggregation profile.

When a descendant is added:

```text
sum := sum + weight * embedding
total_weight := total_weight + weight
```

When it is removed:

```text
sum := sum - weight * embedding
total_weight := total_weight - weight
```

When it changes:

```text
sum := sum - old_weight * old_embedding
sum := sum + new_weight * new_embedding
```

The normalized profile can then be recalculated without invoking the embedding model.

PostgreSQL vector systems can calculate grouped vector averages, and pgvector supports storing and querying the resulting vectors directly.[2]

## Important hierarchy rule

Do not double-count descendants.

If a parent profile includes a child aggregation profile, do not also include all records beneath that child. Choose one representation:

```text
parent profile =
    direct records
  + child aggregation profiles
```

or:

```text
parent profile =
    all records recursively
```

The first approach is usually more efficient, but it means each child profile must accurately represent its descendants.

A good rule is:

```text
At each aggregation level:
- include direct records individually;
- include child aggregations as summarized profiles;
- do not include grandchildren separately.
```

## Weighting child profiles

A child aggregation profile can be weighted according to its descendant population.

For example:

```text
child profile contribution =
    child profile × sqrt(child_descendant_count)
```

or:

```text
child profile contribution =
    child profile × min(child_descendant_count, MAX_WEIGHT)
```

Using raw descendant counts may allow a very large child aggregation to dominate its parent. Capping or dampening the weight prevents one large branch from overwhelming all others.

Possible weighting functions include:

```text
w = 1
w = log(1 + descendant_count)
w = sqrt(descendant_count)
w = min(descendant_count, 100)
```

The correct function depends on whether you want:

```text
each child aggregation to have equal influence
```

or:

```text
each descendant record to have approximately equal influence
```

Since your goal is for the aggregation’s total descendant population to define its profile, a count-aware weight is reasonable, but it should be evaluated empirically.

## Metadata incorporation

A pure descendant centroid may be weak for a newly created aggregation. Include the aggregation’s own metadata as a separate component:

\[
p =
\operatorname{normalize}
\left(
w_m m +
\sum_i w_i e_i
\right)
\]

Where:

- \(m\) is the aggregation metadata embedding.
- \(w_m\) is the metadata weight.
- \(e_i\) are descendant or child-profile embeddings.

For an empty aggregation:

```text
profile = metadata embedding
```

For an established aggregation:

```text
profile = descendant profile with a smaller metadata contribution
```

You can also transition the metadata weight based on population:

```text
0 descendants:     metadata weight = 1.0
1–5 descendants:   metadata weight = 0.5
6–20 descendants:  metadata weight = 0.25
21+ descendants:   metadata weight = 0.10
```

These values are starting points, not fixed requirements.

## Suggested data model

A profile table might look like:

```sql
CREATE TABLE semantic_profile (
    object_type             text NOT NULL,
    object_id               bigint NOT NULL,

    model_name              text NOT NULL,
    model_version           text NOT NULL,
    vector_dimension        integer NOT NULL,

    embedding               vector(1024) NOT NULL,

    weighted_sum            vector(1024),
    total_weight            double precision NOT NULL DEFAULT 0,
    direct_descendant_count integer NOT NULL DEFAULT 0,

    source_version          bigint NOT NULL,
    source_hash             text NOT NULL,

    status                  text NOT NULL,
    generated_at            timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (
        object_type,
        object_id,
        model_name,
        model_version
    )
);
```

You may choose not to store `weighted_sum` in pgvector if your implementation maintains it elsewhere, but retaining it makes incremental addition and removal much easier.

For precise reversibility, also store each contribution:

```sql
CREATE TABLE semantic_profile_contribution (
    profile_object_type  text NOT NULL,
    profile_object_id    bigint NOT NULL,

    source_object_type   text NOT NULL,
    source_object_id     bigint NOT NULL,

    weight               double precision NOT NULL,
    embedding            vector(1024) NOT NULL,
    source_version       bigint NOT NULL,

    PRIMARY KEY (
        profile_object_type,
        profile_object_id,
        source_object_type,
        source_object_id
    )
);
```

This allows a changed descendant’s old contribution to be subtracted safely.

## Event-driven update process

When a record changes:

```text
1. Persist the record change.
2. Increment the record semantic version.
3. Enqueue record_embedding_refresh.
4. Commit.
```

The worker then:

```text
1. Extracts or receives the record’s semantic input.
2. Generates the record embedding.
3. Stores the new record embedding.
4. Emits record_embedding_changed.
5. Identifies direct parent aggregations.
6. Updates their contribution or queues profile refresh.
7. Propagates changes upward.
```

When a child aggregation changes:

```text
child profile changed
  → parent contribution changed
  → parent profile updated
  → grandparent contribution changed
  → continue upward
```

This is a dependency-propagation problem.

## Avoid synchronous recursive propagation

Do not update every ancestor synchronously inside the transaction that changes a record. A deep hierarchy could create long transactions, lock contention, and unpredictable latency.

Instead:

```text
transaction:
    persist domain change
    increment semantic version
    enqueue semantic refresh event
commit
```

A worker performs propagation asynchronously.

The system should tolerate temporary states such as:

```text
record embedding current
parent profile pending
grandparent profile stale
```

Candidate recommendations should use the latest published profile and expose its version or freshness timestamp if necessary.

## Coalescing events

If many descendants are added quickly, do not generate one profile-update task per event.

Use a coalescing key such as:

```text
(profile_type, aggregation_id, model_version)
```

Then maintain one pending job:

```text
aggregation 1234 requires refresh through source_version 82
```

When the worker runs, it processes the latest version.

This is particularly important for bulk imports, where thousands of records may enter the same aggregation in a short period.

## Correct handling of updates and deletes

Incremental aggregation requires knowing the previous contribution.

For a record update:

```text
remove old record embedding contribution
add new record embedding contribution
```

For a record deletion or reassignment:

```text
remove contribution from old aggregation
add contribution to new aggregation
```

For a child aggregation move:

```text
remove child-profile contribution from old parent
add child-profile contribution to new parent
```

If you cannot safely apply an inverse operation, mark the affected aggregation for a full rebuild.

## Versioning and stale-result protection

Every semantic source should have a version:

```text
record.semantic_version
aggregation.semantic_version
profile.source_version
```

A worker must not publish a result generated from an obsolete source version.

Example:

```text
profile job starts for aggregation version 42
new record arrives
aggregation version becomes 43
job finishes for version 42
worker discards or marks version 42 stale
version 43 is queued
```

This prevents a slower old embedding request from overwriting a newer profile.

Embedding pipelines commonly use event-driven updates, versioning, retries, and worker-based processing to keep derived vectors synchronized with source data.[3]

## When a model call is still needed

Pre-computation removes many model calls, but not all of them.

You still need an embedding-model invocation when:

```text
- A record’s semantic content changes.
- A child aggregation’s own metadata changes.
- OCR output changes.
- The embedding model changes.
- The embedding preprocessing changes.
- A new document type requires a new semantic projection.
```

You do not need a new model invocation merely because:

```text
- A parent aggregation receives another already-embedded record.
- A parent aggregation receives an already-profiled child.
- A descendant profile is mathematically combined into its parent.
```

## Caveat: centroid versus re-embedding combined text

There are two different operations:

### Mathematical profile aggregation

```text
profile = normalized weighted combination of vectors
```

This is fast and incrementally maintainable.

### Semantic re-embedding

```text
profile = embedding(full textual representation of all descendants)
```

This requires an embedding-model call and may capture interactions between terms that a simple centroid misses.

The proposed optimization uses mathematical aggregation. It is much faster, but it may not be identical to re-embedding the concatenated descendant text. You should test both approaches on a representative dataset.

A practical strategy is:

```text
incremental vector profile for normal operation
full semantic rebuild periodically or when quality degrades
```

## Hybrid profile design

You can retain both:

```text
1. Incremental centroid profile.
2. Optional periodically rebuilt textual profile.
```

Then use both during candidate retrieval:

```text
candidate_score =
    0.7 * incremental_profile_similarity
  + 0.3 * full_profile_similarity
```

Alternatively, use the incremental profile for fast retrieval and the full profile for reranking the top candidates.

This gives you:

```text
fast broad retrieval
+ higher-quality final ranking
```

## Recommendation

The proposed design should be:

```text
1. Generate and persist an embedding for every record after its semantic content is ready.
2. Generate and persist an embedding for every child aggregation after its own metadata or profile changes.
3. Maintain parent profiles from stored descendant vectors.
4. Propagate profile changes asynchronously up the aggregation hierarchy.
5. Use weighted incremental sums for normal updates.
6. Store source versions and contributions for safe updates and removals.
7. Perform periodic full rebuilds for correction and model changes.
8. Use pgvector to search the published aggregation profiles.
```

The most efficient representation is therefore not:

```text
re-embed the entire aggregation every time
```

but:

```text
embed each changed semantic object once
then propagate compatible vectors upward
```

This approach preserves your intended semantics—the aggregation profile reflects the totality of its descendants—while avoiding repeated embedding work. It also fits naturally with PostgreSQL’s relational hierarchy, asynchronous workers, event queues, and pgvector-based similarity search.

Sources
[1] incremental-pgvector / PostgreSQL Extension Network https://pgxn.org/dist/pg_trickle/0.36.0/blog/incremental-pgvector.html
[2] The pgvector extension - Neon Docs https://neon.com/docs/extensions/pgvector
[3] RAG Series – Embedding Versioning with pgvector https://www.dbi-services.com/blog/rag-series-embedding-versioning-with-pgvector-why-event-driven-architecture-is-a-precondition-to-ai-data-workflows/
[4] Bhorshrm/Event-Driven-Document-Intelligence-Platform - GitHub https://github.com/Bhorshrm/Event-Driven-Document-Intelligence-Platform
[5] GitHub - vinerya/faiss_vector_aggregator: This Python library ... https://github.com/vinerya/faiss_vector_aggregator
[6] Sharding pgvector - PgDog https://pgdog.dev/blog/sharding-pgvector
[7] pg-trickle/blog/pgvector-tooling-landscape.md at main https://github.com/grove/pg-trickle/blob/main/blog/pgvector-tooling-landscape.md
[8] GitHub - hirannor/HexaDocs: Event-driven document ingestion ... https://github.com/hirannor/HexaDocs
[9] Using Nova Embeddings - Amazon Nova https://docs.aws.amazon.com/nova/latest/userguide/nova-embeddings.html
[10] The Postgres Developer's Guide to Vector Index Tradeoffs https://www.tigerdata.com/blog/the-postgres-developers-guide-to-vector-index-tradeoffs

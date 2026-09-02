-- §4 schema migration (SPEC.md). Applied via the RDS Data API in Phase 1.
--
-- ┌──────────────────────────────────────────────────────────────────────────┐
-- │ VERIFY AT BUILD TIME (SPEC.md §4):                                         │
-- │ The bedrock_integration.bedrock_kb column names, types, and index         │
-- │ definitions MUST match Bedrock's current Aurora KB prerequisites doc:     │
-- │ https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html
-- │ Bedrock enforces specific column names for its managed table. Reconcile    │
-- │ this file against that page in Phase 2 before finalizing.                  │
-- │                                                                          │
-- │ Verified 2026-09-01 against knowledge-base-setup.html (Aurora RDS tab):   │
-- │  - Column names are NOT enforced; the doc's own example uses exactly this │
-- │    schema (bedrock_integration.bedrock_kb / id / embedding / chunks /     │
-- │    metadata / custom_metadata) — so SPEC §4 matches the current doc.      │
-- │  - Doc recommends pgvector >= 0.8.0 + `hnsw.iterative_scan='relaxed_order'`│
-- │    and `hnsw.max_scan_tuples=20000` at the DB level when metadata         │
-- │    filtering is used (our patient_scope filter qualifies). Set these in   │
-- │    Phase 1 once the engine version is pinned.                             │
-- └──────────────────────────────────────────────────────────────────────────┘

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS bedrock_integration;

CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding vector(1024),                 -- Titan Text Embeddings V2 dimension
  chunks text,
  metadata jsonb,
  custom_metadata jsonb                   -- patient_scope, source_note_id, note_type, encounter_date
);
CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_hnsw
  ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS bedrock_kb_chunks_fts
  ON bedrock_integration.bedrock_kb USING gin (to_tsvector('english', chunks));
CREATE INDEX IF NOT EXISTS bedrock_kb_custom_metadata_gin
  ON bedrock_integration.bedrock_kb USING gin (custom_metadata);

CREATE TABLE IF NOT EXISTS ontology_index (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid REFERENCES bedrock_integration.bedrock_kb(id),
  entity_text text NOT NULL,
  code_system text NOT NULL CHECK (code_system IN ('ICD10CM','SNOMEDCT','RXNORM')),
  code text NOT NULL,
  description text,
  confidence numeric,
  patient_scope text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ontology_index_entity_trgm
  ON ontology_index USING gin (entity_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ontology_index_code
  ON ontology_index (code_system, code);
CREATE INDEX IF NOT EXISTS ontology_index_patient_scope
  ON ontology_index (patient_scope);

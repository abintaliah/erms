BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 011',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install full-text search Phase 2 queue and publication model',true),
       set_config('app.event_metadata','{"migration":"011_add_full_text_search_phase2"}',true);

DO $$ BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'Full-text search requires PostgreSQL 18 or newer';
    END IF;
END $$;

CREATE TABLE digital_component_search_documents (
    digital_component_id bigint PRIMARY KEY REFERENCES digital_components(id) ON DELETE CASCADE,
    record_id bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    content_set_id bigint REFERENCES digital_component_content_sets(id) ON DELETE CASCADE,
    content_checksum_algo text,
    content_checksum_value text,
    status text NOT NULL,
    detected_mime_type text,
    detected_language text,
    extractor_name text,
    extractor_version text,
    extraction_config_version text NOT NULL,
    index_config_version text NOT NULL,
    indexed_at timestamptz,
    last_attempt_at timestamptz,
    last_error_code text,
    last_error_summary text,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT component_search_status_valid CHECK (
        status IN ('pending','processing','indexed','unsupported','failed','stale')
    ),
    CONSTRAINT component_search_identity_complete CHECK (
        (content_set_id IS NULL AND content_checksum_algo IS NULL AND content_checksum_value IS NULL)
        OR (content_set_id IS NOT NULL AND btrim(content_checksum_algo)<>'' AND btrim(content_checksum_value)<>'')
    ),
    CONSTRAINT component_search_error_summary_bounded CHECK (
        last_error_summary IS NULL OR length(last_error_summary)<=500
    )
);
CREATE INDEX component_search_status_reconcile_idx ON digital_component_search_documents
    (status,date_updated,digital_component_id);
CREATE INDEX component_search_record_idx ON digital_component_search_documents
    (record_id,digital_component_id);

CREATE TABLE digital_component_search_chunks (
    id bigserial PRIMARY KEY,
    digital_component_id bigint NOT NULL REFERENCES digital_component_search_documents(digital_component_id) ON DELETE CASCADE,
    chunk_no integer NOT NULL CHECK (chunk_no>=0),
    page_from integer,
    page_to integer,
    extracted_text text NOT NULL,
    search_vector tsvector NOT NULL,
    text_search_config regconfig NOT NULL,
    CONSTRAINT component_search_chunks_unique UNIQUE(digital_component_id,chunk_no),
    CONSTRAINT component_search_chunks_text_bounded CHECK (length(extracted_text)<=20000),
    CONSTRAINT component_search_chunks_pages_valid CHECK (
        (page_from IS NULL AND page_to IS NULL)
        OR (page_from>0 AND page_to>=page_from)
    )
);
CREATE INDEX component_search_chunks_vector_gin ON digital_component_search_chunks USING gin(search_vector);

CREATE TABLE content_indexing_jobs (
    id bigserial PRIMARY KEY,
    digital_component_id bigint NOT NULL REFERENCES digital_components(id) ON DELETE CASCADE,
    record_id bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    content_set_id bigint NOT NULL REFERENCES digital_component_content_sets(id) ON DELETE CASCADE,
    content_checksum_algo text NOT NULL,
    content_checksum_value text NOT NULL,
    trigger text NOT NULL,
    priority smallint NOT NULL DEFAULT 0 CHECK (priority BETWEEN -100 AND 100),
    status text NOT NULL DEFAULT 'queued',
    not_before timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation>=0),
    attempt_no integer NOT NULL DEFAULT 0 CHECK (attempt_no>=0),
    extraction_config_version text NOT NULL,
    index_config_version text NOT NULL,
    extractor_version text NOT NULL,
    required_capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    queued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    completed_at timestamptz,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT content_indexing_jobs_trigger_valid CHECK (
        trigger IN ('upload','replacement','manual_component','manual_record','backfill','retry','config_change')
    ),
    CONSTRAINT content_indexing_jobs_status_valid CHECK (
        status IN ('queued','leased','succeeded','failed','unsupported','cancelled','skipped')
    ),
    CONSTRAINT content_indexing_jobs_lease_shape CHECK (
        (status='leased' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status<>'leased')
    ),
    CONSTRAINT content_indexing_jobs_capabilities_object CHECK (jsonb_typeof(required_capabilities)='object')
);
CREATE UNIQUE INDEX content_indexing_jobs_active_unique
    ON content_indexing_jobs(
        digital_component_id,content_set_id,extraction_config_version,index_config_version,extractor_version
    ) WHERE status IN ('queued','leased');
CREATE INDEX content_indexing_jobs_claim_idx
    ON content_indexing_jobs(priority DESC,not_before,id)
    WHERE status IN ('queued','leased');
CREATE INDEX content_indexing_jobs_expired_lease_idx
    ON content_indexing_jobs(lease_expires_at,id) WHERE status='leased';

CREATE TABLE content_indexing_attempts (
    id bigserial PRIMARY KEY,
    digital_component_id bigint REFERENCES digital_components(id) ON DELETE SET NULL,
    record_id bigint REFERENCES records(id) ON DELETE SET NULL,
    content_set_id bigint REFERENCES digital_component_content_sets(id) ON DELETE SET NULL,
    content_checksum_algo text NOT NULL,
    content_checksum_value text NOT NULL,
    trigger text NOT NULL,
    requested_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    job_id bigint REFERENCES content_indexing_jobs(id) ON DELETE SET NULL,
    worker_id text,
    lease_generation bigint,
    status text NOT NULL,
    attempt_no integer NOT NULL CHECK (attempt_no>0),
    queued_at timestamptz NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    extractor_name text,
    extractor_version text,
    extraction_config_version text NOT NULL,
    index_config_version text NOT NULL,
    characters_extracted bigint CHECK (characters_extracted IS NULL OR characters_extracted>=0),
    chunks_created integer CHECK (chunks_created IS NULL OR chunks_created>=0),
    ocr_used boolean NOT NULL DEFAULT false,
    error_code text,
    error_summary text,
    request_id text,
    correlation_id text,
    CONSTRAINT content_indexing_attempts_status_valid CHECK (
        status IN ('processing','succeeded','failed','unsupported','cancelled','lease_lost','skipped')
    ),
    CONSTRAINT content_indexing_attempts_error_bounded CHECK (error_summary IS NULL OR length(error_summary)<=500),
    CONSTRAINT content_indexing_attempts_generation_unique UNIQUE(job_id,lease_generation)
);
CREATE INDEX content_indexing_attempts_completed_idx ON content_indexing_attempts(completed_at,id)
    WHERE status<>'processing';

CREATE TABLE content_indexing_result_chunks (
    job_id bigint NOT NULL REFERENCES content_indexing_jobs(id) ON DELETE CASCADE,
    lease_generation bigint NOT NULL,
    chunk_no integer NOT NULL CHECK (chunk_no>=0),
    page_from integer,
    page_to integer,
    extracted_text text NOT NULL,
    text_digest text NOT NULL,
    detected_language text,
    language_decision text NOT NULL,
    text_search_config regconfig NOT NULL,
    characters_count integer NOT NULL CHECK (characters_count>=0),
    date_staged timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(job_id,lease_generation,chunk_no),
    CONSTRAINT result_chunks_text_bounded CHECK (length(extracted_text)<=20000),
    CONSTRAINT result_chunks_digest_format CHECK (text_digest~'^[0-9a-f]{64}$'),
    CONSTRAINT result_chunks_language_decision_valid CHECK (
        language_decision IN ('english','arabic','mixed','unknown','short','low_confidence','unsupported_script','code_like')
    ),
    CONSTRAINT result_chunks_pages_valid CHECK (
        (page_from IS NULL AND page_to IS NULL) OR (page_from>0 AND page_to>=page_from)
    )
);
CREATE INDEX result_chunks_cleanup_idx ON content_indexing_result_chunks(date_staged,job_id,lease_generation);

CREATE TABLE content_indexing_operations (
    job_id bigint NOT NULL REFERENCES content_indexing_jobs(id) ON DELETE CASCADE,
    lease_generation bigint NOT NULL,
    operation text NOT NULL CHECK (operation IN ('chunk','complete','fail')),
    idempotency_key text NOT NULL,
    response jsonb NOT NULL,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(job_id,lease_generation,operation,idempotency_key),
    CONSTRAINT content_indexing_operations_key_bounded CHECK (
        btrim(idempotency_key)<>'' AND length(idempotency_key)<=200
    )
);

CREATE TABLE text_indexing_workers (
    service_user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    worker_id text NOT NULL,
    contract_version text NOT NULL,
    extractor_version text NOT NULL,
    extraction_config_version text NOT NULL,
    index_config_version text NOT NULL,
    capabilities jsonb NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_contact_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_until timestamptz NOT NULL,
    current_job_id bigint REFERENCES content_indexing_jobs(id) ON DELETE SET NULL,
    PRIMARY KEY(service_user_id,worker_id),
    CONSTRAINT text_indexing_workers_id_bounded CHECK (btrim(worker_id)<>'' AND length(worker_id)<=200),
    CONSTRAINT text_indexing_workers_capabilities_object CHECK (jsonb_typeof(capabilities)='object')
);
CREATE INDEX text_indexing_workers_active_idx ON text_indexing_workers(active_until,service_user_id,worker_id);

CREATE FUNCTION validate_component_search_identity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.content_set_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM digital_component_content_sets content_set
        WHERE content_set.id=NEW.content_set_id
          AND content_set.digital_component_id=NEW.digital_component_id
    ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='search content set does not belong to component'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM digital_components component
        WHERE component.id=NEW.digital_component_id AND component.record_id=NEW.record_id
    ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='search record does not match component'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER component_search_validate_identity BEFORE INSERT OR UPDATE
ON digital_component_search_documents FOR EACH ROW EXECUTE FUNCTION validate_component_search_identity();

CREATE FUNCTION schedule_component_content_indexing()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    active_set digital_component_content_sets%ROWTYPE;
    schedule_trigger text;
BEGIN
    IF NEW.content_status<>'available' OR NEW.active_content_set_id IS NULL THEN
        UPDATE digital_component_search_documents SET status='stale',date_updated=CURRENT_TIMESTAMP
         WHERE digital_component_id=NEW.id;
        RETURN NEW;
    END IF;
    SELECT * INTO STRICT active_set FROM digital_component_content_sets
     WHERE id=NEW.active_content_set_id AND digital_component_id=NEW.id AND status='active';
    schedule_trigger:=CASE WHEN TG_OP='INSERT' OR OLD.active_content_set_id IS NULL THEN 'upload' ELSE 'replacement' END;
    UPDATE digital_component_search_documents SET status='stale',date_updated=CURRENT_TIMESTAMP
     WHERE digital_component_id=NEW.id AND content_set_id IS DISTINCT FROM active_set.id;
    INSERT INTO digital_component_search_documents(
        digital_component_id,record_id,content_set_id,content_checksum_algo,content_checksum_value,
        status,extraction_config_version,index_config_version,date_updated
    ) VALUES (NEW.id,NEW.record_id,active_set.id,active_set.checksum_algo,active_set.checksum_value,
              'pending','tika-4.0.0-ocr-eng-ara-v1','fts-content-v1',CURRENT_TIMESTAMP)
    ON CONFLICT(digital_component_id) DO UPDATE SET
        record_id=EXCLUDED.record_id,content_set_id=EXCLUDED.content_set_id,
        content_checksum_algo=EXCLUDED.content_checksum_algo,
        content_checksum_value=EXCLUDED.content_checksum_value,status='pending',
        extraction_config_version=EXCLUDED.extraction_config_version,
        index_config_version=EXCLUDED.index_config_version,indexed_at=NULL,
        last_error_code=NULL,last_error_summary=NULL,date_updated=CURRENT_TIMESTAMP;
    INSERT INTO content_indexing_jobs(
        digital_component_id,record_id,content_set_id,content_checksum_algo,content_checksum_value,
        trigger,extraction_config_version,index_config_version,extractor_version,required_capabilities
    ) VALUES (NEW.id,NEW.record_id,active_set.id,active_set.checksum_algo,active_set.checksum_value,
              schedule_trigger,'tika-4.0.0-ocr-eng-ara-v1','fts-content-v1','4.0.0',
              jsonb_build_object('mime_type',NEW.mime_type,'max_input_bytes',52428800))
    ON CONFLICT(digital_component_id,content_set_id,extraction_config_version,index_config_version,extractor_version)
        WHERE status IN ('queued','leased') DO NOTHING;
    RETURN NEW;
END $$;
CREATE TRIGGER digital_components_schedule_content_indexing
AFTER INSERT OR UPDATE OF active_content_set_id,content_status ON digital_components
FOR EACH ROW EXECUTE FUNCTION schedule_component_content_indexing();

INSERT INTO schema_migrations(version) VALUES ('011_add_full_text_search_phase2')
ON CONFLICT(version) DO NOTHING;

COMMIT;

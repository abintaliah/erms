BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true);
SELECT set_config('app.actor_name', 'Database migration 027', true);
SELECT set_config('app.event_source', 'migration', true);
SELECT set_config(
    'app.change_reason',
    'Replace monolithic PostgreSQL bytea content with ordered, streamable segments',
    true
);

DROP TRIGGER IF EXISTS digital_component_blobs_protect_closed_aggregation
    ON digital_component_blobs;
ALTER TABLE digital_component_blobs RENAME TO digital_component_blobs_legacy;

CREATE TABLE digital_component_content_sets (
    id                    bigserial PRIMARY KEY,
    digital_component_id  bigint NOT NULL
        REFERENCES digital_components (id) ON DELETE CASCADE,
    status                text NOT NULL
        CHECK (status IN ('staged', 'active', 'superseded', 'failed')),
    size_in_bytes         bigint,
    segment_count         integer,
    checksum_algo         text,
    checksum_value        text,
    date_created          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_completed        timestamptz,
    CONSTRAINT digital_component_content_sets_size_nonnegative
        CHECK (size_in_bytes IS NULL OR size_in_bytes >= 0),
    CONSTRAINT digital_component_content_sets_count_nonnegative
        CHECK (segment_count IS NULL OR segment_count >= 0),
    CONSTRAINT digital_component_content_sets_component_id_id_unique
        UNIQUE (digital_component_id, id)
);
CREATE UNIQUE INDEX digital_component_one_active_content_set_idx
    ON digital_component_content_sets (digital_component_id)
    WHERE status = 'active';

ALTER TABLE digital_components
    ADD COLUMN active_content_set_id bigint,
    ADD COLUMN upload_completed_at timestamptz;
ALTER TABLE digital_components
    ADD CONSTRAINT digital_components_active_content_set_fk
    FOREIGN KEY (id, active_content_set_id)
    REFERENCES digital_component_content_sets (digital_component_id, id)
    DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE digital_components DROP CONSTRAINT digital_components_content_status_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_content_status_valid
    CHECK (content_status IN (
        'pending', 'uploading', 'available', 'failed', 'quarantined', 'deleted'
    ));

CREATE TABLE digital_component_blobs (
    id                    bigserial PRIMARY KEY,
    content_set_id        bigint NOT NULL
        REFERENCES digital_component_content_sets (id) ON DELETE CASCADE,
    segment_no            integer NOT NULL,
    segment_size          integer NOT NULL,
    segment_checksum_algo text,
    segment_checksum_value text,
    content               bytea NOT NULL,
    date_stored           timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT digital_component_blobs_set_segment_unique
        UNIQUE (content_set_id, segment_no),
    CONSTRAINT digital_component_blobs_segment_no_nonnegative
        CHECK (segment_no >= 0),
    CONSTRAINT digital_component_blobs_segment_size_positive
        CHECK (segment_size > 0),
    CONSTRAINT digital_component_blobs_segment_size_matches
        CHECK (segment_size = octet_length(content))
);
CREATE INDEX digital_component_blobs_content_set_order_idx
    ON digital_component_blobs (content_set_id, segment_no);

INSERT INTO digital_component_content_sets (
    digital_component_id, status, size_in_bytes, segment_count,
    checksum_algo, checksum_value, date_created, date_completed
)
SELECT dc.id, 'active', octet_length(legacy.content),
       CASE WHEN octet_length(legacy.content) = 0 THEN 0 ELSE 1 END,
       dc.checksum_algo, dc.checksum_value, legacy.date_stored, legacy.date_stored
FROM digital_component_blobs_legacy legacy
JOIN digital_components dc ON dc.id = legacy.digital_component_id;

INSERT INTO digital_component_blobs (
    content_set_id, segment_no, segment_size, segment_checksum_algo,
    segment_checksum_value, content, date_stored
)
SELECT content_set.id, 0, octet_length(legacy.content), dc.checksum_algo,
       dc.checksum_value, legacy.content,
       legacy.date_stored
FROM digital_component_blobs_legacy legacy
JOIN digital_component_content_sets content_set
  ON content_set.digital_component_id = legacy.digital_component_id
 AND content_set.status = 'active'
JOIN digital_components dc ON dc.id = legacy.digital_component_id
WHERE octet_length(legacy.content) > 0;

UPDATE digital_components dc
SET active_content_set_id = content_set.id,
    upload_completed_at = content_set.date_completed
FROM digital_component_content_sets content_set
WHERE content_set.digital_component_id = dc.id
  AND content_set.status = 'active';

DROP TABLE digital_component_blobs_legacy;

ALTER TABLE record_draft_components
    ADD COLUMN content_status text NOT NULL DEFAULT 'available',
    ADD COLUMN segment_count integer,
    ADD COLUMN upload_completed_at timestamptz;
ALTER TABLE record_draft_components
    ADD CONSTRAINT record_draft_components_content_status_valid
        CHECK (content_status IN (
            'uploading', 'interrupted', 'finalizing', 'available',
            'failed', 'cancelled', 'expired'
        )),
    ADD CONSTRAINT record_draft_components_segment_count_nonnegative
        CHECK (segment_count IS NULL OR segment_count >= 0);

CREATE TABLE record_draft_component_blobs (
    id                         bigserial PRIMARY KEY,
    record_draft_component_id  bigint NOT NULL
        REFERENCES record_draft_components (id) ON DELETE CASCADE,
    segment_no                 integer NOT NULL,
    segment_size               integer NOT NULL,
    segment_checksum_algo      text,
    segment_checksum_value     text,
    content                    bytea NOT NULL,
    date_stored                timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT record_draft_component_blobs_component_segment_unique
        UNIQUE (record_draft_component_id, segment_no),
    CONSTRAINT record_draft_component_blobs_segment_no_nonnegative
        CHECK (segment_no >= 0),
    CONSTRAINT record_draft_component_blobs_segment_size_positive
        CHECK (segment_size > 0),
    CONSTRAINT record_draft_component_blobs_segment_size_matches
        CHECK (segment_size = octet_length(content))
);
CREATE INDEX record_draft_component_blobs_component_order_idx
    ON record_draft_component_blobs (record_draft_component_id, segment_no);

INSERT INTO record_draft_component_blobs (
    record_draft_component_id, segment_no, segment_size,
    segment_checksum_algo, segment_checksum_value, content, date_stored
)
SELECT id, 0, octet_length(content), checksum_algo,
       checksum_value, content, date_created
FROM record_draft_components
WHERE octet_length(content) > 0;
UPDATE record_draft_components
SET segment_count = CASE WHEN size_in_bytes = 0 THEN 0 ELSE 1 END,
    upload_completed_at = date_created;
ALTER TABLE record_draft_components DROP COLUMN content;

CREATE TABLE content_upload_sessions (
    id                    bigserial PRIMARY KEY,
    digital_component_id  bigint REFERENCES digital_components (id)
        ON DELETE CASCADE,
    draft_component_id    bigint REFERENCES record_draft_components (id)
        ON DELETE CASCADE,
    content_set_id        bigint REFERENCES digital_component_content_sets (id)
        ON DELETE CASCADE,
    status                text NOT NULL DEFAULT 'uploading'
        CHECK (status IN (
            'uploading', 'interrupted', 'finalizing', 'completed',
            'failed', 'cancelled', 'expired'
        )),
    next_segment_no       integer NOT NULL DEFAULT 0 CHECK (next_segment_no >= 0),
    bytes_received        bigint NOT NULL DEFAULT 0 CHECK (bytes_received >= 0),
    expected_size         bigint CHECK (expected_size IS NULL OR expected_size >= 0),
    checksum_algo         text NOT NULL DEFAULT 'sha256',
    date_created          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at            timestamptz NOT NULL DEFAULT (CURRENT_TIMESTAMP + interval '1 day'),
    CONSTRAINT content_upload_sessions_one_target CHECK (
        ((digital_component_id IS NOT NULL)::integer
         + (draft_component_id IS NOT NULL)::integer) = 1
    ),
    CONSTRAINT content_upload_sessions_content_set_target CHECK (
        (digital_component_id IS NOT NULL AND content_set_id IS NOT NULL)
        OR (draft_component_id IS NOT NULL AND content_set_id IS NULL)
    )
);
CREATE INDEX content_upload_sessions_cleanup_idx
    ON content_upload_sessions (status, expires_at);
CREATE UNIQUE INDEX content_upload_sessions_open_component_idx
    ON content_upload_sessions (digital_component_id)
    WHERE status IN ('uploading', 'interrupted', 'finalizing');
CREATE UNIQUE INDEX content_upload_sessions_open_draft_component_idx
    ON content_upload_sessions (draft_component_id)
    WHERE status IN ('uploading', 'interrupted', 'finalizing');

CREATE OR REPLACE FUNCTION bump_digital_component_version()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - ARRAY['active_content_set_id', 'upload_completed_at'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['active_content_set_id', 'upload_completed_at']) THEN
        NEW.version := OLD.version + 1;
    ELSE
        NEW.version := OLD.version;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS digital_components_bump_version ON digital_components;
CREATE TRIGGER digital_components_bump_version
BEFORE UPDATE ON digital_components
FOR EACH ROW EXECUTE FUNCTION bump_digital_component_version();

CREATE OR REPLACE FUNCTION protect_content_set_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE component_id bigint;
BEGIN
    component_id := CASE WHEN TG_OP = 'DELETE'
        THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
    PERFORM assert_record_effectively_open(
        (SELECT record_id FROM digital_components WHERE id = component_id)
    );
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION protect_blob_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_id bigint;
BEGIN
    set_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.content_set_id ELSE NEW.content_set_id END;
    PERFORM assert_record_effectively_open(
        (SELECT dc.record_id
           FROM digital_component_content_sets content_set
           JOIN digital_components dc ON dc.id = content_set.digital_component_id
          WHERE content_set.id = set_id)
    );
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER digital_component_content_sets_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_content_sets
FOR EACH ROW EXECUTE FUNCTION protect_content_set_in_closed_aggregation();
CREATE TRIGGER digital_component_blobs_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_blobs
FOR EACH ROW EXECUTE FUNCTION protect_blob_in_closed_aggregation();

INSERT INTO schema_migrations (version)
VALUES ('027_segment_postgresql_content')
ON CONFLICT (version) DO NOTHING;

COMMIT;

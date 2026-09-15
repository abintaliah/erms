-- Staging area for assembling records and their content before one atomic commit.
CREATE TABLE IF NOT EXISTS record_drafts (
    id                  bigserial PRIMARY KEY,
    owner_user_id       bigint REFERENCES users (id) ON DELETE RESTRICT,
    aggregation_id      bigint REFERENCES aggregations (id) ON DELETE RESTRICT,
    record_number       text,
    title               text,
    description         text,
    date_originated     timestamptz,
    date_created        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at          timestamptz NOT NULL DEFAULT (CURRENT_TIMESTAMP + interval '7 days'),
    status              text NOT NULL DEFAULT 'open',
    version             bigint NOT NULL DEFAULT 1,
    CONSTRAINT record_drafts_status_valid CHECK (status IN ('open', 'committed')),
    CONSTRAINT record_drafts_version_positive CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS record_drafts_owner_user_id_idx ON record_drafts (owner_user_id);
CREATE INDEX IF NOT EXISTS record_drafts_expires_at_idx ON record_drafts (expires_at);

CREATE TABLE IF NOT EXISTS record_draft_components (
    id                  bigserial PRIMARY KEY,
    draft_id            bigint NOT NULL REFERENCES record_drafts (id) ON DELETE CASCADE,
    component_order     integer NOT NULL,
    file_name           text NOT NULL,
    date_created        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_originated     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mime_type           text NOT NULL,
    size_in_bytes       bigint NOT NULL,
    checksum_algo       text NOT NULL,
    checksum_value      text NOT NULL,
    content             bytea NOT NULL,
    CONSTRAINT record_draft_components_order_positive CHECK (component_order > 0),
    CONSTRAINT record_draft_components_size_nonnegative CHECK (size_in_bytes >= 0),
    CONSTRAINT record_draft_components_file_name_not_blank CHECK (btrim(file_name) <> ''),
    CONSTRAINT record_draft_components_draft_order_unique
        UNIQUE (draft_id, component_order) DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX IF NOT EXISTS record_draft_components_draft_id_idx
    ON record_draft_components (draft_id);

CREATE OR REPLACE FUNCTION touch_record_draft()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS record_drafts_touch ON record_drafts;
CREATE TRIGGER record_drafts_touch
BEFORE UPDATE ON record_drafts
FOR EACH ROW EXECUTE FUNCTION touch_record_draft();

INSERT INTO schema_migrations (version)
VALUES ('004_add_record_drafts')
ON CONFLICT (version) DO NOTHING;

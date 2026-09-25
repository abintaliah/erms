BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 010',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install full-text search Phase 1 metadata and service-authentication foundation',true),
       set_config('app.event_metadata','{"migration":"010_add_full_text_search_phase1"}',true);

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'Full-text search requires PostgreSQL 18 or newer';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_config config
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid=config.cfgnamespace
        WHERE namespace.nspname='pg_catalog' AND config.cfgname='simple'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_config config
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid=config.cfgnamespace
        WHERE namespace.nspname='pg_catalog' AND config.cfgname='english'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_config config
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid=config.cfgnamespace
        WHERE namespace.nspname='pg_catalog' AND config.cfgname='arabic'
    ) THEN
        RAISE EXCEPTION 'Required PostgreSQL text-search configurations are unavailable';
    END IF;
END;
$$;

CREATE TABLE record_search_documents (
    record_id bigint PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
    search_vector tsvector NOT NULL,
    text_search_config regconfig NOT NULL,
    indexed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    index_config_version text NOT NULL,
    CONSTRAINT record_search_documents_config_version_not_blank
        CHECK (btrim(index_config_version) <> '')
);

CREATE INDEX record_search_documents_vector_gin
    ON record_search_documents USING gin(search_vector);

CREATE TABLE aggregation_search_documents (
    aggregation_id bigint PRIMARY KEY REFERENCES aggregations(id) ON DELETE CASCADE,
    search_vector tsvector NOT NULL,
    text_search_config regconfig NOT NULL,
    indexed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    index_config_version text NOT NULL,
    CONSTRAINT aggregation_search_documents_config_version_not_blank
        CHECK (btrim(index_config_version) <> '')
);

CREATE INDEX aggregation_search_documents_vector_gin
    ON aggregation_search_documents USING gin(search_vector);

CREATE FUNCTION refresh_record_metadata_search_document()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO record_search_documents(
        record_id,search_vector,text_search_config,indexed_at,index_config_version
    ) VALUES (
        NEW.id,
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.record_number,'')),'A') ||
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.title,'')),'A') ||
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.description,'')),'B'),
        'pg_catalog.simple'::regconfig,
        CURRENT_TIMESTAMP,
        'fts-metadata-v1'
    )
    ON CONFLICT(record_id) DO UPDATE SET
        search_vector=EXCLUDED.search_vector,
        text_search_config=EXCLUDED.text_search_config,
        indexed_at=EXCLUDED.indexed_at,
        index_config_version=EXCLUDED.index_config_version;
    RETURN NEW;
END;
$$;

CREATE FUNCTION refresh_aggregation_metadata_search_document()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO aggregation_search_documents(
        aggregation_id,search_vector,text_search_config,indexed_at,index_config_version
    ) VALUES (
        NEW.id,
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.aggregation_number,'')),'A') ||
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.title,'')),'A') ||
        setweight(to_tsvector('pg_catalog.simple',coalesce(NEW.description,'')),'B'),
        'pg_catalog.simple'::regconfig,
        CURRENT_TIMESTAMP,
        'fts-metadata-v1'
    )
    ON CONFLICT(aggregation_id) DO UPDATE SET
        search_vector=EXCLUDED.search_vector,
        text_search_config=EXCLUDED.text_search_config,
        indexed_at=EXCLUDED.indexed_at,
        index_config_version=EXCLUDED.index_config_version;
    RETURN NEW;
END;
$$;

CREATE TRIGGER records_refresh_metadata_search
AFTER INSERT OR UPDATE OF record_number,title,description ON records
FOR EACH ROW EXECUTE FUNCTION refresh_record_metadata_search_document();

CREATE TRIGGER aggregations_refresh_metadata_search
AFTER INSERT OR UPDATE OF aggregation_number,title,description ON aggregations
FOR EACH ROW EXECUTE FUNCTION refresh_aggregation_metadata_search_document();

INSERT INTO record_search_documents(
    record_id,search_vector,text_search_config,indexed_at,index_config_version
)
SELECT record.id,
       setweight(to_tsvector('pg_catalog.simple',coalesce(record.record_number,'')),'A') ||
       setweight(to_tsvector('pg_catalog.simple',coalesce(record.title,'')),'A') ||
       setweight(to_tsvector('pg_catalog.simple',coalesce(record.description,'')),'B'),
       'pg_catalog.simple'::regconfig,CURRENT_TIMESTAMP,'fts-metadata-v1'
FROM records record;

INSERT INTO aggregation_search_documents(
    aggregation_id,search_vector,text_search_config,indexed_at,index_config_version
)
SELECT aggregation.id,
       setweight(to_tsvector('pg_catalog.simple',coalesce(aggregation.aggregation_number,'')),'A') ||
       setweight(to_tsvector('pg_catalog.simple',coalesce(aggregation.title,'')),'A') ||
       setweight(to_tsvector('pg_catalog.simple',coalesce(aggregation.description,'')),'B'),
       'pg_catalog.simple'::regconfig,CURRENT_TIMESTAMP,'fts-metadata-v1'
FROM aggregations aggregation;

CREATE VIEW authorized_record_search_documents AS
SELECT document.record_id,document.search_vector,document.text_search_config,
       document.indexed_at,document.index_config_version
FROM record_search_documents document
WHERE current_user_can_view_record(document.record_id);

CREATE VIEW authorized_aggregation_search_documents AS
SELECT document.aggregation_id,document.search_vector,document.text_search_config,
       document.indexed_at,document.index_config_version
FROM aggregation_search_documents document
WHERE current_user_can_view_aggregation(document.aggregation_id);

ALTER TABLE privileges
    ADD COLUMN account_type_restriction text;
ALTER TABLE privileges
    ADD CONSTRAINT privileges_account_type_restriction_valid
    CHECK (account_type_restriction IS NULL OR account_type_restriction IN ('person','service'));

INSERT INTO privileges(code,name,description,category,is_reserved,account_type_restriction)
VALUES
    ('content.index.execute','Execute Content Indexing',
     'Use the lease-scoped internal text-indexing worker contract.','administration',false,'service'),
    ('search.query.debug','Debug Search Query',
     'Request sanitized API-level diagnostics for searches performed by the current user.','administration',false,'person')
ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code='ALL_PRIVS'
  AND privilege.code IN ('content.index.execute','search.query.debug')
ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code IN ('SYS_ADMIN','INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code='search.query.debug'
ON CONFLICT DO NOTHING;

INSERT INTO profiles(code,name,description,is_system)
VALUES ('TEXT_INDEXER_SERVICE','Text Indexer Service',
        'Protected non-interactive profile for the internal text-indexing worker contract.',true);

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code='TEXT_INDEXER_SERVICE' AND privilege.code='content.index.execute';

ALTER TABLE roles ADD COLUMN is_system boolean NOT NULL DEFAULT false;
ALTER TABLE roles ADD COLUMN account_type_restriction text;
ALTER TABLE roles ALTER COLUMN org_unit_id DROP NOT NULL;
ALTER TABLE roles ADD CONSTRAINT roles_account_type_restriction_valid
    CHECK (account_type_restriction IS NULL OR account_type_restriction IN ('person','service'));
ALTER TABLE roles ADD CONSTRAINT roles_system_service_shape
    CHECK (
        (is_system AND account_type_restriction='service' AND org_unit_id IS NULL
         AND supervisor_role_id IS NULL AND NOT is_information_governance)
        OR
        (NOT is_system AND account_type_restriction IS NULL AND org_unit_id IS NOT NULL)
    );

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        role.date_deactivated IS NULL
        AND CASE
            WHEN role.is_system THEN
                role.account_type_restriction='service' AND role.org_unit_id IS NULL
            ELSE org_unit_effectively_active(role.org_unit_id)
        END,
        false
    )
    FROM roles role WHERE role.id=p_role_id;
$$;

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    selected_account_type text;
    selected_role_restriction text;
    selected_role_is_system boolean;
BEGIN
    SELECT account_type INTO selected_account_type
    FROM users
    WHERE id=NEW.user_id AND date_deactivated IS NULL AND date_suspended IS NULL;
    IF selected_account_type IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an active user';
    END IF;
    SELECT account_type_restriction,is_system
      INTO selected_role_restriction,selected_role_is_system
      FROM roles WHERE id=NEW.role_id;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    IF selected_role_restriction IS NOT NULL
       AND selected_role_restriction<>selected_account_type THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role account type restriction does not match user account type';
    END IF;
    IF selected_role_is_system AND EXISTS (
        SELECT 1 FROM user_role_assignments existing
        WHERE existing.user_id=NEW.user_id AND existing.id<>COALESCE(NEW.id,0)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='service system role must be the account only role assignment';
    END IF;
    IF NOT selected_role_is_system AND EXISTS (
        SELECT 1 FROM user_role_assignments existing
        JOIN roles existing_role ON existing_role.id=existing.role_id
        WHERE existing.user_id=NEW.user_id AND existing.id<>COALESCE(NEW.id,0)
          AND existing_role.is_system AND existing_role.account_type_restriction='service'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='service system role must be the account only role assignment';
    END IF;
    RETURN NEW;
END;
$$;

INSERT INTO roles(
    org_unit_id,supervisor_role_id,code,name,description,security_level_id,
    profile_id,is_information_governance,is_system,account_type_restriction
)
SELECT NULL,NULL,'text-indexer-service','Text Indexer Service',
       'Protected non-organizational role for text-indexer service accounts.',
       level.id,profile.id,false,true,'service'
FROM security_levels level CROSS JOIN profiles profile
WHERE level.level_number=(SELECT min(level_number) FROM security_levels)
  AND profile.code='TEXT_INDEXER_SERVICE';

CREATE FUNCTION protect_text_indexer_profile_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_profile_id bigint;
    target_privilege_id bigint;
    target_profile_code text;
    target_privilege_code text;
BEGIN
    IF TG_OP='DELETE' THEN
        target_profile_id:=OLD.profile_id;
        target_privilege_id:=OLD.privilege_id;
    ELSE
        target_profile_id:=NEW.profile_id;
        target_privilege_id:=NEW.privilege_id;
    END IF;
    SELECT code INTO target_profile_code FROM profiles
    WHERE id=target_profile_id;
    SELECT code INTO target_privilege_code FROM privileges
    WHERE id=target_privilege_id;
    IF target_profile_code='TEXT_INDEXER_SERVICE' THEN
        IF TG_OP='DELETE' OR target_privilege_code<>'content.index.execute' THEN
            RAISE EXCEPTION USING ERRCODE='P0001',
                MESSAGE='TEXT_INDEXER_SERVICE profile is protected and contains exactly content.index.execute';
        END IF;
    END IF;
    IF TG_OP='DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER profile_privileges_protect_text_indexer
BEFORE INSERT OR UPDATE OR DELETE ON profile_privileges
FOR EACH ROW EXECUTE FUNCTION protect_text_indexer_profile_membership();

CREATE FUNCTION protect_text_indexer_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code='TEXT_INDEXER_SERVICE' THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='TEXT_INDEXER_SERVICE profile is protected';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER profiles_protect_text_indexer
BEFORE UPDATE OR DELETE ON profiles
FOR EACH ROW EXECUTE FUNCTION protect_text_indexer_profile();

CREATE FUNCTION protect_text_indexer_role()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code='text-indexer-service' AND OLD.is_system THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='text-indexer-service role is protected';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER roles_protect_text_indexer
BEFORE UPDATE OR DELETE ON roles
FOR EACH ROW EXECUTE FUNCTION protect_text_indexer_role();

CREATE TABLE service_account_credentials (
    id bigserial PRIMARY KEY,
    service_user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL,
    credential_identifier text NOT NULL,
    secret_hash text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    last_worker_id text,
    date_revoked timestamptz,
    created_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    revoked_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT service_account_credentials_name_not_blank CHECK (btrim(name)<>''),
    CONSTRAINT service_account_credentials_identifier_format
        CHECK (credential_identifier ~ '^[0-9A-HJKMNP-TV-Z]{26}$'),
    CONSTRAINT service_account_credentials_identifier_unique UNIQUE(credential_identifier),
    CONSTRAINT service_account_credentials_hash_format CHECK (secret_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT service_account_credentials_status_valid CHECK (status IN ('active','revoked')),
    CONSTRAINT service_account_credentials_expiry_valid CHECK (expires_at>date_created),
    CONSTRAINT service_account_credentials_last_worker_not_blank
        CHECK (last_worker_id IS NULL OR btrim(last_worker_id)<>''),
    CONSTRAINT service_account_credentials_revocation_state CHECK (
        (status='active' AND date_revoked IS NULL AND revoked_by_user_id IS NULL)
        OR (status='revoked' AND date_revoked IS NOT NULL)
    )
);

CREATE INDEX service_account_credentials_service_user_idx
    ON service_account_credentials(service_user_id,date_created DESC,id DESC);
CREATE INDEX service_account_credentials_active_expiry_idx
    ON service_account_credentials(expires_at,id) WHERE status='active';

CREATE FUNCTION validate_service_account_credential()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users account
        WHERE account.id=NEW.service_user_id AND account.account_type='service'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='API key target must be a service account';
    END IF;
    IF NEW.created_by_user_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM users actor
        WHERE actor.id=NEW.created_by_user_id AND actor.account_type='person'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='API key creator must be a person account';
    END IF;
    IF NEW.revoked_by_user_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM users actor
        WHERE actor.id=NEW.revoked_by_user_id AND actor.account_type='person'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='API key revoker must be a person account';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER service_account_credentials_validate
BEFORE INSERT OR UPDATE ON service_account_credentials
FOR EACH ROW EXECUTE FUNCTION validate_service_account_credential();

CREATE FUNCTION reject_service_account_password()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM users account WHERE account.id=NEW.user_id AND account.account_type='service') THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='service accounts cannot have interactive passwords';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER user_credentials_reject_service_account
BEFORE INSERT OR UPDATE OF user_id ON user_credentials
FOR EACH ROW EXECUTE FUNCTION reject_service_account_password();

INSERT INTO schema_migrations(version)
VALUES ('010_add_full_text_search_phase1')
ON CONFLICT(version) DO NOTHING;

COMMIT;

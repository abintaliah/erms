BEGIN;

CREATE TABLE saved_searches (
    id              bigserial PRIMARY KEY,
    owner_user_id   bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            text NOT NULL,
    category        text,
    description     text,
    resource_type   text NOT NULL,
    definition      jsonb NOT NULL,
    audience_mode   text NOT NULL DEFAULT 'private',
    date_created    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version         bigint NOT NULL DEFAULT 1,
    CONSTRAINT saved_searches_name_not_blank CHECK (btrim(name)<>''),
    CONSTRAINT saved_searches_name_bounded CHECK (length(name)<=120),
    CONSTRAINT saved_searches_category_valid CHECK (
        category IS NULL OR (btrim(category)<>'' AND length(category)<=80)
    ),
    CONSTRAINT saved_searches_description_bounded CHECK (
        description IS NULL OR length(description)<=500
    ),
    CONSTRAINT saved_searches_resource_type_valid CHECK (
        resource_type IN ('record','aggregation')
    ),
    CONSTRAINT saved_searches_audience_mode_valid CHECK (
        audience_mode IN ('private','shared')
    ),
    CONSTRAINT saved_searches_version_positive CHECK (version>0),
    CONSTRAINT saved_searches_definition_valid CHECK (
        jsonb_typeof(definition)='object'
        AND definition->>'schema_version'='1'
        AND definition->>'resource_type'=resource_type
        AND jsonb_typeof(definition->'request')='object'
        AND (definition->>'max_results') ~ '^[0-9]+$'
        AND (definition->>'max_results')::integer BETWEEN 1 AND 5000
    )
);
CREATE UNIQUE INDEX saved_searches_owner_name_ci_unique
    ON saved_searches(owner_user_id,lower(name));
CREATE INDEX saved_searches_owner_updated_idx
    ON saved_searches(owner_user_id,date_updated DESC,id DESC);
CREATE INDEX saved_searches_resource_updated_idx
    ON saved_searches(resource_type,date_updated DESC,id DESC);
CREATE INDEX saved_searches_category_ci_idx
    ON saved_searches(lower(category),date_updated DESC,id DESC)
    WHERE category IS NOT NULL;

CREATE TABLE saved_search_role_grants (
    saved_search_id bigint NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
    role_id         bigint NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    PRIMARY KEY(saved_search_id,role_id)
);
CREATE INDEX saved_search_role_grants_role_idx
    ON saved_search_role_grants(role_id,saved_search_id);

CREATE TABLE saved_search_org_unit_grants (
    saved_search_id bigint NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
    org_unit_id     bigint NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
    PRIMARY KEY(saved_search_id,org_unit_id)
);
CREATE INDEX saved_search_org_unit_grants_unit_idx
    ON saved_search_org_unit_grants(org_unit_id,saved_search_id);

CREATE FUNCTION validate_saved_search_owner()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users owner
        WHERE owner.id=NEW.owner_user_id AND owner.account_type='person'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514',
            MESSAGE='saved_search_owner_must_be_person';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER saved_searches_validate_owner
BEFORE INSERT OR UPDATE OF owner_user_id ON saved_searches
FOR EACH ROW EXECUTE FUNCTION validate_saved_search_owner();

CREATE FUNCTION touch_saved_search()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated:=CURRENT_TIMESTAMP;
    NEW.version:=OLD.version+1;
    RETURN NEW;
END;
$$;
CREATE TRIGGER saved_searches_touch
BEFORE UPDATE ON saved_searches
FOR EACH ROW EXECUTE FUNCTION touch_saved_search();

CREATE FUNCTION enforce_saved_search_change_reason()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='saved_search_change_reason_required';
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER saved_searches_require_change_reason
BEFORE UPDATE OR DELETE ON saved_searches
FOR EACH ROW EXECUTE FUNCTION enforce_saved_search_change_reason();

CREATE TRIGGER saved_searches_record_history
AFTER INSERT OR UPDATE OR DELETE ON saved_searches
FOR EACH ROW EXECUTE FUNCTION record_entity_history('saved_search');

INSERT INTO privileges(
    code,name,description,category,is_reserved,account_type_restriction
) VALUES
 ('search.saved_search.save','Save Searches',
  'Create saved searches, copy accessible searches, and manage permitted audiences for owned searches.',
  'administration',false,'person'),
 ('search.saved_search.administrator','Administer Saved Searches',
  'Inspect and modify any saved search and manage any eligible role or organizational-unit audience.',
  'administration',false,'person'),
 ('search.saved_search.delete','Delete Saved Searches',
  'Delete owned saved searches and, with saved-search administration, searches owned by other users.',
  'administration',false,'person')
ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE (
    profile.code IN ('ALL_PRIVS','SYS_ADMIN','INFO_GOV_MGR')
    AND privilege.code IN (
        'search.saved_search.save',
        'search.saved_search.administrator',
        'search.saved_search.delete'
    )
) OR (
    profile.code='INFO_GOV_OFFICER'
    AND privilege.code IN ('search.saved_search.save','search.saved_search.delete')
)
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('018_add_advanced_search_phase1')
ON CONFLICT(version) DO NOTHING;

COMMIT;

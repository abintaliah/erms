BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install the approved internationalization Phase 2 message catalogue',true),
       set_config('app.event_metadata','{"migration":"020_add_ui_message_catalogue"}',true);

CREATE TABLE ui_message_definitions (
    message_key text PRIMARY KEY,
    context_group text NOT NULL,
    default_text text NOT NULL,
    semantic_meaning text NOT NULL,
    common_locations jsonb NOT NULL,
    translator_guidance text NOT NULL,
    grammatical_role text NOT NULL,
    parameter_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
    rendered_example text NOT NULL,
    is_html boolean NOT NULL DEFAULT false,
    is_deprecated boolean NOT NULL DEFAULT false,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version bigint NOT NULL DEFAULT 1,
    CONSTRAINT ui_message_definitions_key_shape CHECK (message_key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    CONSTRAINT ui_message_definitions_context_not_blank CHECK (btrim(context_group)<>''),
    CONSTRAINT ui_message_definitions_default_not_blank CHECK (btrim(default_text)<>''),
    CONSTRAINT ui_message_definitions_meaning_not_blank CHECK (btrim(semantic_meaning)<>''),
    CONSTRAINT ui_message_definitions_guidance_not_blank CHECK (btrim(translator_guidance)<>''),
    CONSTRAINT ui_message_definitions_role_not_blank CHECK (btrim(grammatical_role)<>''),
    CONSTRAINT ui_message_definitions_example_not_blank CHECK (btrim(rendered_example)<>''),
    CONSTRAINT ui_message_definitions_locations_array CHECK (jsonb_typeof(common_locations)='array' AND jsonb_array_length(common_locations)>0),
    CONSTRAINT ui_message_definitions_parameter_object CHECK (jsonb_typeof(parameter_schema)='object'),
    CONSTRAINT ui_message_definitions_version_positive CHECK (version>0)
);
CREATE INDEX ui_message_definitions_context_key_idx ON ui_message_definitions(context_group,message_key);

CREATE TABLE ui_message_translations (
    message_key text NOT NULL REFERENCES ui_message_definitions(message_key) ON DELETE RESTRICT,
    language_tag text NOT NULL REFERENCES supported_languages(language_tag) ON DELETE RESTRICT,
    translated_text text NOT NULL,
    published_text text,
    status text NOT NULL DEFAULT 'draft',
    origin text NOT NULL DEFAULT 'source_copy',
    generation_metadata jsonb,
    needs_review boolean NOT NULL DEFAULT false,
    updated_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    reviewed_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    date_reviewed timestamptz,
    published_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    date_published timestamptz,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version bigint NOT NULL DEFAULT 1,
    PRIMARY KEY(message_key,language_tag),
    CONSTRAINT ui_message_translations_text_not_blank CHECK (btrim(translated_text)<>''),
    CONSTRAINT ui_message_translations_published_not_blank CHECK (published_text IS NULL OR btrim(published_text)<>''),
    CONSTRAINT ui_message_translations_status_valid CHECK (status IN ('draft','published')),
    CONSTRAINT ui_message_translations_origin_valid CHECK (origin IN ('source_copy','manual','generated','imported')),
    CONSTRAINT ui_message_translations_generation_object CHECK (generation_metadata IS NULL OR jsonb_typeof(generation_metadata)='object'),
    CONSTRAINT ui_message_translations_source_copy_not_published CHECK (origin<>'source_copy' OR published_text IS NULL),
    CONSTRAINT ui_message_translations_generated_reviewed_before_publish CHECK (origin<>'generated' OR published_text IS NULL OR (reviewed_by_user_id IS NOT NULL AND date_reviewed IS NOT NULL)),
    CONSTRAINT ui_message_translations_review_pair CHECK ((reviewed_by_user_id IS NULL)=(date_reviewed IS NULL)),
    CONSTRAINT ui_message_translations_publish_pair CHECK ((published_by_user_id IS NULL)=(date_published IS NULL)),
    CONSTRAINT ui_message_translations_version_positive CHECK (version>0)
);
CREATE INDEX ui_message_translations_language_status_idx ON ui_message_translations(language_tag,status,message_key);
CREATE INDEX ui_message_translations_language_origin_idx ON ui_message_translations(language_tag,origin,message_key);
CREATE INDEX ui_message_translations_attention_idx ON ui_message_translations(language_tag,needs_review,message_key);

CREATE FUNCTION require_localization_change_reason() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='localization_change_reason_required';
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER supported_languages_require_reason BEFORE INSERT OR UPDATE OR DELETE ON supported_languages
FOR EACH ROW EXECUTE FUNCTION require_localization_change_reason();
CREATE TRIGGER ui_message_definitions_require_reason BEFORE INSERT OR UPDATE OR DELETE ON ui_message_definitions
FOR EACH ROW EXECUTE FUNCTION require_localization_change_reason();
CREATE TRIGGER ui_message_translations_require_reason BEFORE INSERT OR UPDATE OR DELETE ON ui_message_translations
FOR EACH ROW EXECUTE FUNCTION require_localization_change_reason();

CREATE TRIGGER ui_message_definitions_touch BEFORE UPDATE ON ui_message_definitions
FOR EACH ROW EXECUTE FUNCTION touch_localization_row();
CREATE TRIGGER ui_message_translations_touch BEFORE UPDATE ON ui_message_translations
FOR EACH ROW EXECUTE FUNCTION touch_localization_row();

CREATE FUNCTION record_localization_catalogue_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_state jsonb; new_state jsonb; changed text[]; stable_key text;
BEGIN
    old_state:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END;
    new_state:=CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END;
    SELECT COALESCE(array_agg(key ORDER BY key),ARRAY[]::text[]) INTO changed
      FROM jsonb_object_keys(COALESCE(old_state,'{}'::jsonb)||COALESCE(new_state,'{}'::jsonb)) key
     WHERE old_state->key IS DISTINCT FROM new_state->key;
    stable_key:=COALESCE(new_state->>'message_key',old_state->>'message_key')||COALESCE('|'||COALESCE(new_state->>'language_tag',old_state->>'language_tag'),'');
    INSERT INTO event_history(entity_type,entity_id,operation,actor_user_id,actor_type,source,request_id,correlation_id,before_state,after_state,changed_fields,reason,metadata)
    VALUES (TG_ARGV[0],hashtextextended(stable_key,0),CASE TG_OP WHEN 'INSERT' THEN 'CREATE' ELSE TG_OP END,
      NULLIF(current_setting('app.user_id',true),'')::bigint,
      COALESCE(NULLIF(current_setting('app.actor_type',true),''),'automated_process'),
      COALESCE(NULLIF(current_setting('app.event_source',true),''),'database'),
      NULLIF(current_setting('app.request_id',true),'')::uuid,NULLIF(current_setting('app.correlation_id',true),'')::uuid,
      old_state,new_state,changed,NULLIF(current_setting('app.change_reason',true),''),
      COALESCE(NULLIF(current_setting('app.event_metadata',true),'')::jsonb,'{}'::jsonb));
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER ui_message_definitions_history AFTER INSERT OR UPDATE OR DELETE ON ui_message_definitions
FOR EACH ROW EXECUTE FUNCTION record_localization_catalogue_history('ui_message_definition');
CREATE TRIGGER ui_message_translations_history AFTER INSERT OR UPDATE OR DELETE ON ui_message_translations
FOR EACH ROW EXECUTE FUNCTION record_localization_catalogue_history('ui_message_translation');

INSERT INTO schema_migrations(version) VALUES ('020_add_ui_message_catalogue') ON CONFLICT DO NOTHING;
COMMIT;

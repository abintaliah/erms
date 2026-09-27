BEGIN;
ALTER TABLE classification_schemes ADD COLUMN translations jsonb;
ALTER TABLE classifications ADD COLUMN translations jsonb;
ALTER TABLE users ADD COLUMN description text, ADD COLUMN translations jsonb;
ALTER TABLE roles ADD COLUMN translations jsonb;
ALTER TABLE org_units ADD COLUMN translations jsonb;
ALTER TABLE security_levels ADD COLUMN description text, ADD COLUMN translations jsonb;
ALTER TABLE classification_schemes ADD CONSTRAINT classification_schemes_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
ALTER TABLE classifications ADD CONSTRAINT classifications_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
ALTER TABLE users ADD CONSTRAINT users_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
ALTER TABLE roles ADD CONSTRAINT roles_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
ALTER TABLE org_units ADD CONSTRAINT org_units_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
ALTER TABLE security_levels ADD CONSTRAINT security_levels_translations_object CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
CREATE FUNCTION validate_multilingual_entity_translations() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE locale_entry record;field_entry record;allowed_fields text[];
BEGIN
 IF NEW.translations IS NULL THEN RETURN NEW;END IF;
 allowed_fields:=CASE WHEN TG_TABLE_NAME IN ('classification_schemes','classifications') THEN ARRAY['title','description'] ELSE ARRAY['name','description'] END;
 FOR locale_entry IN SELECT key,value FROM jsonb_each(NEW.translations) LOOP
  IF locale_entry.key !~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$' OR NOT EXISTS(SELECT 1 FROM supported_languages WHERE language_tag=locale_entry.key AND is_enabled) OR jsonb_typeof(locale_entry.value)<>'object' OR locale_entry.value='{}'::jsonb THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid_entity_translation_locale',DETAIL=locale_entry.key;END IF;
  FOR field_entry IN SELECT key,value FROM jsonb_each(locale_entry.value) LOOP
   IF NOT field_entry.key=ANY(allowed_fields) OR jsonb_typeof(field_entry.value)<>'string' OR btrim(field_entry.value #>> '{}')='' OR field_entry.value #>> '{}'<>btrim(field_entry.value #>> '{}') THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid_entity_translation_field',DETAIL=locale_entry.key||'.'||field_entry.key;END IF;
  END LOOP;
 END LOOP;RETURN NEW;
END;$$;
CREATE TRIGGER classification_schemes_validate_translations BEFORE INSERT OR UPDATE OF translations ON classification_schemes FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE TRIGGER classifications_validate_translations BEFORE INSERT OR UPDATE OF translations ON classifications FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE TRIGGER users_validate_translations BEFORE INSERT OR UPDATE OF translations ON users FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE TRIGGER roles_validate_translations BEFORE INSERT OR UPDATE OF translations ON roles FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE TRIGGER org_units_validate_translations BEFORE INSERT OR UPDATE OF translations ON org_units FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE TRIGGER security_levels_validate_translations BEFORE INSERT OR UPDATE OF translations ON security_levels FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
DROP TRIGGER IF EXISTS security_levels_bump_version ON security_levels;
CREATE TRIGGER security_levels_bump_version BEFORE UPDATE ON security_levels FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE INDEX classification_schemes_translations_gin ON classification_schemes USING gin(translations jsonb_path_ops);
CREATE INDEX classifications_translations_gin ON classifications USING gin(translations jsonb_path_ops);
CREATE INDEX users_translations_gin ON users USING gin(translations jsonb_path_ops);
CREATE INDEX roles_translations_gin ON roles USING gin(translations jsonb_path_ops);
CREATE INDEX org_units_translations_gin ON org_units USING gin(translations jsonb_path_ops);
CREATE INDEX security_levels_translations_gin ON security_levels USING gin(translations jsonb_path_ops);
INSERT INTO schema_migrations(version) VALUES ('021_add_multilingual_entity_metadata') ON CONFLICT DO NOTHING;
COMMIT;

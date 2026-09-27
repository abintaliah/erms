BEGIN;

ALTER TABLE profiles ADD COLUMN translations jsonb;
ALTER TABLE profiles ADD CONSTRAINT profiles_translations_object
  CHECK (translations IS NULL OR jsonb_typeof(translations)='object');
CREATE TRIGGER profiles_validate_translations
  BEFORE INSERT OR UPDATE OF translations ON profiles
  FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
CREATE INDEX profiles_translations_gin
  ON profiles USING gin(translations jsonb_path_ops);
CREATE INDEX profiles_translation_text_trgm_idx
  ON profiles USING gin ((translations::text) gin_trgm_ops);

INSERT INTO privileges(
  code,name,description,category,is_reserved,account_type_restriction
) VALUES (
  'profile.modify_metadata',
  'Modify Profile Metadata',
  'Modify multilingual names and descriptions for authorization profiles.',
  'administration',false,'person'
) ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
  FROM profiles profile
  JOIN privileges privilege ON privilege.code='profile.modify_metadata'
 WHERE profile.code='ALL_PRIVS'
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('023_add_multilingual_profile_metadata') ON CONFLICT DO NOTHING;

COMMIT;

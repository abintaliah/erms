BEGIN;

ALTER TABLE ui_message_translations
    DROP CONSTRAINT IF EXISTS ui_message_translations_source_copy_not_published;

ALTER TABLE ui_message_translations
    DROP CONSTRAINT IF EXISTS ui_message_translations_check;

INSERT INTO schema_migrations(version)
VALUES ('027_simplify_translation_publication')
ON CONFLICT DO NOTHING;

COMMIT;

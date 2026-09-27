BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Disallow publication of non-English source-copy translations',true),
       set_config('app.event_metadata','{"migration":"028_disallow_non_source_copy_publication"}',true);

CREATE TEMP TABLE source_copy_publication_reconciliation_languages
ON COMMIT DROP
AS
SELECT DISTINCT language_tag
  FROM ui_message_translations
 WHERE lower(language_tag)<>'en'
   AND origin='source_copy'
   AND (
       status<>'draft'
       OR published_text IS NOT NULL
       OR reviewed_by_user_id IS NOT NULL
       OR date_reviewed IS NOT NULL
       OR published_by_user_id IS NOT NULL
       OR date_published IS NOT NULL
   );

UPDATE ui_message_translations
   SET status='draft',
       published_text=NULL,
       reviewed_by_user_id=NULL,
       date_reviewed=NULL,
       published_by_user_id=NULL,
       date_published=NULL,
       needs_review=false
 WHERE lower(language_tag)<>'en'
   AND origin='source_copy'
   AND (
       status<>'draft'
       OR published_text IS NOT NULL
       OR reviewed_by_user_id IS NOT NULL
       OR date_reviewed IS NOT NULL
       OR published_by_user_id IS NOT NULL
       OR date_published IS NOT NULL
   );

UPDATE supported_languages
   SET catalogue_revision=catalogue_revision+1
 WHERE language_tag IN (
       SELECT language_tag
         FROM source_copy_publication_reconciliation_languages
   );

ALTER TABLE ui_message_translations
    DROP CONSTRAINT IF EXISTS ui_message_translations_source_copy_not_published;

ALTER TABLE ui_message_translations
    ADD CONSTRAINT ui_message_translations_source_copy_not_published
    CHECK (
        lower(language_tag)='en'
        OR origin<>'source_copy'
        OR (
            status='draft'
            AND published_text IS NULL
            AND published_by_user_id IS NULL
            AND date_published IS NULL
        )
    );

INSERT INTO schema_migrations(version)
VALUES ('028_disallow_non_source_copy_publication')
ON CONFLICT DO NOTHING;

COMMIT;

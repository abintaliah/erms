BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 012',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install full-text search Phase 3 APIs and reindex batches',true),
       set_config('app.event_metadata','{"migration":"012_add_full_text_search_phase3"}',true);

INSERT INTO privileges(code,name,description,category,is_reserved,account_type_restriction)
VALUES ('record.component.reindex','Reindex Record Components',
        'Request forced indexing of an authorized component or all eligible components of an authorized record.',
        'component',false,'person')
ON CONFLICT DO NOTHING;
UPDATE privileges SET name='Reindex Record Components',
       description='Request forced indexing of an authorized component or all eligible components of an authorized record.',
       category='component',account_type_restriction='person'
 WHERE code='record.component.reindex';

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code IN ('ALL_PRIVS','SYS_ADMIN','INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code='record.component.reindex'
ON CONFLICT DO NOTHING;

CREATE TABLE content_indexing_batches (
    id uuid PRIMARY KEY,
    record_id bigint REFERENCES records(id) ON DELETE SET NULL,
    requested_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_components integer NOT NULL CHECK(total_components>=0),
    queued_count integer NOT NULL CHECK(queued_count>=0),
    already_in_progress_count integer NOT NULL CHECK(already_in_progress_count>=0),
    unavailable_count integer NOT NULL CHECK(unavailable_count>=0),
    CONSTRAINT content_indexing_batch_counts_valid CHECK (
        queued_count+already_in_progress_count+unavailable_count=total_components
    )
);

CREATE TABLE content_indexing_batch_items (
    batch_id uuid NOT NULL REFERENCES content_indexing_batches(id) ON DELETE CASCADE,
    digital_component_id bigint REFERENCES digital_components(id) ON DELETE SET NULL,
    job_id bigint REFERENCES content_indexing_jobs(id) ON DELETE SET NULL,
    disposition text NOT NULL CHECK(disposition IN ('queued','already_in_progress','unsupported_or_no_content')),
    component_identifier bigint NOT NULL,
    PRIMARY KEY(batch_id,component_identifier)
);
CREATE INDEX content_indexing_batch_items_job_idx ON content_indexing_batch_items(job_id) WHERE job_id IS NOT NULL;

INSERT INTO schema_migrations(version) VALUES ('012_add_full_text_search_phase3')
ON CONFLICT(version) DO NOTHING;

COMMIT;

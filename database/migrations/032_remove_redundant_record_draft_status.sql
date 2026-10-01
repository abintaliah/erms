BEGIN;

CREATE OR REPLACE FUNCTION current_user_owns_open_draft(p_draft_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND EXISTS(
    SELECT 1 FROM record_drafts draft
    JOIN users owner ON owner.id=draft.owner_user_id
    WHERE draft.id=p_draft_id AND draft.owner_user_id=current_user_id()
      AND draft.expires_at>CURRENT_TIMESTAMP
      AND owner.status='active')
$$;

ALTER TABLE record_drafts DROP COLUMN status;

INSERT INTO schema_migrations(version)
VALUES ('032_remove_redundant_record_draft_status')
ON CONFLICT(version) DO NOTHING;

COMMIT;

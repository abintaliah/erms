BEGIN;

-- Remove direct component targets from message links. Capture components remain unchanged.
-- Fail safely if the deployment contains unexpected component links.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM message_resource_links WHERE resource_kind='digital_component')
 OR EXISTS(SELECT 1 FROM message_draft_resource_links WHERE resource_kind='digital_component') THEN
  RAISE EXCEPTION 'Component message links exist; review them before applying migration 040';
 END IF;
END $$;
ALTER TABLE message_resource_links DROP CONSTRAINT message_resource_links_resource_kind_check;
ALTER TABLE message_resource_links DROP COLUMN digital_component_id;
ALTER TABLE message_resource_links ADD CONSTRAINT message_resource_links_resource_kind_check CHECK(resource_kind IN ('aggregation','record'));
ALTER TABLE message_resource_links ADD CONSTRAINT message_resource_links_check CHECK(num_nonnulls(aggregation_id,record_id)<=1);
ALTER TABLE message_draft_resource_links DROP CONSTRAINT message_draft_resource_links_resource_kind_check;
ALTER TABLE message_draft_resource_links DROP COLUMN digital_component_id;
ALTER TABLE message_draft_resource_links ADD CONSTRAINT message_draft_resource_links_resource_kind_check CHECK(resource_kind IN ('aggregation','record'));
ALTER TABLE message_draft_resource_links ADD CONSTRAINT message_draft_resource_links_check CHECK(num_nonnulls(aggregation_id,record_id)<=1);
CREATE OR REPLACE FUNCTION messaging_resource_link_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF num_nonnulls(NEW.aggregation_id,NEW.record_id)<>1
 OR (CASE NEW.resource_kind WHEN 'aggregation' THEN NEW.aggregation_id
 WHEN 'record' THEN NEW.record_id END)
 IS DISTINCT FROM NEW.target_id_snapshot THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_resource_target_mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION messaging_resource_link_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['aggregation_id','record_id'])
 IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['aggregation_id','record_id'])
 OR num_nonnulls(NEW.aggregation_id,NEW.record_id)<>0
 OR EXISTS(SELECT 1 FROM aggregations WHERE id=OLD.aggregation_id)
 OR EXISTS(SELECT 1 FROM records WHERE id=OLD.record_id) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_resource_link_immutable';
 END IF;
 RETURN NEW;
END $$;

INSERT INTO schema_migrations(version) VALUES ('040_message_record_aggregation_links');
COMMIT;

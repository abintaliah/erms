BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 031', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Allow governed security-level-only changes on closed resources', true);

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN PERFORM assert_aggregation_effectively_open(NEW.aggregation_id); RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN OLD; END IF;
 IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
 IF current_setting('app.review_date_change_authorized',true)='authorized' AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN RETURN NEW; END IF;
 IF current_setting('app.security_level_change_authorized',true)='authorized' AND NEW.security_level_id IS DISTINCT FROM OLD.security_level_id AND (to_jsonb(NEW)-'security_level_id'-'version')=(to_jsonb(OLD)-'security_level_id'-'version') THEN RETURN NEW; END IF;
 PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE closure_source_id bigint;
BEGIN
 IF TG_OP='INSERT' THEN IF NEW.parent_aggregation_id IS NOT NULL THEN PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id); END IF; RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.id); RETURN OLD; END IF;
 WITH RECURSIVE ancestors AS (
   SELECT id,parent_aggregation_id,date_closed,0 depth FROM aggregations WHERE id=OLD.id
   UNION ALL
   SELECT parent.id,parent.parent_aggregation_id,parent.date_closed,child.depth+1 FROM aggregations parent JOIN ancestors child ON parent.id=child.parent_aggregation_id
 ) SELECT id INTO closure_source_id FROM ancestors WHERE date_closed IS NOT NULL ORDER BY depth LIMIT 1;
 IF closure_source_id IS NOT NULL THEN
  IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
  IF current_setting('app.location_change_authorized',true)='authorized' AND (NEW.assigned_location IS DISTINCT FROM OLD.assigned_location OR NEW.current_location IS DISTINCT FROM OLD.current_location) AND (to_jsonb(NEW)-'assigned_location'-'current_location'-'version')=(to_jsonb(OLD)-'assigned_location'-'current_location'-'version') THEN RETURN NEW; END IF;
  IF current_setting('app.review_date_change_authorized',true)='authorized' AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN RETURN NEW; END IF;
  IF current_setting('app.security_level_change_authorized',true)='authorized' AND NEW.security_level_id IS DISTINCT FROM OLD.security_level_id AND (to_jsonb(NEW)-'security_level_id'-'version')=(to_jsonb(OLD)-'security_level_id'-'version') THEN RETURN NEW; END IF;
  IF closure_source_id=OLD.id AND OLD.date_closed IS NOT NULL AND NEW.date_closed IS NULL AND (to_jsonb(NEW)-'date_closed'-'version')=(to_jsonb(OLD)-'date_closed'-'version') THEN RETURN NEW; END IF;
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='closed aggregation metadata is immutable';
 END IF; RETURN NEW;
END; $$;

INSERT INTO schema_migrations(version)
VALUES ('031_allow_governed_security_changes_on_closed_resources')
ON CONFLICT(version) DO NOTHING;

COMMIT;

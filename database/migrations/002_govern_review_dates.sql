BEGIN;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS is_vital boolean NOT NULL DEFAULT false;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS date_of_next_review timestamptz;
INSERT INTO privileges(code,name,description,category,is_reserved) VALUES
 ('aggregation.review_date.change','Change Aggregation Review Date','Governed scheduling or clearing of an aggregation review date.','aggregation',false),
 ('record.review_date.change','Change Record Review Date','Governed scheduling or clearing of a record review date.','record',false) ON CONFLICT DO NOTHING;
INSERT INTO permissions(code,name,description,resource_type) VALUES
 ('aggregation.review_date.change','Change Aggregation Review Date','Governed scheduling or clearing of an aggregation review date.','aggregation'),
 ('record.review_date.change','Change Record Review Date','Governed scheduling or clearing of a record review date.','record') ON CONFLICT DO NOTHING;
INSERT INTO privilege_dependencies(privilege_id,required_privilege_id) SELECT d.id,r.id FROM privileges d JOIN privileges r ON r.code=CASE WHEN d.code LIKE 'aggregation.%' THEN 'aggregation.view' ELSE 'record.view' END WHERE d.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;
INSERT INTO permission_dependencies(permission_id,required_permission_id) SELECT d.id,r.id FROM permissions d JOIN permissions r ON r.code=CASE WHEN d.resource_type='aggregation' THEN 'aggregation.view' ELSE 'record.view' END WHERE d.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id) SELECT p.id,v.id FROM profiles p CROSS JOIN privileges v WHERE p.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER') AND v.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;

CREATE TRIGGER record_drafts_enforce_future_review_date BEFORE INSERT OR UPDATE OF date_of_next_review ON record_drafts FOR EACH ROW EXECUTE FUNCTION enforce_future_review_date();

CREATE OR REPLACE FUNCTION allow_governed_review_date_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (current_setting('app.review_date_change_authorized',true)<>'authorized' OR NULLIF(btrim(current_setting('app.change_reason',true)), '') IS NULL) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='review_date_change_requires_governed_authorization_and_reason'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER aggregations_govern_review_date BEFORE UPDATE OF date_of_next_review ON aggregations FOR EACH ROW EXECUTE FUNCTION allow_governed_review_date_change();
CREATE TRIGGER records_govern_review_date BEFORE UPDATE OF date_of_next_review ON records FOR EACH ROW EXECUTE FUNCTION allow_governed_review_date_change();

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN PERFORM assert_aggregation_effectively_open(NEW.aggregation_id); RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN OLD; END IF;
 IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
 IF current_setting('app.review_date_change_authorized',true)='authorized' AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN RETURN NEW; END IF;
 PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE closure_source_id bigint;
BEGIN
 IF TG_OP='INSERT' THEN IF NEW.parent_aggregation_id IS NOT NULL THEN PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id); END IF; RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.id); RETURN OLD; END IF;
 WITH RECURSIVE ancestors AS (SELECT id,parent_aggregation_id,date_closed,0 depth FROM aggregations WHERE id=OLD.id UNION ALL SELECT p.id,p.parent_aggregation_id,p.date_closed,a.depth+1 FROM aggregations p JOIN ancestors a ON p.id=a.parent_aggregation_id) SELECT id INTO closure_source_id FROM ancestors WHERE date_closed IS NOT NULL ORDER BY depth LIMIT 1;
 IF closure_source_id IS NOT NULL THEN
  IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
  IF current_setting('app.location_change_authorized',true)='authorized' AND (NEW.assigned_location IS DISTINCT FROM OLD.assigned_location OR NEW.current_location IS DISTINCT FROM OLD.current_location) AND (to_jsonb(NEW)-'assigned_location'-'current_location'-'version')=(to_jsonb(OLD)-'assigned_location'-'current_location'-'version') THEN RETURN NEW; END IF;
  IF current_setting('app.review_date_change_authorized',true)='authorized' AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN RETURN NEW; END IF;
  IF closure_source_id=OLD.id AND OLD.date_closed IS NOT NULL AND NEW.date_closed IS NULL AND (to_jsonb(NEW)-'date_closed'-'version')=(to_jsonb(OLD)-'date_closed'-'version') THEN RETURN NEW; END IF;
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='closed aggregation metadata is immutable';
 END IF; RETURN NEW;
END; $$;
COMMIT;

BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 047',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Expose organizational ownership in authorized search views',true),
       set_config('app.event_metadata','{"migration":"047_expose_organizational_ownership_in_search"}',true);

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL
                  OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,
       resource.description,resource.date_created,resource.date_opened,resource.date_closed,
       resource.security_level_id,resource.inherit_acl_from_parent,
       resource.default_child_aggregation_acl_mode,resource.resource_acl_version,
       resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version,
       resource.owning_org_unit_id
FROM aggregations resource;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id)
            THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,
       resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,
       resource.resource_acl_version,resource.version,resource.owning_org_unit_id
FROM records resource;

INSERT INTO schema_migrations(version)
VALUES ('047_expose_organizational_ownership_in_search');

COMMIT;

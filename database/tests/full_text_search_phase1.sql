BEGIN;

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'Phase 1 verification requires PostgreSQL 18 or newer';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config config
        JOIN pg_namespace namespace ON namespace.oid=config.cfgnamespace
        WHERE namespace.nspname='pg_catalog' AND config.cfgname='arabic'
    ) THEN
        RAISE EXCEPTION 'pg_catalog.arabic is unavailable';
    END IF;
    IF to_tsvector('pg_catalog.arabic','الميزانية المعتمدة والمصروفات')
       @@ websearch_to_tsquery('pg_catalog.arabic','الميزانية') IS NOT TRUE THEN
        RAISE EXCEPTION 'representative Arabic vector/query matching failed';
    END IF;
END;
$$;

INSERT INTO org_units(code,name) VALUES ('FTS-P1-OU','Phase 1 test unit');
INSERT INTO classification_schemes(code,title,date_published)
VALUES ('FTS-P1-CS','Phase 1 scheme',CURRENT_TIMESTAMP);
INSERT INTO classifications(classification_scheme_id,code,title,is_terminal)
SELECT id,'FTS-P1-C','Phase 1 class',true FROM classification_schemes WHERE code='FTS-P1-CS';
INSERT INTO classification_retention_rules(
    classification_id,current_period_years,intermediate_period_years,final_disposition
)
SELECT id,1,1,'destruction' FROM classifications WHERE code='FTS-P1-C';
INSERT INTO aggregations(
    aggregation_number,title,description,owning_org_unit_id,classification_id
)
SELECT 'FTS-P1-A','Alpha registry','secondary details',org_unit.id,classification.id
FROM org_units org_unit CROSS JOIN classifications classification
WHERE org_unit.code='FTS-P1-OU' AND classification.code='FTS-P1-C';
INSERT INTO records(aggregation_id,record_number,title,description,owning_org_unit_id)
SELECT aggregation.id,'FTS-P1-R','Bravo record','supporting notes',aggregation.owning_org_unit_id
FROM aggregations aggregation WHERE aggregation.aggregation_number='FTS-P1-A';

DO $$
DECLARE
    aggregation_document aggregation_search_documents%ROWTYPE;
    record_document record_search_documents%ROWTYPE;
BEGIN
    SELECT document.* INTO STRICT aggregation_document
    FROM aggregation_search_documents document
    JOIN aggregations aggregation ON aggregation.id=document.aggregation_id
    WHERE aggregation.aggregation_number='FTS-P1-A';
    SELECT document.* INTO STRICT record_document
    FROM record_search_documents document
    JOIN records record ON record.id=document.record_id
    WHERE record.record_number='FTS-P1-R';
    IF aggregation_document.text_search_config<>'pg_catalog.simple'::regconfig
       OR record_document.text_search_config<>'pg_catalog.simple'::regconfig
       OR aggregation_document.index_config_version<>'fts-metadata-v1'
       OR record_document.index_config_version<>'fts-metadata-v1' THEN
        RAISE EXCEPTION 'metadata index configuration provenance is incorrect';
    END IF;
    IF aggregation_document.search_vector::text NOT LIKE '%''alpha'':%A%'
       OR aggregation_document.search_vector::text NOT LIKE '%''details'':%B%'
       OR record_document.search_vector::text NOT LIKE '%''bravo'':%A%'
       OR record_document.search_vector::text NOT LIKE '%''supporting'':%B%' THEN
        RAISE EXCEPTION 'metadata weights are incorrect';
    END IF;
    IF ts_rank(setweight(to_tsvector('pg_catalog.simple','priority'),'A'),
               to_tsquery('pg_catalog.simple','priority'))
       <= ts_rank(setweight(to_tsvector('pg_catalog.simple','priority'),'B'),
                  to_tsquery('pg_catalog.simple','priority')) THEN
        RAISE EXCEPTION 'weight A does not rank above weight B';
    END IF;
    IF (SELECT count(*) FROM authorized_record_search_documents)<>0
       OR (SELECT count(*) FROM authorized_aggregation_search_documents)<>0 THEN
        RAISE EXCEPTION 'authorization-filtered metadata relations exposed unauthenticated rows';
    END IF;
    IF (SELECT count(*) FROM pg_indexes
        WHERE indexname IN ('record_search_documents_vector_gin',
                            'aggregation_search_documents_vector_gin')
          AND indexdef LIKE '%USING gin (search_vector)%')<>2 THEN
        RAISE EXCEPTION 'metadata GIN indexes are missing or unusable';
    END IF;
END;
$$;

UPDATE records SET title='Charlie record' WHERE record_number='FTS-P1-R';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM record_search_documents document
        JOIN records record ON record.id=document.record_id
        WHERE record.record_number='FTS-P1-R'
          AND document.search_vector @@ to_tsquery('pg_catalog.simple','charlie:A')
    ) THEN
        RAISE EXCEPTION 'record metadata trigger did not synchronize the document';
    END IF;
END;
$$;

DO $$
DECLARE
    text_profile_id bigint;
    content_privilege_id bigint;
BEGIN
    SELECT id INTO STRICT text_profile_id FROM profiles WHERE code='TEXT_INDEXER_SERVICE';
    SELECT id INTO STRICT content_privilege_id FROM privileges WHERE code='content.index.execute';
    IF (SELECT array_agg(privilege_id ORDER BY privilege_id)
        FROM profile_privileges WHERE profile_id=text_profile_id)
       IS DISTINCT FROM ARRAY[content_privilege_id] THEN
        RAISE EXCEPTION 'TEXT_INDEXER_SERVICE privilege membership is not exact';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM profile_privileges membership
        JOIN profiles profile ON profile.id=membership.profile_id
        JOIN privileges privilege ON privilege.id=membership.privilege_id
        WHERE profile.code='ALL_PRIVS' AND privilege.code='content.index.execute'
    ) THEN
        RAISE EXCEPTION 'ALL_PRIVS does not include content.index.execute';
    END IF;
    IF (SELECT count(*) FROM profile_privileges membership
        JOIN profiles profile ON profile.id=membership.profile_id
        JOIN privileges privilege ON privilege.id=membership.privilege_id
        WHERE privilege.code='search.query.debug'
          AND profile.code IN ('ALL_PRIVS','SYS_ADMIN','INFO_GOV_MGR','INFO_GOV_OFFICER'))<>4 THEN
        RAISE EXCEPTION 'search.query.debug grants are incomplete';
    END IF;
END;
$$;

INSERT INTO users(name,external_id,account_type)
VALUES ('Phase 1 worker','fts-phase1-worker','service'),
       ('Phase 1 person','fts-phase1-person','person');
INSERT INTO user_role_assignments(user_id,role_id)
SELECT account.id,role.id FROM users account CROSS JOIN roles role
WHERE account.external_id='fts-phase1-worker' AND role.code='text-indexer-service';

DO $$
DECLARE
    person_id bigint;
    service_id bigint;
    service_role_id bigint;
BEGIN
    SELECT id INTO STRICT person_id FROM users WHERE external_id='fts-phase1-person';
    SELECT id INTO STRICT service_id FROM users WHERE external_id='fts-phase1-worker';
    SELECT id INTO STRICT service_role_id FROM roles WHERE code='text-indexer-service';
    IF NOT user_has_global_privilege(service_id,'content.index.execute') THEN
        RAISE EXCEPTION 'active service assignment does not grant content.index.execute';
    END IF;
    BEGIN
        INSERT INTO user_role_assignments(user_id,role_id) VALUES(person_id,service_role_id);
        RAISE EXCEPTION 'person assignment to service role unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM NOT LIKE '%account type restriction%' THEN RAISE; END IF;
    END;
    INSERT INTO service_account_credentials(
        service_user_id,name,credential_identifier,secret_hash,expires_at,created_by_user_id
    ) VALUES (
        service_id,'Phase 1 key','01K5ABCDEFGHJKMNPQRSTVWXYZ',repeat('a',64),
        CURRENT_TIMESTAMP+interval '1 day',person_id
    );
    BEGIN
        INSERT INTO user_credentials(user_id,password_hash) VALUES(service_id,'not-allowed');
        RAISE EXCEPTION 'service account password unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM NOT LIKE '%cannot have interactive passwords%' THEN RAISE; END IF;
    END;
END;
$$;

DELETE FROM records WHERE record_number='FTS-P1-R';
DELETE FROM aggregations WHERE aggregation_number='FTS-P1-A';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM record_search_documents)
       OR EXISTS (SELECT 1 FROM aggregation_search_documents) THEN
        RAISE EXCEPTION 'metadata index rows did not cascade on source deletion';
    END IF;
END;
$$;

ROLLBACK;

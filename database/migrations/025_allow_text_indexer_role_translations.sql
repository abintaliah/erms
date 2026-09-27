BEGIN;

CREATE OR REPLACE FUNCTION protect_text_indexer_role()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code='text-indexer-service' AND OLD.is_system THEN
        IF TG_OP='UPDATE' THEN
            IF ROW(
                NEW.id,NEW.org_unit_id,NEW.supervisor_role_id,NEW.code,NEW.name,
                NEW.description,NEW.date_created,NEW.date_deactivated,
                NEW.security_level_id,NEW.profile_id,NEW.is_information_governance,
                NEW.is_system,NEW.account_type_restriction
            ) IS NOT DISTINCT FROM ROW(
                OLD.id,OLD.org_unit_id,OLD.supervisor_role_id,OLD.code,OLD.name,
                OLD.description,OLD.date_created,OLD.date_deactivated,
                OLD.security_level_id,OLD.profile_id,OLD.is_information_governance,
                OLD.is_system,OLD.account_type_restriction
            ) THEN
                RETURN NEW;
            END IF;
        END IF;
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='text-indexer-service role is protected';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('025_allow_text_indexer_role_translations')
ON CONFLICT DO NOTHING;

COMMIT;

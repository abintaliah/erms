BEGIN;

CREATE OR REPLACE FUNCTION protect_text_indexer_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code='TEXT_INDEXER_SERVICE' THEN
        IF TG_OP='UPDATE' THEN
            IF ROW(
                NEW.id,NEW.code,NEW.name,NEW.description,NEW.is_system,
                NEW.date_created
            ) IS NOT DISTINCT FROM ROW(
                OLD.id,OLD.code,OLD.name,OLD.description,OLD.is_system,
                OLD.date_created
            ) THEN
                RETURN NEW;
            END IF;
        END IF;
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='TEXT_INDEXER_SERVICE profile is protected';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('026_allow_text_indexer_profile_translations')
ON CONFLICT DO NOTHING;

COMMIT;

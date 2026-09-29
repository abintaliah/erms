BEGIN;

CREATE COLLATION erms_code_natural (provider = icu, locale = 'und-u-kn-true');

INSERT INTO schema_migrations(version)
VALUES ('029_organization_tree_ordering')
ON CONFLICT DO NOTHING;

COMMIT;

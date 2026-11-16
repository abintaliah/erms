BEGIN;
-- Old reports deliberately remain without endpoint metadata until a heartbeat
-- updates them or the runtime 24-hour retirement policy removes them.
ALTER TABLE messaging_gateway_health
 ADD COLUMN host_addresses inet[],
 ADD COLUMN api_port integer CHECK (api_port BETWEEN 1 AND 65535);
INSERT INTO schema_migrations(version)
 VALUES ('045_messaging_gateway_health_lifecycle');
COMMIT;

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_favourite_aggregations (
    user_id       bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    aggregation_id bigint NOT NULL REFERENCES aggregations (id) ON DELETE CASCADE,
    date_created  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, aggregation_id)
);

CREATE INDEX user_favourite_aggregations_aggregation_id_idx
    ON user_favourite_aggregations (aggregation_id);
CREATE INDEX user_favourite_aggregations_user_created_idx
    ON user_favourite_aggregations (user_id, date_created DESC, aggregation_id);

CREATE TABLE user_favourite_records (
    user_id      bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    record_id    bigint NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, record_id)
);

CREATE INDEX user_favourite_records_record_id_idx
    ON user_favourite_records (record_id);
CREATE INDEX user_favourite_records_user_created_idx
    ON user_favourite_records (user_id, date_created DESC, record_id);

INSERT INTO schema_migrations (version)
VALUES ('028_add_user_favourites');

COMMIT;

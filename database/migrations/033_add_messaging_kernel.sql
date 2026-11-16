BEGIN;

-- Notifications and messaging: complete storage model (specification section 7).
CREATE TABLE message_envelopes (
    id uuid PRIMARY KEY,
    sender_user_id bigint,
    sender_name text NOT NULL,
    sender_kind text NOT NULL,
    message_kind text NOT NULL,
    action_amendment_id uuid,
    system_producer_code text,
    system_configuration_version_id uuid,
    source_event_type text,
    source_event_id text,
    triggered_by_user_id bigint,
    is_test boolean NOT NULL DEFAULT false,
    test_run_id uuid,
    test_initiated_by_user_id bigint,
    subject text NOT NULL,
    priority text NOT NULL DEFAULT 'normal',
    body_rich_text text NOT NULL,
    security_level_id bigint NOT NULL,
    action_required boolean NOT NULL,
    action_due_date date,
    action_due_timezone text,
    action_due_at timestamptz,
    read_receipt_requested boolean NOT NULL,
    relationship_kind text,
    related_delivery_id uuid,
    related_envelope_id uuid,
    sent_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    sender_deleted_at timestamptz,
    sender_purge_after timestamptz,
    request_id uuid NOT NULL
 );

CREATE TABLE message_envelope_localizations (
    envelope_id uuid NOT NULL,
    language_tag text NOT NULL,
    subject text NOT NULL,
    body_rich_text text NOT NULL,
    direction text NOT NULL,
    rendered_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
 );

CREATE TABLE message_recipient_selectors (
    id bigserial PRIMARY KEY,
    envelope_id uuid NOT NULL,
    recipient_type text NOT NULL,
    selector_kind text NOT NULL,
    user_id bigint,
    role_id bigint,
    org_unit_id bigint,
    display_name text NOT NULL,
    ordinal integer NOT NULL
 );

CREATE TABLE message_addressees (
    envelope_id uuid NOT NULL,
    user_id bigint NOT NULL,
    recipient_name text NOT NULL,
    recipient_type text NOT NULL,
    ordinal integer NOT NULL
 );

CREATE TABLE message_mailboxes (
    user_id bigint PRIMARY KEY,
    last_sequence bigint NOT NULL DEFAULT 0
 );

CREATE TABLE message_deliveries (
    id uuid PRIMARY KEY,
    envelope_id uuid NOT NULL,
    recipient_user_id bigint NOT NULL,
    recipient_type text NOT NULL,
    mailbox_sequence bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    language_tag_at_send text NOT NULL,
    read_at timestamptz,
    deleted_at timestamptz,
    purge_after timestamptz,
    deletion_reason text
 );

CREATE TABLE message_action_completions (
    original_delivery_id uuid PRIMARY KEY,
    reply_envelope_id uuid NOT NULL,
    completed_by_user_id bigint NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
 );

CREATE TABLE message_action_amendments (
    id uuid PRIMARY KEY,
    original_envelope_id uuid NOT NULL,
    sequence integer NOT NULL,
    amendment_kind text NOT NULL,
    previous_action_required boolean NOT NULL,
    previous_due_date date,
    previous_due_timezone text,
    previous_due_at timestamptz,
    new_action_required boolean NOT NULL,
    new_due_date date,
    new_due_timezone text,
    new_due_at timestamptz,
    reason text NOT NULL,
    created_by_user_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_id uuid NOT NULL
 );

CREATE TABLE message_resource_links (
    id bigserial PRIMARY KEY,
    envelope_id uuid NOT NULL,
    link_token uuid NOT NULL,
    ordinal integer NOT NULL,
    resource_kind text NOT NULL,
    target_id_snapshot bigint NOT NULL,
    aggregation_id bigint,
    record_id bigint,
    digital_component_id bigint,
    security_level_id_at_send bigint NOT NULL
 );

CREATE TABLE message_drafts (
    id uuid PRIMARY KEY,
    owner_user_id bigint NOT NULL,
    subject text,
    priority text NOT NULL DEFAULT 'normal',
    body_rich_text text,
    security_level_id bigint NOT NULL,
    action_required boolean NOT NULL,
    action_due_date date,
    action_due_timezone text,
    read_receipt_requested boolean NOT NULL,
    relationship_kind text,
    related_delivery_id uuid,
    related_envelope_id uuid,
    version bigint NOT NULL DEFAULT 1,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    deleted_at timestamptz,
    purge_after timestamptz,
    deletion_reason text
 );

CREATE TABLE message_record_captures (
    id uuid PRIMARY KEY,
    selected_envelope_id uuid,
    selected_envelope_id_at_capture uuid NOT NULL,
    record_id bigint,
    record_id_at_capture bigint NOT NULL,
    captured_by_user_id bigint NOT NULL,
    captured_by_name text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
 );

CREATE TABLE message_record_capture_components (
    id bigserial PRIMARY KEY,
    capture_id uuid NOT NULL,
    component_kind text NOT NULL,
    envelope_id uuid,
    envelope_id_at_capture uuid,
    digital_component_id bigint,
    digital_component_id_at_capture bigint NOT NULL,
    component_order integer NOT NULL,
    is_selected_message boolean NOT NULL
 );

CREATE TABLE system_notification_producers (
    producer_code text PRIMARY KEY,
    feature_code text NOT NULL,
    event_type text NOT NULL,
    required_for_business_commit boolean NOT NULL,
    contract_version integer NOT NULL,
    contract_definition jsonb NOT NULL,
    active_configuration_version_id uuid
 );

CREATE TABLE system_notification_configuration_versions (
    id uuid PRIMARY KEY,
    producer_code text NOT NULL,
    version integer NOT NULL,
    enabled boolean NOT NULL,
    subject_template text NOT NULL,
    body_template_rich_text text NOT NULL,
    priority text NOT NULL DEFAULT 'normal',
    audience_mode text NOT NULL,
    resource_presentation jsonb NOT NULL,
    operational_owner text NOT NULL,
    change_reason text NOT NULL,
    created_by_user_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
 );

CREATE TABLE system_notification_configuration_translations (
    configuration_version_id uuid NOT NULL,
    language_tag text NOT NULL,
    subject_template text NOT NULL,
    body_template_rich_text text NOT NULL,
    review_status text NOT NULL,
    reviewed_by_user_id bigint,
    reviewed_at timestamptz
 );

CREATE TABLE message_request_receipts (
    id bigserial PRIMARY KEY,
    operation_kind text NOT NULL,
    principal_user_id bigint,
    producer_code text,
    request_id uuid NOT NULL,
    request_fingerprint text NOT NULL,
    source_event_type text,
    source_event_id text,
    result_envelope_id uuid NOT NULL,
    result_amendment_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    result_purged_at timestamptz
 );

CREATE TABLE message_draft_recipient_selectors (
    id bigserial PRIMARY KEY,
    draft_id uuid NOT NULL,
    recipient_type text NOT NULL,
    selector_kind text NOT NULL,
    user_id bigint,
    role_id bigint,
    org_unit_id bigint,
    display_name text NOT NULL,
    ordinal integer NOT NULL
 );

CREATE TABLE message_draft_resource_links (
    id bigserial PRIMARY KEY,
    draft_id uuid NOT NULL,
    link_token uuid NOT NULL,
    ordinal integer NOT NULL,
    resource_kind text NOT NULL,
    target_id_snapshot bigint NOT NULL,
    aggregation_id bigint,
    record_id bigint,
    digital_component_id bigint,
    security_level_id_at_send bigint NOT NULL
 );

CREATE TABLE system_notification_configuration_audiences (
    id bigserial PRIMARY KEY,
    configuration_version_id uuid NOT NULL,
    recipient_type text NOT NULL,
    selector_kind text NOT NULL,
    user_id bigint,
    role_id bigint,
    org_unit_id bigint,
    display_name text NOT NULL,
    ordinal integer NOT NULL
 );

ALTER TABLE message_envelopes ADD FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_envelopes ADD FOREIGN KEY (action_amendment_id) REFERENCES message_action_amendments(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelopes ADD FOREIGN KEY (system_producer_code) REFERENCES system_notification_producers(producer_code) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelopes ADD FOREIGN KEY (system_configuration_version_id) REFERENCES system_notification_configuration_versions(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelopes ADD FOREIGN KEY (triggered_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_envelopes ADD FOREIGN KEY (test_initiated_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_envelopes ADD FOREIGN KEY (security_level_id) REFERENCES security_levels(id) ON DELETE RESTRICT;
ALTER TABLE message_envelopes ADD FOREIGN KEY (related_delivery_id) REFERENCES message_deliveries(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelopes ADD FOREIGN KEY (related_envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelope_localizations ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelope_localizations ADD FOREIGN KEY (language_tag) REFERENCES supported_languages(language_tag) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_recipient_selectors ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_recipient_selectors ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_recipient_selectors ADD FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_recipient_selectors ADD FOREIGN KEY (org_unit_id) REFERENCES org_units(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_addressees ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_addressees ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_mailboxes ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_deliveries ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_deliveries ADD FOREIGN KEY (recipient_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_action_completions ADD FOREIGN KEY (original_delivery_id) REFERENCES message_deliveries(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_action_completions ADD FOREIGN KEY (reply_envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_action_completions ADD FOREIGN KEY (completed_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_action_amendments ADD FOREIGN KEY (original_envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_action_amendments ADD FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_resource_links ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_resource_links ADD FOREIGN KEY (aggregation_id) REFERENCES aggregations(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_resource_links ADD FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_resource_links ADD FOREIGN KEY (digital_component_id) REFERENCES digital_components(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_resource_links ADD FOREIGN KEY (security_level_id_at_send) REFERENCES security_levels(id) ON DELETE RESTRICT;
ALTER TABLE message_drafts ADD FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_drafts ADD FOREIGN KEY (security_level_id) REFERENCES security_levels(id) ON DELETE RESTRICT;
ALTER TABLE message_record_captures ADD FOREIGN KEY (selected_envelope_id) REFERENCES message_envelopes(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_record_captures ADD FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_record_captures ADD FOREIGN KEY (captured_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_record_capture_components ADD FOREIGN KEY (capture_id) REFERENCES message_record_captures(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_record_capture_components ADD FOREIGN KEY (envelope_id) REFERENCES message_envelopes(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_record_capture_components ADD FOREIGN KEY (digital_component_id) REFERENCES digital_components(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_producers ADD FOREIGN KEY (active_configuration_version_id) REFERENCES system_notification_configuration_versions(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_versions ADD FOREIGN KEY (producer_code) REFERENCES system_notification_producers(producer_code) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_versions ADD FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE system_notification_configuration_translations ADD FOREIGN KEY (configuration_version_id) REFERENCES system_notification_configuration_versions(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_translations ADD FOREIGN KEY (language_tag) REFERENCES supported_languages(language_tag) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_translations ADD FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_request_receipts ADD FOREIGN KEY (principal_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_request_receipts ADD FOREIGN KEY (producer_code) REFERENCES system_notification_producers(producer_code) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_recipient_selectors ADD FOREIGN KEY (draft_id) REFERENCES message_drafts(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_recipient_selectors ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE message_draft_recipient_selectors ADD FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_recipient_selectors ADD FOREIGN KEY (org_unit_id) REFERENCES org_units(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_resource_links ADD FOREIGN KEY (draft_id) REFERENCES message_drafts(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_resource_links ADD FOREIGN KEY (aggregation_id) REFERENCES aggregations(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_resource_links ADD FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_resource_links ADD FOREIGN KEY (digital_component_id) REFERENCES digital_components(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_draft_resource_links ADD FOREIGN KEY (security_level_id_at_send) REFERENCES security_levels(id) ON DELETE RESTRICT;
ALTER TABLE system_notification_configuration_audiences ADD FOREIGN KEY (configuration_version_id) REFERENCES system_notification_configuration_versions(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_audiences ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE system_notification_configuration_audiences ADD FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE system_notification_configuration_audiences ADD FOREIGN KEY (org_unit_id) REFERENCES org_units(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE message_envelopes
    ADD CHECK (sender_kind IN ('user','system')),
    ADD CHECK (message_kind IN ('user_message','system_notification','action_amendment_notice')),
    ADD CHECK ((sender_kind='user')=(sender_user_id IS NOT NULL)),
    ADD CHECK ((sender_kind='system')=(message_kind='system_notification')),
    ADD CHECK ((message_kind='action_amendment_notice')=(action_amendment_id IS NOT NULL)),
    ADD UNIQUE (action_amendment_id), ADD UNIQUE (test_run_id),
    ADD CHECK ((sender_kind='system' AND system_producer_code IS NOT NULL
        AND system_configuration_version_id IS NOT NULL AND source_event_type IS NOT NULL
        AND source_event_id IS NOT NULL AND length(source_event_id) BETWEEN 1 AND 255)
        OR (sender_kind='user' AND system_producer_code IS NULL
        AND system_configuration_version_id IS NULL AND source_event_type IS NULL
        AND source_event_id IS NULL AND triggered_by_user_id IS NULL)),
    ADD CHECK ((is_test AND sender_kind='system' AND test_run_id IS NOT NULL AND test_initiated_by_user_id IS NOT NULL)
        OR (NOT is_test AND test_run_id IS NULL AND test_initiated_by_user_id IS NULL)),
    ADD CHECK (COALESCE((relationship_kind IS NULL AND related_delivery_id IS NULL AND related_envelope_id IS NULL)
        OR (relationship_kind='reply' AND related_delivery_id IS NOT NULL AND related_envelope_id IS NULL)
        OR (relationship_kind='follow_up' AND related_delivery_id IS NULL AND related_envelope_id IS NOT NULL)
        OR (relationship_kind='forward' AND num_nonnulls(related_delivery_id,related_envelope_id)=1),false)),
    ADD CHECK (sender_deleted_at IS NULL OR sender_purge_after IS NOT NULL),
    ADD CHECK (sender_kind='user' OR (sender_deleted_at IS NULL AND sender_purge_after IS NULL)),
    ADD CHECK (expires_at>sent_at),
    ADD CHECK (btrim(sender_name)<>''),
    ADD CHECK (char_length(subject) BETWEEN 1 AND 255 AND btrim(subject)<>''),
    ADD CHECK (priority IN ('normal','high','very_high')),
    ADD CHECK (octet_length(body_rich_text)<=65536),
    ADD CHECK (num_nonnulls(action_due_date,action_due_timezone,action_due_at) IN (0,3)),
    ADD CHECK (action_required IS TRUE OR action_due_date IS NULL),
    ADD CHECK (sender_kind<>'system' OR (sender_name='system' AND NOT action_required AND NOT read_receipt_requested)),
    ADD CHECK (message_kind<>'action_amendment_notice' OR
        (relationship_kind IS NULL AND NOT is_test AND NOT action_required AND NOT read_receipt_requested));
CREATE UNIQUE INDEX message_envelopes_user_request_idx ON message_envelopes(sender_user_id,request_id) WHERE sender_kind='user';
CREATE UNIQUE INDEX message_envelopes_system_request_idx ON message_envelopes(system_producer_code,request_id) WHERE sender_kind='system';
CREATE UNIQUE INDEX message_envelopes_system_event_idx ON message_envelopes(system_producer_code,source_event_type,source_event_id) WHERE sender_kind='system' AND NOT is_test;
CREATE INDEX message_envelopes_outbox_idx ON message_envelopes(sender_user_id,sent_at DESC,id DESC) WHERE sender_deleted_at IS NULL AND message_kind='user_message';
CREATE INDEX message_envelopes_expiry_idx ON message_envelopes(expires_at,id);
ALTER TABLE message_envelope_localizations ADD PRIMARY KEY(envelope_id,language_tag),
    ADD CHECK(direction IN ('ltr','rtl')), ADD CHECK(char_length(subject) BETWEEN 1 AND 255 AND btrim(subject)<>''),
    ADD CHECK(octet_length(body_rich_text)<=65536);
ALTER TABLE message_addressees ADD PRIMARY KEY(envelope_id,user_id),
    ADD UNIQUE(envelope_id,user_id,recipient_type), ADD UNIQUE(envelope_id,recipient_type,ordinal),
    ADD CHECK(recipient_type IN ('to','cc')), ADD CHECK(ordinal>=0), ADD CHECK(btrim(recipient_name)<>'');
ALTER TABLE message_mailboxes ADD CHECK(last_sequence>=0);
ALTER TABLE message_deliveries ADD UNIQUE(envelope_id,recipient_user_id), ADD UNIQUE(recipient_user_id,mailbox_sequence),
    ADD FOREIGN KEY(envelope_id,recipient_user_id,recipient_type) REFERENCES message_addressees(envelope_id,user_id,recipient_type),
    ADD CHECK(mailbox_sequence>0), ADD CHECK(recipient_type IN ('to','cc')),
    ADD CHECK((deleted_at IS NULL AND deletion_reason IS NULL)
        OR (deleted_at IS NOT NULL AND purge_after IS NOT NULL AND deletion_reason IS NOT NULL AND deletion_reason IN ('user_deleted','retention_expired')));
CREATE INDEX message_deliveries_inbox_idx ON message_deliveries(recipient_user_id,deleted_at,read_at,created_at DESC,id);
CREATE INDEX message_deliveries_page_idx ON message_deliveries(recipient_user_id,mailbox_sequence DESC) WHERE deleted_at IS NULL;
ALTER TABLE message_action_completions ADD UNIQUE(reply_envelope_id);
CREATE INDEX message_action_completions_user_idx ON message_action_completions(completed_by_user_id,completed_at DESC);
ALTER TABLE message_action_amendments ADD UNIQUE(original_envelope_id,sequence), ADD UNIQUE(created_by_user_id,request_id),
    ADD CHECK(sequence>0), ADD CHECK(amendment_kind IN ('due_date_added','due_date_changed','due_date_removed','action_withdrawn')),
    ADD CHECK(btrim(reason)<>'' AND char_length(reason)<=2000),
    ADD CHECK(num_nonnulls(previous_due_date,previous_due_timezone,previous_due_at) IN (0,3)),
    ADD CHECK(num_nonnulls(new_due_date,new_due_timezone,new_due_at) IN (0,3));
ALTER TABLE message_drafts ADD CHECK(priority IN ('normal','high','very_high')), ADD CHECK(version>0),
    ADD CHECK(subject IS NULL OR char_length(subject)<=255), ADD CHECK(body_rich_text IS NULL OR octet_length(body_rich_text)<=65536),
    ADD CHECK((action_due_date IS NULL)=(action_due_timezone IS NULL)), ADD CHECK(action_required OR action_due_date IS NULL),
    ADD CHECK(relationship_kind IS NULL OR relationship_kind IN ('reply','forward','follow_up')),
    ADD CHECK((deleted_at IS NULL AND purge_after IS NULL AND deletion_reason IS NULL)
        OR (deleted_at IS NOT NULL AND purge_after IS NOT NULL AND deletion_reason IS NOT NULL AND deletion_reason IN ('expired','discarded')));
CREATE INDEX message_drafts_owner_idx ON message_drafts(owner_user_id,date_updated DESC,id);
CREATE INDEX message_drafts_expiry_idx ON message_drafts(expires_at,id);
ALTER TABLE message_record_captures ADD UNIQUE(record_id), ADD UNIQUE(record_id_at_capture), ADD CHECK(btrim(captured_by_name)<>'');
ALTER TABLE message_record_capture_components ADD UNIQUE(digital_component_id), ADD UNIQUE(digital_component_id_at_capture),
    ADD UNIQUE(capture_id,component_order), ADD CHECK(component_order>0),
    ADD CHECK((component_kind='message' AND envelope_id_at_capture IS NOT NULL AND is_selected_message=(component_order=1))
        OR (component_kind='provenance' AND envelope_id IS NULL AND envelope_id_at_capture IS NULL AND NOT is_selected_message));
CREATE UNIQUE INDEX message_capture_provenance_idx ON message_record_capture_components(capture_id) WHERE component_kind='provenance';
CREATE UNIQUE INDEX message_capture_envelope_idx ON message_record_capture_components(capture_id,envelope_id_at_capture) WHERE component_kind='message';
ALTER TABLE system_notification_producers ADD CHECK(contract_version>0), ADD CHECK(jsonb_typeof(contract_definition)='object');
ALTER TABLE system_notification_configuration_versions ADD UNIQUE(producer_code,version), ADD UNIQUE(producer_code,id),
    ADD CHECK(version>0), ADD CHECK(priority IN ('normal','high','very_high')),
    ADD CHECK(char_length(subject_template) BETWEEN 1 AND 255 AND btrim(subject_template)<>''),
    ADD CHECK(octet_length(body_template_rich_text)<=65536), ADD CHECK(btrim(operational_owner)<>''), ADD CHECK(btrim(change_reason)<>''),
    ADD CHECK(jsonb_typeof(resource_presentation)='object');
ALTER TABLE system_notification_producers ADD FOREIGN KEY(producer_code,active_configuration_version_id)
    REFERENCES system_notification_configuration_versions(producer_code,id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE message_envelopes ADD FOREIGN KEY(system_producer_code,system_configuration_version_id)
    REFERENCES system_notification_configuration_versions(producer_code,id);
ALTER TABLE system_notification_configuration_translations ADD PRIMARY KEY(configuration_version_id,language_tag),
    ADD CHECK(review_status IN ('draft','reviewed','published')),
    ADD CHECK(review_status='draft' OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)),
    ADD CHECK(char_length(subject_template) BETWEEN 1 AND 255 AND btrim(subject_template)<>''),
    ADD CHECK(octet_length(body_template_rich_text)<=65536);

ALTER TABLE message_recipient_selectors ADD CHECK(recipient_type IN ('to','cc')), ADD CHECK(ordinal>=0),
 ADD CHECK(btrim(display_name)<>''), ADD UNIQUE(envelope_id,recipient_type,ordinal),
 ADD CHECK((selector_kind='user' AND user_id IS NOT NULL AND role_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='role' AND role_id IS NOT NULL AND user_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='org_unit' AND org_unit_id IS NOT NULL AND user_id IS NULL AND role_id IS NULL));
CREATE UNIQUE INDEX message_recipient_selectors_user_id_unique ON message_recipient_selectors(envelope_id,recipient_type,user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX message_recipient_selectors_role_id_unique ON message_recipient_selectors(envelope_id,recipient_type,role_id) WHERE role_id IS NOT NULL;
CREATE UNIQUE INDEX message_recipient_selectors_org_unit_id_unique ON message_recipient_selectors(envelope_id,recipient_type,org_unit_id) WHERE org_unit_id IS NOT NULL;

ALTER TABLE message_draft_recipient_selectors ADD CHECK(recipient_type IN ('to','cc')), ADD CHECK(ordinal>=0),
 ADD CHECK(btrim(display_name)<>''), ADD UNIQUE(draft_id,recipient_type,ordinal),
 ADD CHECK((selector_kind='user' AND user_id IS NOT NULL AND role_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='role' AND role_id IS NOT NULL AND user_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='org_unit' AND org_unit_id IS NOT NULL AND user_id IS NULL AND role_id IS NULL));
CREATE UNIQUE INDEX message_draft_recipient_selectors_user_id_unique ON message_draft_recipient_selectors(draft_id,recipient_type,user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX message_draft_recipient_selectors_role_id_unique ON message_draft_recipient_selectors(draft_id,recipient_type,role_id) WHERE role_id IS NOT NULL;
CREATE UNIQUE INDEX message_draft_recipient_selectors_org_unit_id_unique ON message_draft_recipient_selectors(draft_id,recipient_type,org_unit_id) WHERE org_unit_id IS NOT NULL;

ALTER TABLE system_notification_configuration_audiences ADD CHECK(recipient_type IN ('to','cc')), ADD CHECK(ordinal>=0),
 ADD CHECK(btrim(display_name)<>''), ADD UNIQUE(configuration_version_id,recipient_type,ordinal),
 ADD CHECK((selector_kind='user' AND user_id IS NOT NULL AND role_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='role' AND role_id IS NOT NULL AND user_id IS NULL AND org_unit_id IS NULL)
 OR (selector_kind='org_unit' AND org_unit_id IS NOT NULL AND user_id IS NULL AND role_id IS NULL));
CREATE UNIQUE INDEX system_notification_configuration_audiences_user_id_unique ON system_notification_configuration_audiences(configuration_version_id,recipient_type,user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX system_notification_configuration_audiences_role_id_unique ON system_notification_configuration_audiences(configuration_version_id,recipient_type,role_id) WHERE role_id IS NOT NULL;
CREATE UNIQUE INDEX system_notification_configuration_audiences_org_unit_id_unique ON system_notification_configuration_audiences(configuration_version_id,recipient_type,org_unit_id) WHERE org_unit_id IS NOT NULL;

ALTER TABLE message_resource_links ADD UNIQUE(envelope_id,link_token), ADD UNIQUE(envelope_id,ordinal),
 ADD CHECK(ordinal>=0), ADD CHECK(resource_kind IN ('aggregation','record','digital_component')),
 ADD CHECK(num_nonnulls(aggregation_id,record_id,digital_component_id)<=1);
CREATE INDEX message_resource_links_aggregation_id_idx ON message_resource_links(aggregation_id) WHERE aggregation_id IS NOT NULL;
CREATE INDEX message_resource_links_record_id_idx ON message_resource_links(record_id) WHERE record_id IS NOT NULL;
CREATE INDEX message_resource_links_digital_component_id_idx ON message_resource_links(digital_component_id) WHERE digital_component_id IS NOT NULL;

ALTER TABLE message_draft_resource_links ADD UNIQUE(draft_id,link_token), ADD UNIQUE(draft_id,ordinal),
 ADD CHECK(ordinal>=0), ADD CHECK(resource_kind IN ('aggregation','record','digital_component')),
 ADD CHECK(num_nonnulls(aggregation_id,record_id,digital_component_id)<=1);
CREATE INDEX message_draft_resource_links_aggregation_id_idx ON message_draft_resource_links(aggregation_id) WHERE aggregation_id IS NOT NULL;
CREATE INDEX message_draft_resource_links_record_id_idx ON message_draft_resource_links(record_id) WHERE record_id IS NOT NULL;
CREATE INDEX message_draft_resource_links_digital_component_id_idx ON message_draft_resource_links(digital_component_id) WHERE digital_component_id IS NOT NULL;

ALTER TABLE message_request_receipts ADD CHECK(operation_kind IN ('send','amendment')),
 ADD CHECK(num_nonnulls(principal_user_id,producer_code)=1),
 ADD CHECK(operation_kind<>'amendment' OR principal_user_id IS NOT NULL),
 ADD CHECK((operation_kind='amendment')=(result_amendment_id IS NOT NULL)),
 ADD CHECK(length(request_fingerprint)=64),
 ADD CHECK((source_event_type IS NULL)=(source_event_id IS NULL));
CREATE UNIQUE INDEX message_request_receipts_user_key ON message_request_receipts(operation_kind,principal_user_id,request_id) WHERE principal_user_id IS NOT NULL;
CREATE UNIQUE INDEX message_request_receipts_producer_key ON message_request_receipts(operation_kind,producer_code,request_id) WHERE producer_code IS NOT NULL;
CREATE UNIQUE INDEX message_request_receipts_event_key ON message_request_receipts(producer_code,source_event_type,source_event_id) WHERE source_event_id IS NOT NULL;
CREATE INDEX message_request_receipts_result_idx ON message_request_receipts(result_envelope_id);

-- Reuse the established effective-role and privilege predicates everywhere.
CREATE FUNCTION messaging_user_clearance(p_user bigint) RETURNS integer LANGUAGE sql STABLE AS $$
 SELECT max(l.level_number)::integer FROM users u
 JOIN user_role_assignments a ON a.user_id=u.id JOIN roles r ON r.id=a.role_id
 JOIN security_levels l ON l.id=r.security_level_id
 WHERE u.id=p_user AND u.status='active' AND u.account_type='person'
 AND a.valid_from<=CURRENT_TIMESTAMP AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
 AND role_effectively_active(r.id)
$$;
CREATE FUNCTION messaging_user_eligible(p_user bigint,p_level integer) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(messaging_user_clearance(p_user)>=p_level,false)
 AND user_has_global_privilege(p_user,'messaging.user_messages.exchange')
$$;

-- Ordinary writes cannot edit sent content. Whole-group purge is a later-phase
-- service operation; no ordinary API is granted a way to enable deletion.
CREATE FUNCTION messaging_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_immutable';
END $$;
CREATE FUNCTION messaging_delivery_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-'read_at') IS DISTINCT FROM (to_jsonb(OLD)-'read_at')
 OR (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at)
 OR NEW.read_at IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_delivery_immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION messaging_resource_link_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF num_nonnulls(NEW.aggregation_id,NEW.record_id,NEW.digital_component_id)<>1
 OR (CASE NEW.resource_kind WHEN 'aggregation' THEN NEW.aggregation_id
 WHEN 'record' THEN NEW.record_id WHEN 'digital_component' THEN NEW.digital_component_id END)
 IS DISTINCT FROM NEW.target_id_snapshot THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_resource_target_mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION messaging_resource_link_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['aggregation_id','record_id','digital_component_id'])
 IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['aggregation_id','record_id','digital_component_id'])
 OR num_nonnulls(NEW.aggregation_id,NEW.record_id,NEW.digital_component_id)<>0
 OR EXISTS(SELECT 1 FROM aggregations WHERE id=OLD.aggregation_id)
 OR EXISTS(SELECT 1 FROM records WHERE id=OLD.record_id)
 OR EXISTS(SELECT 1 FROM digital_components WHERE id=OLD.digital_component_id) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_resource_link_immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_envelopes_immutable BEFORE UPDATE OR DELETE ON message_envelopes FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_envelope_localizations_immutable BEFORE UPDATE OR DELETE ON message_envelope_localizations FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_recipient_selectors_immutable BEFORE UPDATE OR DELETE ON message_recipient_selectors FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_addressees_immutable BEFORE UPDATE OR DELETE ON message_addressees FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_action_completions_immutable BEFORE UPDATE OR DELETE ON message_action_completions FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_action_amendments_immutable BEFORE UPDATE OR DELETE ON message_action_amendments FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_request_receipts_immutable BEFORE UPDATE OR DELETE ON message_request_receipts FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER system_notification_configuration_versions_immutable BEFORE UPDATE OR DELETE ON system_notification_configuration_versions FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER system_notification_configuration_translations_immutable BEFORE UPDATE OR DELETE ON system_notification_configuration_translations FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER system_notification_configuration_audiences_immutable BEFORE UPDATE OR DELETE ON system_notification_configuration_audiences FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_deliveries_read_once BEFORE UPDATE ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_delivery_update();
CREATE TRIGGER message_deliveries_no_delete BEFORE DELETE ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_resource_links_insert BEFORE INSERT ON message_resource_links FOR EACH ROW EXECUTE FUNCTION messaging_resource_link_insert();
CREATE TRIGGER message_resource_links_update BEFORE UPDATE ON message_resource_links FOR EACH ROW EXECUTE FUNCTION messaging_resource_link_update();
CREATE TRIGGER message_resource_links_no_delete BEFORE DELETE ON message_resource_links FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();

-- Commit-time guards allow transactional fan-out, but never partial messages.
CREATE FUNCTION messaging_validate_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e message_envelopes; parent message_envelopes;
BEGIN
 SELECT * INTO e FROM message_envelopes WHERE id=NEW.id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT 1 FROM message_recipient_selectors WHERE envelope_id=e.id AND recipient_type='to')
 OR NOT EXISTS(SELECT 1 FROM message_addressees WHERE envelope_id=e.id AND recipient_type='to')
 OR EXISTS(SELECT 1 FROM message_addressees a LEFT JOIN message_deliveries d
       ON d.envelope_id=a.envelope_id AND d.recipient_user_id=a.user_id
       WHERE a.envelope_id=e.id AND (d.id IS NULL OR a.user_id=e.sender_user_id))
 OR NOT EXISTS(SELECT 1 FROM message_request_receipts WHERE result_envelope_id=e.id) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_incomplete_fanout';
 END IF;
 IF e.sender_kind='system' AND e.security_level_id<>(SELECT id FROM security_levels ORDER BY level_number LIMIT 1) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_system_level';
 END IF;
 IF e.action_due_date IS NOT NULL AND
   (NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=e.action_due_timezone)
    OR e.action_due_at IS DISTINCT FROM ((e.action_due_date+1)::timestamp AT TIME ZONE e.action_due_timezone)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_due_boundary';
 END IF;
 IF e.related_delivery_id IS NOT NULL THEN
  SELECT original.* INTO parent FROM message_envelopes original
  JOIN message_deliveries d ON d.envelope_id=original.id
  WHERE d.id=e.related_delivery_id AND d.recipient_user_id=e.sender_user_id;
 ELSIF e.related_envelope_id IS NOT NULL THEN
  SELECT * INTO parent FROM message_envelopes WHERE id=e.related_envelope_id AND sender_user_id=e.sender_user_id;
 END IF;
 IF e.relationship_kind IS NOT NULL AND (parent.id IS NULL OR parent.message_kind<>'user_message'
 OR parent.is_test OR (SELECT level_number FROM security_levels WHERE id=parent.security_level_id)>
 (SELECT level_number FROM security_levels WHERE id=e.security_level_id)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_relationship_invalid';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER message_envelope_complete AFTER INSERT ON message_envelopes
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION messaging_validate_envelope();

CREATE FUNCTION messaging_validate_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_mailboxes WHERE user_id=NEW.recipient_user_id AND last_sequence=NEW.mailbox_sequence) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_sequence_not_allocated';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_delivery_sequence BEFORE INSERT ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_validate_delivery();
CREATE FUNCTION messaging_mailbox_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.user_id<>OLD.user_id OR NEW.last_sequence<>OLD.last_sequence+1 THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_mailbox_sequence_immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_mailbox_update BEFORE UPDATE ON message_mailboxes FOR EACH ROW EXECUTE FUNCTION messaging_mailbox_update();

CREATE FUNCTION messaging_validate_completion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_deliveries d JOIN message_envelopes original ON original.id=d.envelope_id
 JOIN message_envelopes reply ON reply.id=NEW.reply_envelope_id
 WHERE d.id=NEW.original_delivery_id AND d.recipient_user_id=NEW.completed_by_user_id
 AND reply.sender_user_id=NEW.completed_by_user_id AND reply.relationship_kind='reply'
 AND reply.related_delivery_id=d.id AND original.action_required AND original.message_kind='user_message'
 AND NOT EXISTS(SELECT 1 FROM message_action_amendments a WHERE a.original_envelope_id=original.id AND NOT a.new_action_required)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_completion_invalid';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER message_completion_valid AFTER INSERT ON message_action_completions
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION messaging_validate_completion();

ALTER TABLE message_action_amendments ADD CHECK(previous_action_required),
 ADD CHECK((amendment_kind='due_date_added' AND previous_due_date IS NULL AND new_due_date IS NOT NULL AND new_action_required)
 OR (amendment_kind='due_date_changed' AND previous_due_date IS NOT NULL AND new_due_date IS NOT NULL AND new_action_required
     AND ROW(previous_due_date,previous_due_timezone,previous_due_at) IS DISTINCT FROM ROW(new_due_date,new_due_timezone,new_due_at))
 OR (amendment_kind='due_date_removed' AND previous_due_date IS NOT NULL AND new_due_date IS NULL AND new_action_required)
 OR (amendment_kind='action_withdrawn' AND NOT new_action_required AND new_due_date IS NULL));
CREATE FUNCTION messaging_validate_amendment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original message_envelopes; previous message_action_amendments;
BEGIN
 SELECT * INTO original FROM message_envelopes WHERE id=NEW.original_envelope_id FOR UPDATE;
 SELECT * INTO previous FROM message_action_amendments WHERE original_envelope_id=NEW.original_envelope_id
 AND sequence<NEW.sequence ORDER BY sequence DESC LIMIT 1;
 IF original.message_kind<>'user_message' OR NOT original.action_required OR original.sender_user_id<>NEW.created_by_user_id
 OR NEW.sequence<>COALESCE(previous.sequence,0)+1
 OR ROW(NEW.previous_action_required,NEW.previous_due_date,NEW.previous_due_timezone,NEW.previous_due_at)
 IS DISTINCT FROM ROW(COALESCE(previous.new_action_required,original.action_required),
 CASE WHEN previous.id IS NULL THEN original.action_due_date ELSE previous.new_due_date END,
 CASE WHEN previous.id IS NULL THEN original.action_due_timezone ELSE previous.new_due_timezone END,
 CASE WHEN previous.id IS NULL THEN original.action_due_at ELSE previous.new_due_at END)
 OR NOT EXISTS(SELECT 1 FROM message_envelopes WHERE action_amendment_id=NEW.id AND sender_user_id=NEW.created_by_user_id)
 THEN RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_amendment_invalid'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER message_amendment_valid AFTER INSERT ON message_action_amendments
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION messaging_validate_amendment();

CREATE FUNCTION messaging_draft_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.id<>OLD.id OR NEW.owner_user_id<>OLD.owner_user_id OR NEW.date_created<>OLD.date_created
 OR NEW.version<>OLD.version+1 THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_draft_version_invalid';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_draft_update BEFORE UPDATE ON message_drafts FOR EACH ROW EXECUTE FUNCTION messaging_draft_update();
CREATE TRIGGER message_draft_resource_target BEFORE INSERT ON message_draft_resource_links FOR EACH ROW EXECUTE FUNCTION messaging_resource_link_insert();

-- Inbox ordering is the envelope send instant plus delivery UUID. Delivery's
-- created_at is the same transaction instant; the service joins the envelope.
CREATE INDEX message_delivery_sent_page_idx ON message_deliveries(recipient_user_id,created_at DESC,id DESC) WHERE deleted_at IS NULL;
CREATE INDEX message_envelope_related_delivery_idx ON message_envelopes(related_delivery_id) WHERE related_delivery_id IS NOT NULL;
CREATE INDEX message_envelope_related_envelope_idx ON message_envelopes(related_envelope_id) WHERE related_envelope_id IS NOT NULL;

CREATE FUNCTION messaging_snapshot_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_envelopes WHERE id=NEW.envelope_id
      AND xmin::text::bigint=(txid_current()%4294967296)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_snapshot_already_committed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_selector_insert BEFORE INSERT ON message_recipient_selectors FOR EACH ROW EXECUTE FUNCTION messaging_snapshot_insert();
CREATE TRIGGER message_addressee_insert BEFORE INSERT ON message_addressees FOR EACH ROW EXECUTE FUNCTION messaging_snapshot_insert();
CREATE TRIGGER message_delivery_insert BEFORE INSERT ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_snapshot_insert();
CREATE TRIGGER message_localization_insert BEFORE INSERT ON message_envelope_localizations FOR EACH ROW EXECUTE FUNCTION messaging_snapshot_insert();
CREATE TRIGGER message_link_snapshot_insert BEFORE INSERT ON message_resource_links FOR EACH ROW EXECUTE FUNCTION messaging_snapshot_insert();

CREATE FUNCTION messaging_delivery_timestamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 -- Denormalize only the ordering instant, never message content; this permits
 -- the recipient/sent-time/UUID index to serve Inbox keyset pagination.
 SELECT sent_at INTO NEW.created_at FROM message_envelopes WHERE id=NEW.envelope_id;
 RETURN NEW;
END $$;
CREATE TRIGGER message_delivery_timestamp BEFORE INSERT ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_delivery_timestamp();
CREATE FUNCTION messaging_default_level() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.security_level_id IS NULL THEN
  SELECT id INTO NEW.security_level_id FROM security_levels ORDER BY level_number LIMIT 1;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_envelope_default_level BEFORE INSERT ON message_envelopes FOR EACH ROW EXECUTE FUNCTION messaging_default_level();
CREATE TRIGGER message_draft_default_level BEFORE INSERT ON message_drafts FOR EACH ROW EXECUTE FUNCTION messaging_default_level();

-- Immutable capture provenance survives nulling of live resource references.
CREATE FUNCTION messaging_capture_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE keys text[];
BEGIN
 keys:=CASE TG_TABLE_NAME WHEN 'message_record_captures' THEN ARRAY['selected_envelope_id','record_id']
 ELSE ARRAY['envelope_id','digital_component_id'] END;
 IF (to_jsonb(NEW)-keys) IS DISTINCT FROM (to_jsonb(OLD)-keys) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_capture_immutable';
 END IF;
 IF EXISTS(SELECT 1 FROM unnest(keys) k WHERE to_jsonb(NEW)->k IS DISTINCT FROM to_jsonb(OLD)->k
    AND to_jsonb(NEW)->k<>'null'::jsonb) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_capture_reference_immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_capture_update BEFORE UPDATE ON message_record_captures FOR EACH ROW EXECUTE FUNCTION messaging_capture_update();
CREATE TRIGGER message_capture_component_update BEFORE UPDATE ON message_record_capture_components FOR EACH ROW EXECUTE FUNCTION messaging_capture_update();
CREATE TRIGGER message_capture_no_delete BEFORE DELETE ON message_record_captures FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE TRIGGER message_capture_component_no_delete BEFORE DELETE ON message_record_capture_components FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE FUNCTION messaging_validate_capture() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE total integer; provenance integer; selected integer;
BEGIN
 SELECT count(*),count(*) FILTER(WHERE component_kind='provenance'),count(*) FILTER(WHERE is_selected_message)
 INTO total,provenance,selected FROM message_record_capture_components WHERE capture_id=NEW.id;
 IF total<2 OR provenance<>1 OR selected<>1 OR NEW.selected_envelope_id IS DISTINCT FROM NEW.selected_envelope_id_at_capture
 OR NEW.record_id IS DISTINCT FROM NEW.record_id_at_capture
 OR EXISTS(SELECT 1 FROM message_record_capture_components x LEFT JOIN digital_components d ON d.id=x.digital_component_id
    WHERE x.capture_id=NEW.id AND (x.component_order>total
    OR (x.component_kind='provenance' AND x.component_order<>total)
    OR (x.component_kind='message' AND x.envelope_id IS DISTINCT FROM x.envelope_id_at_capture)
    OR (x.is_selected_message AND x.envelope_id IS DISTINCT FROM NEW.selected_envelope_id)
    OR x.digital_component_id IS DISTINCT FROM x.digital_component_id_at_capture OR d.record_id IS DISTINCT FROM NEW.record_id OR d.component_order IS DISTINCT FROM x.component_order)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_capture_incomplete';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER message_capture_valid AFTER INSERT ON message_record_captures
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION messaging_validate_capture();

CREATE FUNCTION messaging_validate_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.result_purged_at IS NULL AND NOT EXISTS(SELECT 1 FROM message_envelopes e WHERE e.id=NEW.result_envelope_id
 AND e.sender_user_id IS NOT DISTINCT FROM NEW.principal_user_id
 AND e.system_producer_code IS NOT DISTINCT FROM NEW.producer_code
 AND e.request_id=NEW.request_id
 AND ((NEW.operation_kind='send' AND e.message_kind<>'action_amendment_notice')
 OR (NEW.operation_kind='amendment' AND e.action_amendment_id=NEW.result_amendment_id))) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_receipt_result_mismatch';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER message_receipt_valid AFTER INSERT ON message_request_receipts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION messaging_validate_receipt();

CREATE FUNCTION messaging_capture_component_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_record_captures WHERE id=NEW.capture_id
      AND xmin::text::bigint=(txid_current()%4294967296)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_capture_already_committed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_capture_component_insert BEFORE INSERT ON message_record_capture_components FOR EACH ROW EXECUTE FUNCTION messaging_capture_component_insert();

CREATE TRIGGER message_mailbox_no_delete BEFORE DELETE ON message_mailboxes FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();

INSERT INTO schema_migrations(version) VALUES ('033_add_messaging_kernel')
ON CONFLICT(version) DO NOTHING;

COMMIT;

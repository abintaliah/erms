-- Seed a realistic three-level functional classification scheme for the
-- greenfield development environment: 4 roots, 12 branches, 36 terminals.
--
-- This is optional seed data, not a schema migration. It intentionally does
-- not read or write schema_migrations.
BEGIN;

DO $$
DECLARE
    seed_name constant text := '002_seed_ewa_functional_classification_scheme';
    scheme_id bigint;
    level_number integer;
BEGIN
    IF EXISTS (
        SELECT 1 FROM classification_schemes
        WHERE lower(code) = lower('EWA-FCS')
           OR lower(title) = lower('Electricity and Water Authority Functional Classification Scheme')
    ) THEN
        RAISE EXCEPTION
            'scheme EWA-FCS or Electricity and Water Authority Functional Classification Scheme already exists';
    END IF;

    PERFORM set_config('app.actor_type', 'automated_process', true),
            set_config('app.event_source', 'seeding', true),
            set_config(
                'app.change_reason',
                'Seed the Electricity and Water Authority functional classification scheme',
                true
            ),
            set_config(
                'app.event_metadata',
                jsonb_build_object(
                    'seed', seed_name,
                    'operation', 'development_classification_seed',
                    'basis', 'greenfield example data explicitly requested by the user',
                    'scheme_code', 'EWA-FCS',
                    'structure', jsonb_build_object(
                        'root_classifications', 4,
                        'branch_classifications', 12,
                        'terminal_classifications', 36
                    )
                )::text,
                true
            );

    INSERT INTO classification_schemes (
        code, title, description, authority, scope_note, edition, date_published
    ) VALUES (
        'EWA-FCS',
        'Electricity and Water Authority Functional Classification Scheme',
        'A function-based classification scheme for records created while governing, planning, constructing, operating and regulating electricity, potable-water and wastewater services, and while serving customers and advancing resource sustainability.',
        'Electricity and Water Authority — Records and Information Governance Office',
        'Applies to all headquarters, operational regions, plants, networks, customer-service channels, projects and controlled subsidiaries of the Authority. Transitory convenience copies remain subject to approved records-management procedures.',
        'First edition — 2026',
        CURRENT_TIMESTAMP
    ) RETURNING id INTO scheme_id;

    CREATE TEMP TABLE ewa_classification_seed (
        hierarchy_level integer NOT NULL,
        parent_code text,
        code text PRIMARY KEY,
        title text NOT NULL,
        description text NOT NULL,
        keywords text NOT NULL,
        is_terminal boolean NOT NULL,
        current_years integer,
        intermediate_years integer,
        final_disposition text,
        instructions text
    ) ON COMMIT DROP;

    INSERT INTO ewa_classification_seed VALUES
    (1,NULL,'EWA-01','Governance and Corporate Stewardship','Direction, oversight and corporate support functions that enable the Authority to fulfil its statutory mandate.','governance, board, strategy, legal, risk, workforce, finance, procurement',false,NULL,NULL,NULL,NULL),
    (2,'EWA-01','EWA-01.01','Governance, Strategy and Executive Direction','Corporate governance, executive decision-making, strategic planning and enterprise policy direction.','board, executive committee, strategy, performance, policy, delegation',false,NULL,NULL,NULL,NULL),
    (3,'EWA-01.01','EWA-01.01.01','Board and Executive Committee Governance','Records of governing-board and executive-committee constitution, agendas, deliberations, resolutions and formal oversight.','board papers, committee minutes, resolutions, governance charter, decisions',true,5,10,'transfer_to_external_archive','Retain signed minutes, approved papers and resolutions in current custody for 5 years, then in the records centre for 10 years. Transfer the authoritative set and governing instruments to the designated archival authority; destroy duplicate working packs after verification.'),
    (3,'EWA-01.01','EWA-01.01.02','Corporate Strategy and Performance','Development, approval and monitoring of corporate strategies, business plans, performance indicators and enterprise scorecards.','strategic plan, business plan, KPI, scorecard, performance review, annual priorities',true,5,10,'selective_preservation','Preserve approved strategies, final performance reports and major review records permanently as a representative institutional record. Destroy routine monitoring extracts and superseded drafts after 15 years.'),
    (3,'EWA-01.01','EWA-01.01.03','Enterprise Policy and Delegations','Creation, approval and maintenance of enterprise policies, governance frameworks, delegations and authorities.','policy, procedure, delegation of authority, governance framework, approval matrix',true,5,10,'transfer_to_external_archive','Keep approved instruments and documented approval history for 15 years after supersession. Transfer historically significant policy frameworks and delegations; destroy consultation copies and routine drafts.'),
    (2,'EWA-01','EWA-01.02','Legal, Risk and Regulatory Assurance','Legal services, enterprise risk, insurance, statutory compliance and assurance activities.','legal, litigation, risk, insurance, compliance, regulator, assurance',false,NULL,NULL,NULL,NULL),
    (3,'EWA-01.02','EWA-01.02.01','Legal Advice, Claims and Litigation','Legal opinions, dispute files, claims, litigation, settlements and privileged advice concerning Authority operations.','legal opinion, litigation, claim, dispute, settlement, privilege, counsel',true,7,13,'selective_preservation','Retain for 20 years after final resolution or expiry of appeal rights. Permanently preserve precedent-setting matters, major public-interest cases and significant legal opinions; securely destroy routine closed matters.'),
    (3,'EWA-01.02','EWA-01.02.02','Enterprise Risk and Insurance','Enterprise risk registers, risk assessments, treatment plans, insurance programmes and material loss events.','risk register, risk assessment, mitigation, insurance policy, loss event, business risk',true,5,10,'selective_preservation','Retain approved enterprise risk registers and insurance programme records for 15 years. Preserve milestone registers and records of catastrophic or precedent-setting losses; destroy routine assessments when superseded and retention expires.'),
    (3,'EWA-01.02','EWA-01.02.03','Regulatory Compliance and Assurance','Evidence of compliance with statutory obligations, regulatory submissions, internal assurance reviews and corrective actions.','compliance register, regulatory return, audit, assurance, corrective action, statutory report',true,7,8,'transfer_to_external_archive','Retain final regulatory submissions, assurance reports and closure evidence for 15 years. Transfer submissions and findings of enduring regulatory or public significance; destroy routine evidence after expiry.'),
    (2,'EWA-01','EWA-01.03','People, Finance and Commercial Services','Management of workforce, financial resources, procurement, suppliers and commercial agreements.','human resources, payroll, finance, accounting, procurement, supplier, contract',false,NULL,NULL,NULL,NULL),
    (3,'EWA-01.03','EWA-01.03.01','Workforce and Employment Administration','Recruitment, appointment, service history, performance, leave, conduct and separation records for Authority personnel.','employee file, recruitment, performance, leave, conduct, separation, pension',true,7,43,'destruction','Retain the authoritative employee file for 50 years after separation to support employment, pension and occupational claims. Destroy unsuccessful recruitment files after 2 years unless a complaint or litigation hold applies.'),
    (3,'EWA-01.03','EWA-01.03.02','Financial Accounting and Treasury','Budgets, ledgers, payments, receivables, treasury, taxation, financial statements and supporting accounting evidence.','budget, ledger, invoice, payment, receivable, treasury, tax, financial statement',true,7,3,'destruction','Retain audited accounts and supporting transaction evidence for 10 years after financial-year closure, subject to audit, tax and investigation holds. Authoritative annual financial statements are managed with corporate reporting records.'),
    (3,'EWA-01.03','EWA-01.03.03','Procurement, Contracts and Supplier Management','Sourcing, tendering, evaluation, contract award, supplier performance and commercial close-out records.','tender, bid, evaluation, purchase order, contract, supplier, variation, close-out',true,7,8,'selective_preservation','Retain for 15 years after contract expiry or final settlement. Preserve records of strategic procurements, major infrastructure contracts and precedent-setting commercial decisions; destroy routine procurement files after expiry.'),

    (1,NULL,'EWA-02','Electricity System and Network Services','Planning, development, operation and maintenance of electricity generation, transmission, distribution and system-control capabilities.','electricity, generation, transmission, distribution, grid, substation, system operations',false,NULL,NULL,NULL,NULL),
    (2,'EWA-02','EWA-02.01','Electricity Planning and Asset Strategy','Long-range demand forecasting, system studies, asset strategy and capital investment planning for electricity services.','load forecast, power system study, asset strategy, capital plan, grid planning',false,NULL,NULL,NULL,NULL),
    (3,'EWA-02.01','EWA-02.01.01','Electricity Demand Forecasting','Forecasts and models of electricity demand, load profiles, peak requirements and scenario assumptions.','demand forecast, load profile, peak demand, scenario, econometric model',true,5,10,'selective_preservation','Retain validated forecasts, models and assumptions for 15 years after supersession. Preserve benchmark forecasts supporting major policy or investment decisions; destroy intermediate model runs after validation.'),
    (3,'EWA-02.01','EWA-02.01.02','Power System Studies and Network Modelling','Technical studies and models addressing load flow, fault levels, stability, reliability and network reinforcement.','load flow, fault level, stability, reliability, network model, reinforcement study',true,10,15,'retain_as_local_archives','Retain approved studies and validated network models as local technical archives for the operational life of affected assets plus 15 years. Superseded working models may be destroyed after technical validation.'),
    (3,'EWA-02.01','EWA-02.01.03','Electricity Capital Portfolio Planning','Prioritisation, approval and governance of electricity capital programmes and investment portfolios.','capital programme, investment case, portfolio, prioritisation, grid expansion',true,7,13,'selective_preservation','Retain approved portfolio plans, investment cases and benefit reviews for 20 years. Preserve milestone programmes and decisions shaping the electricity system; destroy routine portfolio working records after expiry.'),
    (2,'EWA-02','EWA-02.02','Electricity Projects and Asset Delivery','Design, permitting, construction, commissioning and handover of electricity infrastructure and major equipment.','project delivery, design, construction, commissioning, substation, cable, overhead line',false,NULL,NULL,NULL,NULL),
    (3,'EWA-02.02','EWA-02.02.01','Generation and Grid Infrastructure Projects','Project records for power-generation facilities, bulk supply points, transmission lines and strategic substations.','power plant, transmission line, bulk supply point, substation, EPC, project',true,10,20,'selective_preservation','Retain the approved design, as-built, commissioning, safety and handover record for asset life plus 20 years. Permanently preserve landmark projects and records documenting major system development.'),
    (3,'EWA-02.02','EWA-02.02.02','Distribution Network Projects','Design and delivery records for distribution substations, feeders, cables, overhead lines and network extensions.','distribution substation, feeder, cable, overhead line, network extension, as-built',true,10,15,'retain_as_local_archives','Retain final design, as-built, test and handover records locally for asset life plus 15 years. Destroy superseded drawings only after configuration control confirms replacement by the authoritative revision.'),
    (3,'EWA-02.02','EWA-02.02.03','Electricity Equipment Commissioning and Handover','Factory and site acceptance, energisation, commissioning, defect resolution and operational handover records.','FAT, SAT, energisation, commissioning, defects, handover, test certificate',true,10,15,'retain_as_local_archives','Retain signed test certificates, energisation authorities, commissioning dossiers and defect closure evidence for asset life plus 15 years as local technical archives.'),
    (2,'EWA-02','EWA-02.03','Electricity Operations and Maintenance','Real-time system operation, outage management, inspection, maintenance and technical incident response.','control centre, dispatch, outage, maintenance, protection, incident, reliability',false,NULL,NULL,NULL,NULL),
    (3,'EWA-02.03','EWA-02.03.01','Grid Control, Dispatch and Switching','Control-room logs, dispatch instructions, switching programmes and operational coordination records.','SCADA, control room, dispatch, switching schedule, operating log, grid control',true,3,7,'destruction','Retain authoritative operating logs, dispatch instructions and completed switching programmes for 10 years, longer where linked to an incident, claim or regulatory investigation.'),
    (3,'EWA-02.03','EWA-02.03.02','Electricity Asset Inspection and Maintenance','Inspection findings, preventive and corrective maintenance, test results and work histories for electricity assets.','inspection, preventive maintenance, corrective maintenance, work order, test result, asset history',true,5,10,'retain_as_local_archives','Retain verified maintenance history and condition assessments for asset life plus 10 years to support safety, reliability and engineering analysis. Destroy duplicate field copies after capture.'),
    (3,'EWA-02.03','EWA-02.03.03','Electricity Outages and Technical Incidents','Planned and unplanned outage records, disturbance investigations, protection events and restoration reviews.','outage, interruption, disturbance, protection trip, root cause, restoration',true,7,13,'selective_preservation','Retain incident and outage records for 20 years. Permanently preserve major blackouts, safety-significant events and incidents that materially changed standards or system design.'),

    (1,NULL,'EWA-03','Water and Wastewater Services','Planning, production, treatment, distribution, collection and quality management of potable water and wastewater services.','water, wastewater, desalination, treatment, reservoir, pipeline, sewerage, quality',false,NULL,NULL,NULL,NULL),
    (2,'EWA-03','EWA-03.01','Water Resources and Supply Planning','Demand forecasting, supply balancing, water-resource strategy and capital planning for reliable water services.','water demand, supply forecast, resource plan, hydraulic model, capacity planning',false,NULL,NULL,NULL,NULL),
    (3,'EWA-03.01','EWA-03.01.01','Water Demand and Supply Forecasting','Forecasts, scenarios and balances for potable-water demand, production, storage and imports.','water forecast, demand projection, supply balance, storage, scenario planning',true,5,10,'selective_preservation','Retain approved forecasts and underlying assumptions for 15 years after supersession. Preserve benchmark studies supporting major supply-policy and infrastructure decisions.'),
    (3,'EWA-03.01','EWA-03.01.02','Water Network Hydraulic Modelling','Hydraulic models and studies supporting pressure, flow, storage, resilience and network reinforcement decisions.','hydraulic model, pressure, flow, reservoir, network reinforcement, resilience',true,10,15,'retain_as_local_archives','Retain validated models, calibration evidence and approved studies as local technical archives for the life of the represented network plus 15 years.'),
    (3,'EWA-03.01','EWA-03.01.03','Water Capital Portfolio Planning','Governance and prioritisation of water-production, transmission, distribution and wastewater capital programmes.','water capital plan, portfolio, investment case, desalination, pipeline, treatment plant',true,7,13,'selective_preservation','Retain approved programmes, investment cases and benefit reviews for 20 years. Preserve milestone programmes and decisions that materially shaped water security or wastewater services.'),
    (2,'EWA-03','EWA-03.02','Water Production, Treatment and Quality','Operation of production and treatment facilities and assurance of drinking-water and treated-effluent quality.','desalination, treatment plant, laboratory, water quality, sampling, compliance',false,NULL,NULL,NULL,NULL),
    (3,'EWA-03.02','EWA-03.02.01','Water Production and Treatment Operations','Plant operating logs, production records, process-control data and operational performance for water facilities.','plant log, production, desalination, treatment process, chemical dosing, performance',true,5,10,'destruction','Retain validated plant logs and production summaries for 15 years. Extend retention where records support environmental, health, incident or contractual investigations.'),
    (3,'EWA-03.02','EWA-03.02.02','Drinking Water Quality Monitoring','Sampling plans, laboratory results, exceedance investigations and compliance evidence for potable-water quality.','water sample, laboratory result, drinking water, exceedance, quality standard, compliance',true,10,20,'retain_as_local_archives','Retain authoritative sampling, analytical and exceedance records locally for 30 years to support public-health assurance, trend analysis and regulatory accountability.'),
    (3,'EWA-03.02','EWA-03.02.03','Treatment Process Validation and Improvement','Validation studies, trials and optimisation of water and wastewater treatment processes.','process validation, pilot trial, optimisation, membrane, disinfection, treatment study',true,7,13,'selective_preservation','Retain approved validation and optimisation studies for 20 years. Preserve studies introducing significant treatment technology or changing public-health safeguards.'),
    (2,'EWA-03','EWA-03.03','Water Distribution and Wastewater Operations','Operation, maintenance and incident management for water distribution, sewerage and treated-effluent networks.','water distribution, sewerage, wastewater, pipeline, pumping station, leakage, overflow',false,NULL,NULL,NULL,NULL),
    (3,'EWA-03.03','EWA-03.03.01','Water Network Operations and Maintenance','Operational control, inspection, flushing, repair and maintenance histories for distribution assets.','distribution network, pipeline, valve, flushing, leak repair, maintenance',true,5,15,'retain_as_local_archives','Retain verified asset maintenance history and significant operational records for asset life plus 15 years as local technical archives.'),
    (3,'EWA-03.03','EWA-03.03.02','Wastewater Collection and Treatment Operations','Sewerage-network and treatment-plant operations, maintenance, discharge monitoring and sludge-management records.','sewerage, wastewater plant, discharge, sludge, pumping station, effluent',true,7,13,'retain_as_local_archives','Retain authoritative operating, discharge and maintenance records for 20 years, and asset histories for asset life plus 15 years where longer.'),
    (3,'EWA-03.03','EWA-03.03.03','Water Supply and Wastewater Incidents','Investigation and response records for contamination, supply interruption, major leakage, sewer overflow and environmental events.','contamination, supply interruption, burst main, sewer overflow, environmental incident, root cause',true,10,20,'selective_preservation','Retain incident files for 30 years. Permanently preserve events with major public-health, environmental, regulatory or infrastructure consequences and associated lessons learned.'),

    (1,NULL,'EWA-04','Customer, Revenue and Sustainability Services','Customer relationships, connections, metering, billing, revenue protection, conservation and public service programmes.','customer, connection, meter, billing, revenue, tariff, conservation, sustainability',false,NULL,NULL,NULL,NULL),
    (2,'EWA-04','EWA-04.01','Customer Accounts and Service Delivery','Establishment and administration of customer accounts, service requests, complaints and vulnerable-customer support.','customer account, service request, complaint, contact centre, vulnerable customer',false,NULL,NULL,NULL,NULL),
    (3,'EWA-04.01','EWA-04.01.01','Customer Account Establishment and Closure','Applications, identity and eligibility checks, service agreements, account changes and final closure records.','new account, service agreement, identity check, account transfer, closure',true,7,3,'destruction','Retain account establishment, material changes and closure evidence for 10 years after account closure, subject to unresolved debt, complaint, fraud or litigation holds.'),
    (3,'EWA-04.01','EWA-04.01.02','Customer Requests, Complaints and Appeals','Customer enquiries, service requests, complaints, escalation, investigation, remedy and external appeal records.','complaint, enquiry, service request, escalation, ombudsman, appeal, remedy',true,5,5,'selective_preservation','Retain case records for 10 years after closure. Preserve precedent-setting complaints, systemic investigations and cases resulting in material policy or service change.'),
    (3,'EWA-04.01','EWA-04.01.03','Connections and Service Activation','Technical and administrative records for new electricity, water and wastewater connections and service activation.','connection application, load request, water connection, activation, inspection, service point',true,7,13,'retain_as_local_archives','Retain approved connection design, capacity, inspection and activation records for the life of the service connection plus 10 years; destroy routine correspondence after expiry.'),
    (2,'EWA-04','EWA-04.02','Metering, Billing and Revenue Management','Meter lifecycle, consumption measurement, tariff application, billing, collection and revenue-protection functions.','meter, AMI, consumption, tariff, bill, payment, debt, revenue protection',false,NULL,NULL,NULL,NULL),
    (3,'EWA-04.02','EWA-04.02.01','Meter Asset and Reading Management','Meter installation, configuration, testing, replacement, reading, validation and interval-data management.','meter installation, smart meter, AMI, reading, interval data, calibration, replacement',true,7,8,'destruction','Retain meter lifecycle and validated consumption data for 15 years after meter removal or reading date. Preserve data longer where required for disputes, settlement or investigation.'),
    (3,'EWA-04.02','EWA-04.02.02','Billing, Tariffs and Adjustments','Tariff implementation, bill calculation, issue, correction, adjustment, refund and account reconciliation records.','tariff, invoice, bill, adjustment, refund, reconciliation, consumption charge',true,7,3,'destruction','Retain billing transactions, tariff calculations and approved adjustments for 10 years after the transaction or account closure, whichever is later.'),
    (3,'EWA-04.02','EWA-04.02.03','Collections and Revenue Protection','Debt recovery, payment arrangements, disconnection action, theft investigation and revenue-protection cases.','debt collection, payment plan, disconnection, tampering, theft, fraud, revenue protection',true,7,8,'selective_preservation','Retain closed collection and revenue-protection cases for 15 years. Preserve major fraud cases, novel enforcement precedents and matters producing significant control changes.'),
    (2,'EWA-04','EWA-04.03','Sustainability and Demand Management','Energy and water conservation, renewable integration, emissions management, public programmes and sustainability reporting.','sustainability, conservation, demand management, renewable energy, emissions, efficiency',false,NULL,NULL,NULL,NULL),
    (3,'EWA-04.03','EWA-04.03.01','Energy Efficiency and Demand-Side Management','Design, delivery and evaluation of electricity-efficiency, peak-reduction and demand-response programmes.','energy efficiency, demand response, peak reduction, rebate, conservation programme',true,7,13,'selective_preservation','Retain programme design, participation evidence and evaluations for 20 years. Preserve flagship programmes and evidence informing major demand-management policy.'),
    (3,'EWA-04.03','EWA-04.03.02','Water Conservation Programmes','Design, delivery and evaluation of leakage reduction, efficient-use, reuse and public water-conservation initiatives.','water conservation, leakage reduction, reuse, efficiency, awareness campaign',true,7,13,'selective_preservation','Retain programme and evaluation records for 20 years. Preserve significant conservation initiatives, long-term outcome studies and records of material policy impact.'),
    (3,'EWA-04.03','EWA-04.03.03','Sustainability, Climate and Emissions Reporting','Greenhouse-gas inventories, climate-risk assessments, sustainability metrics, targets and public disclosures.','carbon inventory, greenhouse gas, climate risk, ESG, sustainability report, emissions target',true,7,13,'transfer_to_external_archive','Retain verified datasets, methodologies and approved disclosures for 20 years. Transfer final sustainability reports, milestone inventories and major climate-risk assessments for permanent preservation.');

    FOR level_number IN 1..3 LOOP
        INSERT INTO classifications (
            classification_scheme_id, parent_classification_id, code, title,
            description, authority, scope_note, keywords, is_terminal
        )
        SELECT
            scheme_id,
            parent.id,
            seed.code,
            seed.title,
            seed.description,
            'Electricity and Water Authority — Records and Information Governance Office',
            CASE seed.hierarchy_level
                WHEN 1 THEN 'Top-level functional domain applying across the Authority.'
                WHEN 2 THEN 'Functional branch grouping related business processes and records.'
                ELSE 'Assignable terminal class governing the records described and its approved retention rule.'
            END,
            seed.keywords,
            seed.is_terminal
        FROM ewa_classification_seed AS seed
        LEFT JOIN classifications AS parent
          ON parent.classification_scheme_id = scheme_id
         AND parent.code = seed.parent_code
        WHERE seed.hierarchy_level = level_number;
    END LOOP;

    INSERT INTO classification_retention_rules (
        classification_id, current_period_years, intermediate_period_years,
        final_disposition, instructions
    )
    SELECT
        classification.id,
        seed.current_years,
        seed.intermediate_years,
        seed.final_disposition,
        seed.instructions
    FROM ewa_classification_seed AS seed
    JOIN classifications AS classification
      ON classification.classification_scheme_id = scheme_id
     AND classification.code = seed.code
    WHERE seed.is_terminal;

    IF (SELECT count(*) FROM classifications WHERE classification_scheme_id = scheme_id) <> 52 THEN
        RAISE EXCEPTION 'EWA-FCS seed did not create exactly 52 classifications';
    END IF;
    IF (
        SELECT count(*)
        FROM classifications
        WHERE classification_scheme_id = scheme_id AND is_terminal
    ) <> 36 THEN
        RAISE EXCEPTION 'EWA-FCS seed did not create exactly 36 terminal classifications';
    END IF;
    IF (
        SELECT count(*)
        FROM classification_retention_rules AS rule
        JOIN classifications AS classification ON classification.id = rule.classification_id
        WHERE classification.classification_scheme_id = scheme_id
    ) <> 36 THEN
        RAISE EXCEPTION 'EWA-FCS seed did not create exactly 36 retention rules';
    END IF;

    SET CONSTRAINTS ALL IMMEDIATE;

    RAISE NOTICE 'seeded EWA-FCS with 4 roots, 12 branches, 36 terminals and 36 retention rules';
END;
$$;

COMMIT;

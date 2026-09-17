-- Seed a realistic general administrative classification scheme for the
-- greenfield development environment: 4 roots, 12 branches, 36 terminals.
--
-- This is optional seed data, not a schema migration. It intentionally does
-- not read or write schema_migrations.
BEGIN;

DO $$
DECLARE
    seed_name constant text := '003_seed_general_classification_scheme';
    scheme_id bigint;
    level_number integer;
BEGIN
    IF EXISTS (
        SELECT 1 FROM classification_schemes
        WHERE lower(code) = lower('GCS')
           OR lower(title) = lower('General Classification Scheme')
    ) THEN
        RAISE EXCEPTION 'scheme GCS or General Classification Scheme already exists';
    END IF;

    PERFORM set_config('app.actor_type', 'automated_process', true),
            set_config('app.event_source', 'administrative_tool', true),
            set_config(
                'app.change_reason',
                'Seed the General Classification Scheme with realistic administrative functions and retention rules',
                true
            ),
            set_config(
                'app.event_metadata',
                jsonb_build_object(
                    'seed', seed_name,
                    'operation', 'development_classification_seed',
                    'basis', 'greenfield example data explicitly requested by the user',
                    'scheme_code', 'GCS',
                    'scheme_title', 'General Classification Scheme',
                    'structure', jsonb_build_object(
                        'root_classifications', 4,
                        'branch_classifications', 12,
                        'terminal_classifications', 36,
                        'retention_rules', 36
                    )
                )::text,
                true
            );

    INSERT INTO classification_schemes (
        code, title, description, authority, scope_note, edition, date_published
    ) VALUES (
        'GCS',
        'General Classification Scheme',
        'A function-based classification scheme for common corporate records concerning administration, human resources, finance and asset management.',
        'Corporate Records and Information Governance Office',
        'Applies to common administrative and corporate-service records created by all business units. Function-specific operational records remain governed by the applicable specialist classification scheme.',
        'First edition — 2026',
        CURRENT_TIMESTAMP
    ) RETURNING id INTO scheme_id;

    CREATE TEMP TABLE general_classification_seed (
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

    INSERT INTO general_classification_seed VALUES
    (1,NULL,'GCS-01','Administration','Corporate governance, office administration and shared support activities that enable the organization to operate.','administration, governance, office services, correspondence, meetings, policy',false,NULL,NULL,NULL,NULL),
    (2,'GCS-01','GCS-01.01','Corporate Governance and Planning','Enterprise governance, strategic planning, policy direction and organizational performance oversight.','governance, strategy, policy, executive, performance, planning',false,NULL,NULL,NULL,NULL),
    (3,'GCS-01.01','GCS-01.01.01','Governing Body and Executive Committees','Constitution, agendas, papers, minutes, resolutions and decision records of the governing body and executive committees.','board, executive committee, agenda, minutes, resolution, decision',true,5,10,'transfer_to_external_archive','Retain signed minutes, approved papers and resolutions for 15 years, then transfer the authoritative set to the designated archival authority. Destroy convenience copies after verification.'),
    (3,'GCS-01.01','GCS-01.01.02','Corporate Strategy and Business Planning','Development, approval, monitoring and review of strategic plans, annual business plans, objectives and performance measures.','strategy, business plan, objectives, KPI, scorecard, performance review',true,5,10,'selective_preservation','Retain approved plans and final performance reviews for 15 years. Preserve milestone strategies and reviews documenting major organizational change; destroy superseded working drafts.'),
    (3,'GCS-01.01','GCS-01.01.03','Corporate Policies and Delegations','Development, approval, issue and maintenance of corporate policies, governance frameworks and delegations of authority.','policy, governance framework, delegation, authority, approval, procedure',true,5,10,'transfer_to_external_archive','Retain approved instruments and approval history for 15 years after supersession. Transfer policies and delegations of enduring governance significance; destroy routine consultation copies.'),
    (2,'GCS-01','GCS-01.02','Office and Administrative Services','Management of office facilities, administrative support, supplies, travel and routine business coordination.','office services, facilities, supplies, travel, reception, administration',false,NULL,NULL,NULL,NULL),
    (3,'GCS-01.02','GCS-01.02.01','Office Accommodation and Support Services','Allocation and operation of office space, reception, mailrooms, meeting facilities and shared administrative services.','office space, reception, mailroom, meeting room, accommodation, support service',true,3,4,'destruction','Retain service arrangements, space allocations and significant issue files for 7 years after supersession or closure. Destroy routine bookings, logs and requests after 2 years.'),
    (3,'GCS-01.02','GCS-01.02.02','Travel and Official Visits','Authorization and administration of business travel, itineraries, official visits and related logistical arrangements.','business travel, itinerary, official visit, mission, airfare, accommodation',true,3,4,'destruction','Retain approved travel and official-visit files for 7 years after completion and financial reconciliation, subject to audit or investigation holds.'),
    (3,'GCS-01.02','GCS-01.02.03','Administrative Supplies and Services','Requests, approvals and delivery records for stationery, printing, couriers and routine administrative supplies and services.','stationery, printing, courier, office supplies, service request, consumables',true,2,3,'destruction','Retain purchasing and service evidence for 5 years after completion. Destroy routine stock-control and delivery records when no longer required for audit.'),
    (2,'GCS-01','GCS-01.03','Corporate Communications and Engagement','Official correspondence, public communications, stakeholder engagement and corporate events.','correspondence, communications, media, stakeholder, publication, event',false,NULL,NULL,NULL,NULL),
    (3,'GCS-01.03','GCS-01.03.01','Official Correspondence and Briefings','Substantive incoming and outgoing correspondence, executive briefings and formal organizational representations.','official correspondence, briefing, memorandum, ministerial, executive response',true,5,10,'selective_preservation','Retain substantive correspondence and approved briefings for 15 years. Preserve material documenting significant decisions, public issues or relationships; destroy routine correspondence.'),
    (3,'GCS-01.03','GCS-01.03.02','Media, Publications and Digital Communications','Media releases, approved publications, website content and official social-media communications.','media release, publication, website, social media, campaign, brand',true,3,7,'selective_preservation','Retain final published content and approvals for 10 years. Preserve representative publications and communications concerning major events, policies or institutional milestones.'),
    (3,'GCS-01.03','GCS-01.03.03','Stakeholder Engagement and Corporate Events','Planning and delivery of consultations, stakeholder forums, conferences, ceremonies and corporate events.','stakeholder, consultation, conference, ceremony, event, engagement',true,3,7,'selective_preservation','Retain final programmes, participant records, outcomes and evaluations for 10 years. Preserve records of major consultations and events of lasting institutional significance.'),

    (1,NULL,'GCS-02','Human Resources','Management of workforce planning, recruitment, employment, development, wellbeing, conduct and separation.','human resources, employees, recruitment, payroll, training, performance, wellbeing',false,NULL,NULL,NULL,NULL),
    (2,'GCS-02','GCS-02.01','Workforce Planning and Recruitment','Workforce establishment, position planning, recruitment, selection and appointment activities.','workforce plan, establishment, vacancy, recruitment, selection, appointment',false,NULL,NULL,NULL,NULL),
    (3,'GCS-02.01','GCS-02.01.01','Workforce Establishment and Planning','Approved staffing establishments, workforce forecasts, organizational design and resource planning.','staffing establishment, workforce forecast, headcount, organization design, succession',true,5,10,'selective_preservation','Retain approved establishment and workforce plans for 15 years after supersession. Preserve plans documenting major restructures or enduring workforce-policy changes.'),
    (3,'GCS-02.01','GCS-02.01.02','Recruitment and Selection','Vacancy approvals, advertisements, applications, assessments, interview records and selection decisions.','vacancy, application, interview, assessment, candidate, selection',true,2,3,'destruction','Transfer successful candidate records to the employee file. Retain unsuccessful applications and selection working papers for 5 years after appointment, longer if a complaint is active.'),
    (3,'GCS-02.01','GCS-02.01.03','Appointment and Onboarding','Offers, pre-employment checks, contracts, induction and initial employment documentation.','offer, employment contract, background check, onboarding, induction, probation',true,7,43,'destruction','Retain authoritative appointment and onboarding evidence with the employee file for 50 years after separation. Destroy duplicate onboarding checklists after verified capture.'),
    (2,'GCS-02','GCS-02.02','Employment Administration and Performance','Personnel files, attendance, leave, remuneration, performance and employee lifecycle administration.','personnel file, leave, attendance, remuneration, performance, promotion',false,NULL,NULL,NULL,NULL),
    (3,'GCS-02.02','GCS-02.02.01','Employee Personnel Files','Authoritative service history, contractual changes, promotions, transfers, leave and separation documentation for individual employees.','employee file, service history, promotion, transfer, leave, separation',true,7,43,'destruction','Retain the authoritative personnel file for 50 years after separation to support employment, pension and occupational claims, subject to longer legal holds.'),
    (3,'GCS-02.02','GCS-02.02.02','Performance and Career Management','Performance agreements, appraisals, development plans, talent reviews and career progression decisions.','performance appraisal, objectives, development plan, talent review, career',true,5,5,'destruction','Retain completed performance and career-management records for 10 years after the review cycle or separation, whichever is later.'),
    (3,'GCS-02.02','GCS-02.02.03','Payroll, Benefits and Attendance','Payroll inputs, salary changes, allowances, benefits, attendance and leave-accounting records.','payroll, salary, allowance, benefits, attendance, timesheet, leave balance',true,7,3,'destruction','Retain payroll, benefit and attendance transaction records for 10 years after the financial year, subject to pension, tax, audit and dispute requirements.'),
    (2,'GCS-02','GCS-02.03','Learning, Wellbeing and Employee Relations','Training, occupational wellbeing, grievances, discipline and workplace relations.','training, learning, wellbeing, health, grievance, discipline, employee relations',false,NULL,NULL,NULL,NULL),
    (3,'GCS-02.03','GCS-02.03.01','Learning and Professional Development','Training needs, course delivery, attendance, qualifications and professional-development records.','training, course, qualification, certification, development, attendance',true,5,5,'destruction','Retain individual training and qualification evidence for 10 years after separation. Retain programme evaluations for 5 years after supersession.'),
    (3,'GCS-02.03','GCS-02.03.02','Employee Health, Safety and Wellbeing','Occupational health surveillance, workplace adjustments, wellbeing programmes and employee assistance administration.','occupational health, wellbeing, medical surveillance, adjustment, employee assistance',true,7,43,'destruction','Retain occupational health and exposure records for 50 years after separation where required. Keep general wellbeing programme records for 7 years after completion.'),
    (3,'GCS-02.03','GCS-02.03.03','Grievances, Discipline and Employee Relations','Employee grievances, disciplinary matters, investigations, appeals and collective workplace relations.','grievance, discipline, misconduct, investigation, appeal, labor relations',true,7,13,'selective_preservation','Retain closed case files for 20 years. Preserve precedent-setting or organization-wide employee-relations matters; securely destroy routine cases after expiry.'),

    (1,NULL,'GCS-03','Finance','Planning, controlling, accounting for and reporting the organization’s financial resources and obligations.','finance, accounting, budget, treasury, revenue, expenditure, audit',false,NULL,NULL,NULL,NULL),
    (2,'GCS-03','GCS-03.01','Budgeting and Financial Planning','Budget formulation, allocation, forecasting, monitoring and financial performance planning.','budget, forecast, allocation, financial plan, variance, capital budget',false,NULL,NULL,NULL,NULL),
    (3,'GCS-03.01','GCS-03.01.01','Annual Budget Development and Approval','Budget submissions, challenge processes, consolidation, approvals and authorized allocations.','annual budget, submission, allocation, approval, appropriation, budget book',true,7,8,'selective_preservation','Retain approved budgets and supporting decision records for 15 years. Preserve final budgets and significant allocation decisions as evidence of corporate priorities.'),
    (3,'GCS-03.01','GCS-03.01.02','Financial Forecasting and Scenario Planning','Rolling forecasts, cash projections, scenario modelling and financial sustainability analysis.','financial forecast, cash projection, scenario, sensitivity, sustainability',true,5,5,'destruction','Retain approved forecasts and material scenario analyses for 10 years after supersession. Destroy intermediate calculations after validation and audit closure.'),
    (3,'GCS-03.01','GCS-03.01.03','Budget Monitoring and Variance Management','Periodic expenditure monitoring, variance analysis, budget transfers and corrective actions.','budget monitoring, variance, transfer, expenditure, management report',true,7,3,'destruction','Retain final monitoring reports, approved transfers and corrective actions for 10 years after financial-year closure.'),
    (2,'GCS-03','GCS-03.02','Accounting and Financial Operations','General ledger, payables, receivables, banking, taxation and routine financial transactions.','ledger, accounts payable, receivable, banking, tax, payment, invoice',false,NULL,NULL,NULL,NULL),
    (3,'GCS-03.02','GCS-03.02.01','General Ledger and Financial Close','Chart of accounts, journals, reconciliations, trial balances and period-end close records.','general ledger, journal, reconciliation, trial balance, month end, year end',true,7,3,'destruction','Retain ledgers, journals and completed reconciliations for 10 years after financial-year closure, subject to audit, tax and investigation holds.'),
    (3,'GCS-03.02','GCS-03.02.02','Accounts Payable and Expenditure','Supplier invoices, payment approvals, expense claims, disbursements and supporting evidence.','supplier invoice, payment, expense claim, disbursement, payable',true,7,3,'destruction','Retain transaction evidence and approvals for 10 years after financial-year closure. Destroy duplicates after reconciliation and audit requirements are satisfied.'),
    (3,'GCS-03.02','GCS-03.02.03','Accounts Receivable and Revenue','Billing, receipts, debtor balances, credit control, adjustments and revenue reconciliation.','invoice, receipt, debtor, credit control, revenue, adjustment, receivable',true,7,3,'destruction','Retain receivable, collection and revenue-reconciliation records for 10 years after settlement or write-off, whichever is later.'),
    (2,'GCS-03','GCS-03.03','Treasury, Reporting and Financial Assurance','Cash and investment management, statutory reporting, taxation, audit and financial controls.','treasury, investment, financial statement, tax, audit, internal control',false,NULL,NULL,NULL,NULL),
    (3,'GCS-03.03','GCS-03.03.01','Treasury and Cash Management','Banking arrangements, liquidity, investments, borrowing, guarantees and treasury operations.','bank account, cash management, investment, borrowing, guarantee, liquidity',true,7,13,'selective_preservation','Retain executed financing instruments and material treasury decisions for 20 years after maturity. Preserve records of significant borrowings or investment-policy decisions.'),
    (3,'GCS-03.03','GCS-03.03.02','Financial Statements and Statutory Reporting','Preparation, approval and publication of annual financial statements and statutory financial returns.','financial statement, annual accounts, statutory return, disclosure, audit opinion',true,7,13,'transfer_to_external_archive','Retain authoritative signed statements, disclosures and audit opinions for 20 years, then transfer the final annual sets for permanent preservation.'),
    (3,'GCS-03.03','GCS-03.03.03','Financial Audit and Control Assurance','Internal and external financial audits, control testing, findings, management responses and remediation.','financial audit, control test, finding, management response, remediation',true,7,8,'selective_preservation','Retain audit files, final reports and closure evidence for 15 years. Preserve major investigations and audits producing significant governance or control changes.'),

    (1,NULL,'GCS-04','Asset Management','Planning, acquiring, operating, maintaining and disposing of physical, technology and information assets.','asset management, property, equipment, fleet, technology, inventory, disposal',false,NULL,NULL,NULL,NULL),
    (2,'GCS-04','GCS-04.01','Asset Planning and Acquisition','Asset strategies, investment planning, requirements, acquisition and commissioning.','asset strategy, capital plan, acquisition, specification, commissioning, investment',false,NULL,NULL,NULL,NULL),
    (3,'GCS-04.01','GCS-04.01.01','Asset Strategy and Lifecycle Planning','Asset-management policies, lifecycle strategies, condition forecasts and renewal programmes.','asset strategy, lifecycle, condition, renewal, asset plan, criticality',true,5,15,'retain_as_local_archives','Retain approved lifecycle strategies and condition baselines for the life of the relevant asset portfolio plus 15 years as local technical archives.'),
    (3,'GCS-04.01','GCS-04.01.02','Asset Requirements and Acquisition','Business requirements, specifications, evaluations, approvals and acquisition records for assets.','requirement, specification, evaluation, acquisition, purchase, acceptance',true,7,8,'destruction','Retain acquisition and acceptance records for asset life plus 7 years. Where procurement files provide the authoritative evidence, retain cross-references rather than duplicates.'),
    (3,'GCS-04.01','GCS-04.01.03','Asset Commissioning and Handover','Installation, testing, commissioning, certification, defects and operational handover documentation.','installation, commissioning, acceptance test, certification, defect, handover',true,10,15,'retain_as_local_archives','Retain signed commissioning, certification and handover records for asset life plus 15 years as part of the authoritative asset history.'),
    (2,'GCS-04','GCS-04.02','Asset Operations and Maintenance','Asset registers, operation, inspection, maintenance, calibration and configuration management.','asset register, operation, maintenance, inspection, calibration, configuration',false,NULL,NULL,NULL,NULL),
    (3,'GCS-04.02','GCS-04.02.01','Asset Registers and Configuration Records','Authoritative asset identities, ownership, location, configuration, valuation and status histories.','asset register, inventory, configuration, location, ownership, valuation',true,10,15,'retain_as_local_archives','Maintain the authoritative register throughout asset life and retain superseded configuration and ownership histories for 15 years after disposal.'),
    (3,'GCS-04.02','GCS-04.02.02','Inspection, Maintenance and Repair','Preventive and corrective maintenance, inspections, work orders, repairs and condition assessments.','maintenance, inspection, work order, repair, condition assessment, service history',true,5,10,'retain_as_local_archives','Retain verified maintenance and condition history for asset life plus 10 years. Destroy duplicate field copies after capture into the authoritative system.'),
    (3,'GCS-04.02','GCS-04.02.03','Calibration, Testing and Certification','Calibration results, statutory examinations, test certificates and evidence of equipment fitness for use.','calibration, test certificate, statutory inspection, compliance, equipment',true,7,8,'destruction','Retain certificates and results for asset life plus 7 years, or longer where a safety standard, incident or legal hold requires.'),
    (2,'GCS-04','GCS-04.03','Property, Fleet and Asset Disposal','Property administration, fleet operations, inventory control, surplus handling and disposal.','property, lease, fleet, vehicle, inventory, surplus, disposal',false,NULL,NULL,NULL,NULL),
    (3,'GCS-04.03','GCS-04.03.01','Property and Lease Management','Ownership, leasing, occupancy, valuation and management of land, buildings and premises.','property, land, building, lease, occupancy, valuation, title',true,10,20,'selective_preservation','Retain title and significant property records permanently while owned and for 30 years after disposal. Preserve records of landmark properties; destroy routine occupancy files after expiry.'),
    (3,'GCS-04.03','GCS-04.03.02','Fleet and Mobile Asset Management','Vehicle acquisition, registration, allocation, operation, servicing, incidents and disposal.','fleet, vehicle, registration, allocation, service, accident, fuel',true,5,5,'destruction','Retain fleet histories for 10 years after vehicle disposal. Incident records follow the longer applicable safety, insurance or legal retention period.'),
    (3,'GCS-04.03','GCS-04.03.03','Surplus, Transfer and Asset Disposal','Approval, valuation, transfer, sale, recycling and destruction of surplus or retired assets.','surplus, transfer, auction, sale, recycling, destruction, disposal',true,7,8,'destruction','Retain disposal approvals, valuations, transfer evidence and certificates for 15 years after completion, subject to environmental and audit requirements.');

    FOR level_number IN 1..3 LOOP
        INSERT INTO classifications (
            classification_scheme_id, parent_classification_id, code, title,
            description, authority, scope_note, keywords, is_terminal
        )
        SELECT scheme_id, parent.id, seed.code, seed.title, seed.description,
               'Corporate Records and Information Governance Office',
               CASE seed.hierarchy_level
                   WHEN 1 THEN 'Top-level corporate function applying across the organization.'
                   WHEN 2 THEN 'Functional branch grouping related activities and records.'
                   ELSE 'Assignable terminal class governing the described records and approved retention rule.'
               END,
               seed.keywords, seed.is_terminal
        FROM general_classification_seed AS seed
        LEFT JOIN classifications AS parent
          ON parent.classification_scheme_id = scheme_id
         AND parent.code = seed.parent_code
        WHERE seed.hierarchy_level = level_number;
    END LOOP;

    INSERT INTO classification_retention_rules (
        classification_id, current_period_years, intermediate_period_years,
        final_disposition, instructions
    )
    SELECT classification.id, seed.current_years, seed.intermediate_years,
           seed.final_disposition, seed.instructions
    FROM general_classification_seed AS seed
    JOIN classifications AS classification
      ON classification.classification_scheme_id = scheme_id
     AND classification.code = seed.code
    WHERE seed.is_terminal;

    IF (SELECT count(*) FROM classifications WHERE classification_scheme_id = scheme_id) <> 52 THEN
        RAISE EXCEPTION 'GCS seed did not create exactly 52 classifications';
    END IF;
    IF (
        SELECT count(*) FROM classifications
        WHERE classification_scheme_id = scheme_id AND is_terminal
    ) <> 36 THEN
        RAISE EXCEPTION 'GCS seed did not create exactly 36 terminal classifications';
    END IF;
    IF (
        SELECT count(*)
        FROM classification_retention_rules AS rule
        JOIN classifications AS classification ON classification.id = rule.classification_id
        WHERE classification.classification_scheme_id = scheme_id
    ) <> 36 THEN
        RAISE EXCEPTION 'GCS seed did not create exactly 36 retention rules';
    END IF;

    SET CONSTRAINTS ALL IMMEDIATE;
    RAISE NOTICE 'seeded GCS with 4 roots, 12 branches, 36 terminals and 36 retention rules';
END;
$$;

COMMIT;

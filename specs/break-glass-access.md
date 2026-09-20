# Break-glass authorization — review draft

Status: **not approved and not implemented**

This document exists for separate security, records-management, and operational review. Phase 11 does not create a hidden account, hard-coded role, environment-variable bypass, database trigger bypass, or security-level bypass.

## Proposed purpose

Break-glass access would exist only to recover from the simultaneous loss of all effective authorization administrators or another formally declared emergency that prevents ordinary continuity recovery. It must never become a routine support mechanism.

## Proposed constraints

- Activation requires two named approvers from separate functions, one of whom represents information governance.
- Access is time-limited, single-purpose, and bound to one named person—not a shared credential.
- The credential is generated only at activation, stored outside the application database, and revoked automatically at expiry.
- Activation grants only the minimum administration privileges required to restore ordinary administration.
- It does not bypass resource security clearance, resource ACLs, closure/integrity constraints, or information-governance rules.
- Every activation, authentication, operation, failure, expiry, and revocation produces immutable audit events and an external alert.
- The emergency operator cannot erase or alter audit history.
- Post-incident review and credential rotation are mandatory.

## Decision required before implementation

Reviewers must decide whether an application-level mechanism is needed at all, or whether controlled database/platform recovery under the existing disaster-recovery process is safer. No code should be written until threat modelling, key custody, approval workflow, maximum duration, allowed privilege set, alert destinations, and testing cadence are approved.


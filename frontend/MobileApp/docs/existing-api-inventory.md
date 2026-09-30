# Existing API integration inventory

This Phase 0 inventory identifies the owning existing contracts required by the
approved mobile scope. It does not redefine their request or response shapes.

| Mobile journey | Existing owning contract |
| --- | --- |
| Sign-in, current principal, sign-out, expiry | Authentication subsystem |
| Dashboard, favourites, recent activity | Dashboard and User Favourites |
| Global discovery and diagnostics | Full-Text Search |
| Scheme and hierarchy navigation | Aggregation Classification Browser |
| Aggregation and record presentation | Aggregation and Record Detail contracts |
| Component rendition and viewer audit | Document Viewing and Content Storage |
| Resource history | Event History |
| Visible actions and destinations | Security and Authorization capability responses |
| English, Arabic, direction, dates, and terminology | Internationalization and User Preferences |

No new endpoint is approved by this inventory. Before a feature module is
implemented, its current API methods, pagination boundary, authorization
response, error codes, and concurrency requirements must be traced to its
owning specification and tests.

Known gaps remain governed by section 22 of the mobile specification.

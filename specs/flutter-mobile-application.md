# Wathiq Mobile Application — Flutter UX and Client Specification

## 1. Status and purpose

This document defines the mobile-specific product and client contract for the
Wathiq Flutter application. It covers the mobile experience, application shell,
responsive behavior, client state, use of existing ERMS APIs, and mobile
security boundaries for iOS and Android.

This specification does not redefine any existing ERMS subsystem. Authentication,
authorization, security levels, privileges, profiles, ACLs, governance access,
search semantics, classification rules, record and aggregation behavior,
favourites, event history, content storage, preview generation, localization,
and audit behavior remain governed by their existing approved specifications
and implementation documentation.

The mobile application is a client of those subsystems. Server responses remain
authoritative. Where the desired mobile experience cannot be implemented with
an existing API, this document identifies the gap for separate review; it does
not create or approve a new endpoint.

Implementation phases are intentionally outside the scope of this revision.

## 2. Product intent

Wathiq provides a familiar mobile counterpart to the existing WebUI. It allows
users to access existing ERMS capabilities from phones and tablets without
changing the business rules or security boundaries already enforced by the
server.

The initial target audience is:

- top management;
- system administrators; and
- records administrators.

The eventual mobile product may expose the full set of suitable Wathiq
capabilities. Every destination, resource, field, and action remains conditional
on the authenticated user's server-authorized access. The mobile application
must never infer that a user's target audience, job title, or installed
application grants access.

## 3. Governing principles

### 3.1 Existing contracts remain authoritative

The Flutter client must use existing API contracts and server-derived outcomes.
It must not:

- reproduce authorization policy in Dart;
- calculate effective privileges, ACLs, security clearance, governance access,
  lifecycle permission, or resource visibility locally;
- expose an action merely because a client-side role name appears to permit it;
- reinterpret server validation or concurrency outcomes;
- introduce a mobile-only resource state or workflow; or
- require a change to an implemented subsystem without separate approval.

When an existing subsystem specification and this document overlap, the
existing subsystem specification governs the domain behavior and this document
governs only the mobile presentation and interaction.

### 3.2 Familiarity with the WebUI

The app must preserve Wathiq's recognizable visual identity, terminology,
information hierarchy, icons where suitable, and action meanings. A WebUI user
should recognize the corresponding mobile destination without learning new
domain language.

Mobile layouts may reorganize dense WebUI screens into cards, disclosure
sections, tabs, sheets, or step-based forms. Such adaptation must not change
field meaning, validation, available choices, authorization, or API behavior.

### 3.3 Server-authoritative disclosure

The client renders only destinations and content returned or permitted by the
server. It must not download unauthorized or unnecessary data and hide it after
the fact. Counts, continuation state, empty states, and navigation affordances
must not reveal inaccessible resources.

### 3.4 No unbounded collection loading

Every tenant-grown collection that has a paged existing API must be loaded
incrementally. Reaching the end of currently rendered items may request only
the next bounded page. The client must never request an entire search,
classification hierarchy, aggregation hierarchy, record collection, or event
stream for presentation convenience.

## 4. Supported platforms and form factors

The application must support iOS and Android from its first delivery.

### 4.1 Phones

- Phone use is portrait-only initially.
- The UI must not rotate into a landscape phone layout.
- Primary controls must remain reachable without horizontal scrolling.
- Dense information must wrap, collapse, or move into a secondary surface
  rather than shrink below comfortable readability.

### 4.2 Tablets

- Tablets support portrait and landscape orientations.
- Tablet layouts are responsive expansions of the same navigation and task
  model, not a separate product.
- Available width should reduce avoidable scrolling. For example, dashboard
  cards may form additional columns and fill the visible screen.
- A wider layout may show master and detail regions together where the same
  phone flow would use separate screens.
- Orientation changes must preserve the current destination, selection,
  loaded pages, and meaningful scroll position.

Exact minimum iOS and Android versions remain an implementation decision until
the Flutter and dependency baseline is selected.

## 5. Visual language

The application uses the Wathiq name and follows the established WebUI visual
language as closely as native mobile interaction permits.

- The initial application supports the light appearance only.
- Colors, typography, spacing character, status treatment, icon meaning, and
  visual hierarchy should be derived from the Wathiq WebUI design language.
- Platform-native behavior should be retained where it improves predictability,
  including system back behavior, scrolling physics, text selection, safe-area
  handling, and standard input behavior.
- A desktop control must not be copied literally when it produces a poor mobile
  experience. The mobile alternative must preserve the same task and meaning.
- Long forms may use a step-based presentation with a review step before
  submission.

Screen mockups are not normative artifacts in this document. Mockups will be
created separately for approval when implementation planning begins. An
approved mockup may refine layout but may not silently alter this specification
or an existing subsystem contract.

## 6. Localization and terminology

English and Arabic are first-class from the beginning. Every screen must be
designed and verified in both left-to-right and right-to-left directions.

The canonical application wording is sourced from:

- `frontend/webui/i18n/messages.en.json`; and
- `frontend/webui/i18n/messages.ar.generated.json`.

The Flutter client must reuse the exact active translation associated with an
existing contextual `message_key`. It must preserve established entity names,
action names, status wording, capitalization intent, placeholders, and Arabic
terminology. It must not introduce a synonymous mobile-only label for an
existing concept.

The Arabic generated artifact is a governed merge base and may contain
administrator-curated wording. It must not be regenerated wholesale or treated
as disposable output. Any new mobile-only user-visible message requires a new
contextual key processed through the existing translation-artifact governance
workflow. Inline hard-coded English or Arabic strings are prohibited.

The app must:

- follow the authenticated user's existing effective language preference;
- update direction, alignment, navigation affordances, and icon direction when
  the effective language changes;
- use logical leading and trailing placement rather than hard-coded left and
  right placement;
- preserve mixed Arabic/English and identifier readability;
- use the established date, time, timezone, and number presentation contracts;
  and
- clear user-specific localized state at logout or session expiry.

## 7. Application shell and navigation

### 7.1 Top application bar

The top bar carries Wathiq identity, the current destination title, and the
minimum context-appropriate actions. Global search is the most prominent
cross-application navigation action and appears above ordinary drawer
destinations in the navigation hierarchy.

The compact phone treatment may open the search field as a dedicated search
screen. A tablet may place the field directly in the application bar when
space permits. Both treatments execute the same existing search contract.

### 7.2 Side drawer

The initial side-drawer order is:

1. Global Search
2. Dashboard
3. Classification Browser
4. Favourites
5. Recent Activity
6. User/Profile
7. Sign out

Only destinations currently available to the authenticated user may be shown.
Unavailable administrative or governed destinations are omitted rather than
displayed as disabled promises of access. The drawer must refresh its visible
destinations after authentication state or server-provided capabilities change.

The ordering and grouping may be refined through separately approved mockups.

### 7.3 Back navigation

Back navigation returns to the previous mobile screen and restores its retained
session state. It must not unexpectedly submit a form, repeat a mutation, reset
a classification tree, or discard a search without the confirmation required
by the corresponding workflow.

The platform back gesture and visible back control must have equivalent
results. Returning from an opened result restores the previous query, loaded
pages, filters, hierarchy expansion, and practical scroll position.

### 7.4 Deep links

External deep links into a specific aggregation, record, or component are
deferred. Internal app navigation may still use typed routes so that future
deep-link support does not require redesigning screen ownership.

## 8. Authentication and session experience

### 8.1 Sign-in

The app uses the existing username-and-password authentication flow. It does
not introduce another credential type or authentication endpoint.

Sign-in errors must use the server outcome and established non-disclosing
wording. The app must not reveal whether an account exists or locally reinterpret
inactive, suspended, locked, revoked, expired, or password-change-required
states.

### 8.2 Session storage

Authenticated session material is held only for the life of the app process in
the initial implementation. Sensitive API responses are also held in memory
only. The app must not persist credentials, session tokens, protected resource
responses, document bytes, previews, search results, recent activity, or
favourites to general device storage.

Nonsensitive application configuration and packaged translation assets may be
persistent. Platform logs, crash reports, and diagnostics must not contain
credentials, session tokens, document content, protected metadata, or raw API
responses.

If the user terminates the process, locally held session material disappears
and the next launch requires username and password. The client does not claim
that process termination revoked or audited the still-existing server session.
The server's existing expiry and cleanup behavior remains authoritative.

### 8.3 Background timeout

The initial mobile rule is based on time continuously spent in the background:

- the threshold is 15 minutes;
- server expiry or revocation always takes precedence;
- returning before 15 minutes resumes the active session, subject to server
  validation;
- returning at or after 15 minutes discards local session state and presents
  sign-in; and
- successful reauthentication starts at the Dashboard rather than restoring
  the prior protected screen.

At the 10-minute point the app may issue one best-effort local device warning
that sign-in will soon be required. This is a local notification, not a server
push notification. Its delivery is subject to platform permission, operating
system scheduling, and application lifecycle constraints. Failure to deliver
the warning must not extend the session or alter the 15-minute rule.

An interaction-based inactivity timeout is deferred as an improvement. It
should eventually count meaningful navigation, scrolling, searching, input, or
actions rather than passive rendering or background refresh.

### 8.4 Explicit sign-out

Explicit Sign out invokes the existing logout operation before clearing local
state. Regardless of the response, the client returns to sign-in and removes
all user-specific in-memory state. A retry must not retain protected screens.

### 8.5 Session identification

Mobile requests must provide a stable, truthful user-agent description that
allows the existing session-administration experience to distinguish Wathiq
mobile sessions and platform family. It must not include a persistent device
fingerprint or unnecessary personal data.

Biometric and PIN re-entry are deferred. They must not be represented as
available controls until separately specified and approved.

## 9. Dashboard experience

### 9.1 Data boundary

The Dashboard uses the existing consolidated dashboard-summary request. It must
not fan out into separate entity, count, favourite, recent-activity,
classification, or ownership requests to assemble dashboard cards.

One downward pull refreshes the entire dashboard. Only one summary request may
be active at a time; repeated refresh gestures reuse, await, or decline the
active request. Existing rendered content remains visible during refresh.

Because the API returns one consolidated response, a request-level failure is a
dashboard-level failure. After a successful response, sections render as
independent visual units so an empty or inapplicable section does not disturb
the others.

### 9.2 Content priority

Dashboard information is presented in this product priority:

1. authorized summary information;
2. personal recent activity;
3. personal favourites;
4. review warnings; and
5. remaining dashboard information returned for the user.

The precise card arrangement may adapt to device width. The mobile client must
not manufacture a metric missing from the consolidated response or broaden the
server-authorized dashboard scope.

### 9.3 Favourites preview

The dashboard shows at most three favourite entries in its compact preview. A
clear navigation action opens the dedicated Favourites screen containing the
complete authorized collection already returned by the existing favourites
contract.

Adding or removing a favourite is available through the established heart
control on applicable aggregation and record surfaces. The client updates the
affected visible item without reloading unrelated dashboard content and
reconciles with the next dashboard refresh.

### 9.4 Recent-activity preview and expansion

The first dashboard request asks for five recent-activity items. When the user
reaches the end of that section, the client may refresh the consolidated
summary with the recent limit increased by five: 10, 15, and so on, up to the
existing maximum of 50.

This interaction must not capture the dashboard's primary scroll or prevent
the user from moving to later dashboard sections. It must preserve already
rendered content while the larger response is requested, prevent overlapping
requests, and remove duplicates by stable resource identity and activity
context.

No current API supports a continuation after 50. The UI must end truthfully at
that boundary and must not imply that all historical activity has been loaded.

### 9.5 Phone and tablet arrangement

On phones, dashboard sections form one natural vertical page. On tablets,
cards should use the additional width and height so that information that fits
comfortably on screen is not forced into unnecessary vertical scrolling.
Independent nested scroll regions should be avoided unless their behavior is
unambiguous and does not trap the page scroll.

## 10. Global search experience

Global search uses the existing full-text search behavior without redefining
query semantics, indexing state, result ranking, authorization, diagnostics,
or matched-component behavior.

### 10.1 Search entry

- The primary entry is a single clearly labelled query field.
- Submitting opens or updates the results screen.
- The initial experience does not expose the Advanced Search query builder.
- Search diagnostics are a secondary action shown only when the existing
  server authorization permits them.

### 10.2 Incremental results

- The first request asks for 25 results.
- Reaching the end requests only the next 25 through the existing pagination
  contract.
- The client never requests the full result set.
- Only one next-page request may be active for a query and result context.
- A changed query invalidates outstanding requests and previously issued
  continuation state.
- Appended pages are deduplicated without rebuilding already rendered cards.
- A next-page failure retains earlier results and provides an inline Retry
  action.
- Empty, indexing/freshness, unsupported-preview, and terminal-result states
  remain truthful to the existing server response.

### 10.3 Result navigation

- An aggregation result opens Aggregation Details.
- A record result opens Record Details.
- A matched digital component opens the existing document-view experience at
  that component.
- Returning restores the query, loaded results, and practical scroll position.
- Search state remains in memory for the active session and is cleared at
  logout or session expiry.

## 11. Classification browsing

Classification browsing reuses the existing browse endpoints and their opaque
cursor semantics. The Flutter client does not reconstruct the hierarchy from a
bulk download.

### 11.1 Scheme entry

The app requests the schemes visible through the existing contract and then:

- shows the scheme list when more than one scheme is returned;
- opens the classification browser directly when exactly one scheme is
  returned; and
- shows the established empty or unavailable state when none are returned.

No client-side user-to-scheme membership rule is introduced.

### 11.2 Hierarchy interaction

- Selecting a scheme loads only its first root page.
- Expanding a node loads only that node's immediate collection.
- Child aggregations and records are separate paged collections.
- Mobile requests 25 items per collection page.
- Reaching a collection boundary requests only its next opaque cursor.
- Loaded ancestors, sibling collections, selection, and scroll state remain
  stable while a page is appended.
- Stale responses from an earlier scheme, node, filter, or ordering context are
  ignored.
- Failure in one branch retains other loaded branches and offers an inline
  Retry action.

The phone flow may use separate hierarchy and detail screens. A tablet may use
a master-detail layout. Both use the same loaded state and navigation outcome.

### 11.3 Destination path

The authorized journey can continue from schemes and classifications through
aggregations, child aggregations, records, Record Details, and document
preview. Each transition uses the current server-authorized representation.

## 12. Aggregation and record details

### 12.1 Read presentation

Aggregation and Record Details must display all metadata and details made
available to the user through the corresponding existing read contract. Mobile
may reorganize this information into a concise header and clearly labelled
sections, but it must not omit a returned governed field merely to simplify the
layout.

Long values wrap. Optional empty values follow established empty-value
presentation. Identifiers, dates, status, containing relationships, ownership,
classification, medium, location, retention, hold, security, and other domain
values retain their established terminology and semantics without being
redefined here.

Record Details includes the visible digital-component collection and navigation
to preview. Aggregation Details incrementally loads child aggregations and
records in 25-item pages when the existing paged browse contract is used.

### 12.2 Favourites

Applicable aggregation and record detail surfaces provide the established
add/remove favourite control. The state is private to the signed-in user and is
discarded from client memory at sign-out while remaining persisted by the
existing server subsystem.

### 12.3 Event history

Aggregation and record event history is available from the detail experience
only when permitted by the existing server authorization. The mobile client
uses the existing history contract and presentation terminology. It must not
infer missing history or expose raw audit payloads beyond the authorized API
response.

### 12.4 Metadata editing boundary

The baseline mobile detail experience is read-only apart from favourites and
preview navigation. Metadata editing is an intended later mobile capability for
users whose existing server authorization and resource capabilities allow it.

When introduced, editing must use the existing mutation endpoints and preserve
their complete validation, optimistic concurrency, reason, confirmation,
capability, and error contracts. Step-based mobile forms are preferred for long
forms. No field, validation rule, permission, or lifecycle exception may be
invented for mobile convenience.

## 13. Favourites screen

The dedicated Favourites destination presents the authenticated user's complete
authorized aggregation and record favourites returned by the existing API.

- Aggregations and records remain distinguishable without relying on color
  alone.
- Selecting an entry opens its corresponding detail screen.
- A filled heart removes that favourite without opening the entry.
- Removal updates the full collection and dashboard preview immediately.
- Empty and error states do not imply that a formerly visible resource still
  exists.
- The screen is scrollable but does not issue artificial per-item hydration
  requests.

The current favourites endpoint returns the complete authorized collection.
The app must not pretend that this response is server-paginated.

## 14. Recent Activity screen

Recent Activity is available as both a dashboard section and a drawer
destination. It begins with five entries and can increase the requested limit
in increments of five up to 50 using the existing API limit.

Selecting an aggregation or record opens the corresponding details. Selecting
activity attributed from a component view follows the existing resource
attribution and does not expose a separate unauthorized component entry.

The screen must distinguish loading more, refreshing, empty, authorization
loss, and terminal 50-item states. It must not describe the first 50 as the
user's complete history.

## 15. Document viewing

Document viewing uses the existing authorized rendition behavior and supports
the formats already previewable by Wathiq. The mobile specification does not
add a conversion format or alter rendition security.

### 15.1 Viewer capabilities

Where supported by the current preview representation, the viewer provides:

- in-document search;
- page navigation;
- zoom;
- rotation;
- thumbnail navigation;
- current-page and total-page feedback; and
- switching between authorized components of the same record without leaving
  the viewer.

Loading and conversion use an indeterminate preparation state because the
existing rendition operation does not provide progress percentage. Unsupported,
failed, deleted, or newly unauthorized content produces the established
non-disclosing error treatment and a safe route back to the record.

### 15.2 Deferred content actions

The following mobile actions are deferred:

- downloading originals;
- opening content in another application;
- operating-system sharing;
- printing; and
- screenshot and screen-recording prevention.

Until screenshot prevention is separately approved and implemented, the app
must not claim that the operating system prevents capture.

## 16. Offline and connectivity behavior

The initial application is online-only. It does not provide offline login,
offline browsing, persistent protected caches, downloaded document access,
queued mutations, or conflict reconciliation.

When connectivity is lost:

- already rendered information remains visible in the background;
- a centered offline popup clearly states that connection is unavailable;
- actions requiring server confirmation are disabled;
- protected information is not written to persistent storage;
- the app monitors for reconnection without generating uncontrolled request
  loops; and
- after reconnection, the user can retry or the current safe read may revalidate
  according to the approved screen behavior.

The popup must not erase rendered information, misrepresent it as current, or
allow dismissal into an apparently interactive but disconnected screen.
Server session expiry during the outage still takes precedence when connection
returns.

## 17. Loading, refresh, errors, and authorization changes

### 17.1 Loading

Each screen distinguishes initial loading from incremental loading. Initial
loading may use skeletons or a restrained progress state. Loading another page
must preserve already rendered items and navigation context.

### 17.2 Pull-to-refresh

Pull-to-refresh revalidates the current screen's complete safe read model. On
the Dashboard it always refreshes the single consolidated dashboard response.
It must not start duplicate requests or blank valid content while waiting.

### 17.3 Retry

Every failed initial read or incremental page request offers a context-appropriate
Retry action. A page-level retry must not reset unrelated navigation state. A
failed dashboard summary is retried as one dashboard request because its
sections do not have independent API requests.

### 17.4 Revocation and unavailable content

If a session is revoked or expires, the app clears protected in-memory state and
shows sign-in with a concise message. After successful sign-in it opens the
Dashboard.

If a resource becomes unauthorized, deleted, or unavailable while open, the app:

- removes protected details from the active presentation;
- shows a clear, non-disclosing message;
- removes stale navigation state for that resource; and
- returns the user to the nearest safe destination.

The client must not distinguish "not found" from "not permitted" when the
existing API deliberately uses a non-disclosing response.

## 18. Client state and request coordination

All user-specific feature state is scoped to the active in-memory session.
This includes:

- visible navigation destinations;
- dashboard data;
- search query, pages, filters, and scroll position;
- selected scheme, expanded classification paths, loaded child pages, and
  selection;
- favourites and recent activity;
- detail representations and capability responses; and
- document-viewer component and page position.

Logout, session expiry, or process termination clears this state. Signing in as
another user must never reuse the previous user's state.

The client must cancel or disregard obsolete asynchronous responses. A response
belonging to a prior user, query, route, scheme, resource version, or refresh
generation must not populate the current screen.

Reads that are safe to share within one screen generation may reuse a single
in-flight request. Mutations must never be automatically repeated unless the
existing operation is explicitly safe and the user remains informed.

## 19. Mobile security and privacy

- Transport and deployment security follow the existing ERMS deployment
  contract.
- Protected data is not persisted for offline use in the initial application.
- Secrets and content must not appear in logs, analytics, screenshots produced
  by automated tests, or crash payloads.
- Clipboard behavior must be deliberate for sensitive fields and content.
- The app must not embed third-party content viewers, analytics, or services
  that receive Wathiq content without separate approval.
- A hidden UI action is not a security boundary; every operation remains
  server-authorized.
- Mobile user-agent identification must be truthful but privacy-minimizing.

Rooted/jailbroken-device policy, managed-device enforcement, certificate
pinning, screenshot blocking, and public-versus-private store distribution
remain undecided and require separate review before becoming requirements.

## 20. Performance requirements

- App startup must not preload feature collections before authentication.
- After authentication, only data required for the initial destination is on
  the critical path.
- Dashboard data comes from one consolidated request.
- Global search pages contain 25 results.
- Classification, child-aggregation, and record browse pages contain 25 items
  per collection request.
- Recent activity begins at five and expands in increments of five, with a
  current maximum of 50.
- The client prevents overlapping requests for the same collection and context.
- Appending a page must not rebuild an entire hierarchy or discard earlier
  pages.
- Large lists use lazy rendering so off-screen widgets do not create avoidable
  memory or layout cost.
- Optional assets and secondary destinations must not delay the initial
  authenticated screen.
- Phone and tablet performance must be verified in English and Arabic.

## 21. Existing integration boundaries

The mobile implementation must consume, not replace, the existing contracts for:

- login, logout, current principal, and session expiry;
- consolidated dashboard summary;
- favourites;
- personal recent activity;
- global full-text search and authorized diagnostics;
- classification and aggregation browsing;
- aggregation and record details;
- record digital components and rendition viewing;
- event history;
- server-derived capabilities and authorization outcomes; and
- user language preferences and governed translations.

Endpoint shapes, domain semantics, and audit rules remain in their owning
specifications and implementation documentation. This list is an integration
inventory, not a duplicate mobile definition of those subsystems.

## 22. Known API and platform gaps requiring later review

The following desired improvements are not part of the current API contract and
are not approved by this specification:

### 22.1 Push notifications

ERMS has no notification subsystem or mobile device-registration and delivery
contract. Event-driven push notifications require separate product, privacy,
security, API, token-lifecycle, preference, and audit design.

### 22.2 Recent-activity continuation beyond 50

The existing recent-activity and dashboard contracts accept a bounded limit but
no cursor or offset. The current mobile experience can expand from five to 50
by re-requesting a larger limit. True continuation beyond 50 and elimination of
repeated earlier rows would require a separately approved server-pagination
enhancement.

### 22.3 Force-termination audit distinction

Mobile operating systems do not reliably allow a network request when a user
terminates an app. The client can discard its in-memory session, but the server
cannot truthfully record "mobile app force-closed" under the existing contract.
The server will later record its normal session-expiry outcome. A distinct
termination event would require separate design and must not be simulated.

### 22.4 Future deep links

External universal/app links require an approved URL-routing, authentication,
authorization, stale-target, and deployment association contract. Internal
typed navigation alone does not approve external deep linking.

## 23. Deferred mobile capabilities

The following are intentionally deferred without being rejected from the
eventual product:

- Advanced Search visual query builder;
- metadata editing and other governed mutations;
- biometric or PIN re-entry;
- interaction-based inactivity timing;
- offline access, protected caching, and queued work;
- push notifications;
- external deep links;
- downloads, external opening, sharing, and printing;
- screenshot and screen-recording prevention;
- dark appearance;
- phone landscape layouts;
- a formal accessibility conformance target;
- rooted/jailbroken-device and managed-device policy; and
- final application distribution channel.

Deferral does not authorize an implementation shortcut. Each capability must be
specified or explicitly brought into scope before implementation.

## 24. Repository location and ownership boundary

All Flutter mobile application source code, platform projects, tests,
configuration, project-local tooling, assets, generated localization inputs,
and mobile-specific documentation must be stored beneath:

```text
frontend/MobileApp/
```

The Flutter package name may use the Dart-compatible identifier
`wathiq_mobile`; the required repository directory remains `MobileApp`.

Mobile implementation must not place application code in `frontend/webui`, the
backend services, database directories, or another top-level mobile directory.
Changes outside `frontend/MobileApp` are permitted only when an approved mobile
requirement genuinely requires a shared contract or repository-level
configuration change. Such a change must be identified, reviewed, and tested
against the owning subsystem before it is made.

The existing English and Arabic catalogue files remain canonical in
`frontend/webui/i18n`. The mobile build may consume a validated, generated, or
copied project-local representation beneath `frontend/MobileApp`, but it must
not fork the wording or establish an independent translation authority.

## 25. Development environment prerequisites

The development environment must be prepared for both iOS and Android before
mobile implementation begins. Installing an editor extension alone is not a
complete Flutter toolchain.

### 25.1 Common tooling

Every developer workstation requires:

- an Apple Silicon or otherwise Flutter-supported macOS development machine
  when the workstation is expected to build both iOS and Android;
- Git;
- Visual Studio Code;
- the Flutter SDK on the current stable channel;
- the Dart SDK bundled with that Flutter SDK; and
- network access to the approved Flutter, Dart, Apple, Android, and project
  dependency sources during controlled dependency installation.

The repository must record and deliberately update its supported Flutter/Dart
baseline when the Flutter project is scaffolded. Developer machines and CI must
use that recorded baseline rather than silently floating between incompatible
SDK versions.

### 25.2 Visual Studio Code

VS Code requires the official **Flutter** extension published under
`Dart-Code.flutter`. Installing it also installs the official **Dart** extension
under `Dart-Code.dart-code`. Flutter DevTools is supplied through the Flutter
toolchain and is available from VS Code while a Flutter debug session is active.

No third-party theme, code-generation, state-management, lint, AI, or device
extension is a project prerequisite unless it is separately evaluated and added
to the repository's documented toolchain.

VS Code must be configured to use the repository-approved Flutter SDK path. A
developer validates the editor integration through **Flutter: Run Flutter
Doctor** and confirms that Flutter commands, Dart analysis, device selection,
debugging, hot reload, and DevTools are available.

### 25.3 iOS tooling

An iOS-capable workstation requires:

- the current project-supported Xcode version;
- Xcode command-line tools selected for that Xcode installation;
- reviewed and accepted Apple/Xcode licences;
- the required iOS platform and Simulator runtime;
- CocoaPods for Flutter plugins that use native iOS dependencies; and
- an Apple ID and development signing configuration when testing on a physical
  device.

App Store distribution credentials, organization signing ownership, bundle
identifier, and distribution channel remain release decisions and are not
implied by a successful local toolchain check.

### 25.4 Android tooling

An Android-capable workstation requires:

- the current stable Android Studio;
- an Android SDK location recognized by Flutter;
- the project-selected Android SDK Platform;
- Android SDK Build-Tools;
- Android SDK Command-line Tools;
- Android SDK Platform-Tools;
- Android Emulator;
- CMake and the side-by-side NDK when required by the selected Flutter version
  or native dependencies;
- a compatible JDK; and
- reviewed and accepted Android SDK licences.

The initial environment should install Android API level 36, matching the
current Flutter setup guidance at the time this prerequisite was recorded. The
project must pin its compile/target SDK and native-tool versions when the
Flutter project is created; a later SDK change is an explicit toolchain update,
not an incidental local-machine change.

At least one hardware-accelerated ARM-compatible phone emulator and one tablet
emulator should be configured on Apple Silicon. Physical-device testing
requires Android Developer options and authorized USB or wireless debugging.

### 25.5 Local validation gate

Before the first mobile project commit, the development workstation must pass:

```text
flutter doctor -v
flutter devices
flutter emulators
```

The validation record must confirm:

- Flutter and its bundled Dart SDK are found at the intended path;
- the VS Code Flutter and Dart extensions are active;
- Xcode, CocoaPods, and at least one iOS Simulator runtime are available;
- Android Studio, the Android SDK, required SDK tools, and accepted licences are
  available;
- at least one iOS simulator and one Android emulator or physical device can be
  selected; and
- no unresolved Flutter Doctor issue affects either target platform.

License acceptance is a human legal action. Setup scripts and automation must
not silently accept Apple or Android licences on a developer's behalf.

### 25.6 Verified bootstrap workstation

On 30 September 2026, the initial Apple Silicon development workstation was
verified with:

- Flutter 3.47.5 stable;
- Dart 3.13.4 and DevTools 2.60.0 from that Flutter SDK;
- VS Code with Flutter and Dart extensions 3.142.0;
- Xcode 27.0;
- CocoaPods 1.17.0;
- Android Studio 2026.1.4.8;
- Android SDK Command-line Tools 15859902;
- OpenJDK 17; and
- Git 2.54.0.

Flutter Doctor passed the Flutter, Xcode/iOS, VS Code-accessible Flutter
tooling, connected local targets, and network checks. Android Studio and the
command-line tools were installed, but the Android SDK platforms/tools, SDK
location, licences, and emulator still required completion through the Android
Studio setup workflow. The environment is not considered Android-ready until
the local validation gate in section 25.5 passes.

These observed versions document the bootstrap environment; they do not replace
the repository-pinned toolchain baseline required when the Flutter project is
created.

## 26. Recommended delivery phases

Each phase must preserve the existing subsystem contracts, use only approved
APIs, and finish with focused automated verification plus approved phone and
tablet mockups for the user-facing work introduced by that phase. English,
Arabic, LTR, RTL, iOS, Android, phone, and tablet implications are part of each
phase rather than a final translation or responsiveness pass.

### Validation contract for every phase

Beginning with Phase 0, every implementation unit must be delivered with a
corresponding validation check. An implementation unit is the smallest
independently meaningful behavior or boundary introduced by a change, such as
a parser, configuration rule, state transition, API adapter, widget, route,
responsive layout, platform configuration, or generated artifact.

For every unit, the same change must:

- identify the requirement and owning specification section;
- identify the implementation location;
- add or update an automated unit, widget, integration, contract, static, or
  platform check at the lowest effective test level;
- cover the successful outcome and applicable invalid, empty, boundary,
  failure, stale, cancellation, authorization, language, direction, and device
  variants;
- prove that a failure produces the specified safe state rather than only
  proving the successful path;
- retain the check as a regression test for later phases; and
- record the requirement-to-implementation-to-check mapping in the phase
  validation matrix.

A unit is not complete merely because it compiles, renders once, or passes
manual inspection. Visual units additionally require focused widget or golden
checks where stable and live device/simulator review for the applicable phone,
tablet, English, Arabic, LTR, and RTL combinations. API-facing units require
contract checks against the existing response, error, pagination, concurrency,
and authorization boundaries; they must not replace server authorization with
client assumptions.

Every defect correction must add a regression check that fails for the observed
defect before or together with the correction. Generated artifacts require a
repeatable validator that detects drift from their canonical source. Platform
configuration requires automated inspection where practical plus a real build
or runtime check on the affected platform.

The complete affected validation set, static analysis, and formatting checks
must pass before a unit is reported complete. A phase cannot pass its exit gate
while any delivered unit lacks validation evidence, while the validation matrix
has an unresolved row, or while a relevant check is skipped without an approved
and documented reason.

### Phase 0 — Product and technical foundation

Phase 0 establishes the implementation baseline without delivering governed
business workflows.

Required work:

- complete and validate the iOS and Android development toolchains;
- scaffold the Flutter application beneath `frontend/MobileApp`;
- record the approved Flutter, Dart, iOS, Android, Java, and dependency
  baseline;
- define project structure, routing, state ownership, HTTP boundaries,
  cancellation, error mapping, and test conventions;
- inventory the existing APIs required by the approved mobile scope;
- establish Wathiq mobile design tokens without copying WebUI-only CSS;
- establish validated ingestion of the canonical English and Arabic message
  catalogues;
- implement a non-governed shell prototype for LTR, RTL, phone, and tablet
  layout verification;
- establish sensitive logging, in-memory secret, and environment-configuration
  rules;
- establish the validation matrix and automated check conventions required for
  every Phase 0 and later implementation unit;
- create and approve mockups for authentication, navigation, loading, empty,
  error, offline, phone, and tablet foundations; and
- prove connectivity to an approved non-production ERMS environment without
  embedding credentials or environment secrets.

Exit gate:

- the project builds and its tests and static analysis pass on the pinned
  toolchain;
- every delivered Phase 0 unit has a mapped automated check and the validation
  matrix contains no unresolved delivered-unit row;
- empty bilingual builds run on iOS and Android targets;
- the source tree and generated artifacts respect section 24;
- no new endpoint, authorization rule, domain workflow, or production secret
  has been introduced; and
- all unresolved platform or API prerequisites are recorded truthfully.

### Phase 1 — Authentication and application shell

Phase 1 delivers the shared secure experience used by all later workflows:

- existing username/password authentication and required credential-state
  handling;
- server-authoritative principal and destination visibility;
- the approved side drawer and global-search entry;
- complete English/Arabic and LTR/RTL shell behavior;
- phone portrait and responsive tablet orientation behavior;
- explicit sign-out and protected state clearing;
- the 15-minute background timeout and best-effort 10-minute warning;
- process-restart credential requirements;
- mobile user-agent identification;
- central loading, retry, revocation, non-disclosing error, and offline
  presentation; and
- isolation of every user's in-memory state.

Exit gate: authentication and shell behavior work on both platforms and in both
languages without client-side authorization reconstruction.

### Phase 2 — Read-only content foundation

Phase 2 delivers reusable authorized content destinations:

- Aggregation Details with all returned authorized metadata;
- Record Details with all returned authorized metadata;
- responsive information grouping;
- child aggregation and record collections in bounded 25-item pages;
- authorized event-history presentation;
- add/remove favourite controls;
- safe deleted, revoked, unavailable, and newly unauthorized states;
- retained Back-navigation state; and
- shared resource-card presentation for later discovery workflows.

Exit gate: authorized aggregation and record representations can be opened and
navigated without duplicating domain or authorization policy in Flutter.

### Phase 3 — Dashboard, favourites, and recent activity

Phase 3 delivers the first management-oriented workspace:

- one consolidated dashboard-summary request;
- single-swipe whole-dashboard refresh;
- authorized summary information;
- recent activity beginning at five and expanding by five to 50;
- a three-item favourites preview;
- dedicated Favourites and Recent Activity screens;
- navigation from favourites and activity to details;
- non-destructive refresh and retry behavior; and
- responsive tablet use of available screen space without trapped scrolling.

Exit gate: the mobile dashboard truthfully reflects the authenticated user's
existing dashboard contract without client request fan-out.

### Phase 4 — Document-viewing experience

Phase 4 delivers the governed viewer over the existing rendition boundary:

- every currently previewable format;
- preparation and conversion states;
- supported PDF search, page navigation, zoom, rotation, and thumbnails;
- authorized component switching within a record;
- unsupported, failed, deleted, and authorization-loss states; and
- verification that no deferred download, share, print, or external-open
  action is exposed.

Exit gate: each current Wathiq preview outcome has a verified mobile result on
iOS and Android without altering content-storage or rendition behavior.

### Phase 5 — Global full-text search

Phase 5 delivers the primary discovery workflow:

- the main global query field;
- bounded 25-result initial and continuation requests;
- aggregation, record, and matched-component results;
- navigation into details and the focused component viewer;
- retained query, loaded pages, and scroll state;
- incremental retry without destructive reload;
- existing indexing and freshness presentation; and
- authorized diagnostics as a secondary action.

The Advanced Search query builder remains deferred from this phase.

Exit gate: authorized discovery remains bounded, stable, non-disclosing, and
consistent with the existing full-text search contract.

### Phase 6 — Classification browsing

Phase 6 delivers hierarchical discovery:

- the approved zero-, one-, or multiple-scheme entry behavior;
- existing opaque-cursor hierarchy navigation;
- 25-item pages for each independently loaded collection;
- stable expansion, selection, loaded state, and scroll position;
- branch-local loading, empty, failure, and retry states;
- phone hierarchy-to-detail navigation;
- tablet master-detail presentation where approved; and
- navigation through aggregations, records, and document preview.

Exit gate: no hierarchy is bulk-downloaded and an individual branch failure
does not destroy unrelated loaded state.

### Phase 7 — Metadata editing and governed records actions

Phase 7 introduces mutations for users already authorized by the server:

- server-authorized edit actions only;
- step-based mobile forms for dense metadata;
- existing field definitions, choices, validation, and commands;
- optimistic concurrency and conflict recovery;
- required reasons, confirmations, and impact presentation;
- capability revalidation before submission;
- protection against automatic mutation retries; and
- existing audit outcomes.

An action enters this phase only after its current API is confirmed to support
the complete mobile workflow. Missing support is raised for separate review and
must not be bypassed.

Exit gate: included mutations produce the same governed result as the WebUI
without changing subsystem rules.

### Phase 8 — Advanced and administrative parity

Phase 8 expands toward suitable WebUI parity. The recommended order is:

1. Advanced Search query building and saved searches;
2. remaining records-administration workflows;
3. legal-hold and governance views;
4. user, role, and organization administration;
5. security, ACL, and access-explanation administration;
6. classification and translation administration; and
7. operational and diagnostic surfaces suitable for mobile.

Each capability requires its own API-compatibility review and approved mobile
mockups. Dense WebUI surfaces must become comprehensible mobile task flows, not
compressed desktop tables.

Exit gate: each included administrative workflow preserves its existing server
contract and remains usable at phone width.

### Phase 9 — Production hardening and release readiness

Phase 9 prepares a release candidate through:

- complete iOS and Android regression suites;
- physical phone and tablet verification;
- English/Arabic visual and behavioral review;
- revocation, authorization-change, network-loss, and recovery testing;
- performance, memory, large-result, hierarchy, and viewer stress testing;
- sensitive logging and persistence review;
- dependency and package security review;
- crash and restoration testing;
- reproducible signing and environment configuration;
- a distribution-channel decision; and
- operational support and upgrade documentation.

Exit gate: signed release candidates pass the approved security, UX,
performance, localization, and server-compatibility gates.

The improvements listed in section 23 remain outside these phases until their
own prerequisites and specifications are approved. In particular, push
notifications and recent-activity continuation beyond 50 require separately
reviewed server changes.

## 27. Mobile-specific verification requirements

Verification must cover the mobile behavior defined here without retesting or
redefining the internal correctness of established subsystems.

### 27.1 Platforms and responsive layout

- Supported iOS and Android builds launch and authenticate against the same
  approved server contract.
- Phones remain portrait-only.
- Tablets retain state across portrait and landscape transitions.
- Phone and tablet layouts contain no unintended horizontal scrolling,
  clipped actions, or inaccessible content.

### 27.2 English and Arabic

- Every active mobile message resolves through the governed catalogue.
- Existing concepts use the exact existing English and Arabic translations.
- RTL mirrors layout and navigation appropriately without reversing identifiers
  or corrupting mixed-direction text.
- Both languages are checked on phone and tablet layouts.

### 27.3 Authentication and isolation

- Server expiry and revocation supersede client timing.
- Fifteen minutes continuously in the background requires a new sign-in.
- The optional 10-minute local warning cannot extend the session.
- Process restart requires username and password.
- Explicit sign-out uses the existing logout operation.
- Logout, expiry, and user changes clear all protected client state.
- Existing session administration can recognize the Wathiq mobile user agent.

### 27.4 Navigation and authorization changes

- The drawer contains only currently available destinations in the specified
  order.
- Back navigation restores retained in-session list and hierarchy state.
- Revoked, deleted, or newly unauthorized resources are removed and replaced
  by a non-disclosing message and safe navigation.
- A stale response from a previous user or context cannot populate the UI.

### 27.5 Bounded data access

- Search requests and appends 25 results at a time.
- Classification and aggregation branches request 25 items per collection.
- No hierarchy or search workflow downloads its full collection.
- Recent activity begins with five and expands by five only at its boundary,
  never beyond the current API maximum of 50.
- Incremental failures retain earlier items and expose Retry.
- Duplicate request and stale-response guards are exercised under rapid
  navigation and repeated scrolling.

### 27.6 Dashboard

- One pull gesture produces at most one consolidated dashboard request.
- Existing dashboard content remains visible during refresh.
- The favourites preview shows no more than three entries.
- Recent-activity expansion does not trap or hijack dashboard scrolling.
- A dashboard request failure is presented honestly as a dashboard-level
  failure.
- Tablet layouts use available space without changing dashboard meaning.

### 27.7 Details, favourites, history, and preview

- All metadata returned by an authorized detail contract is reachable and
  readable in the mobile layout.
- Favourite addition and removal remain synchronized across details, dashboard,
  and the Favourites screen.
- Event history is reachable only when authorized.
- Every currently previewable format follows the existing preview outcome.
- Component switching, PDF search, page navigation, zoom, rotation, and
  thumbnails work where supported.
- No deferred download, share, print, or external-open control is exposed.

### 27.8 Connectivity

- Loss of connectivity leaves rendered information behind a centered offline
  popup.
- Server-dependent actions cannot proceed while offline.
- Reconnection does not create a request storm or silently repeat a mutation.
- Server session expiry during an outage is enforced when connectivity returns.

## 28. Acceptance criteria for this specification

The mobile product conforms to this specification when:

1. it behaves as a client of existing ERMS subsystems without duplicating or
   weakening their rules;
2. it introduces no unapproved API endpoint, privilege, resource, workflow, or
   server state;
3. its iOS and Android experiences provide the defined phone and tablet
   behavior;
4. English and Arabic use the governed Wathiq catalogue and terminology;
5. navigation and content are driven by server-authorized availability;
6. dashboard, search, recent activity, and hierarchy access remain bounded as
   specified;
7. protected data and session state are memory-only in the initial online-only
   application;
8. document preview uses the existing rendition boundary and omits deferred
   content-export actions;
9. revocation, expiry, authorization loss, connectivity loss, and partial-page
   failures produce truthful, recoverable mobile states; and
10. every identified API gap remains a proposal for separate review rather
    than an assumed dependency.

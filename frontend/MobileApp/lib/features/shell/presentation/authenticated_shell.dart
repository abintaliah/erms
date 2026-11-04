import 'package:flutter/material.dart';

import '../../../core/design/wathiq_brand.dart';
import '../../../core/localization/message_catalogue.dart';
import '../../auth/application/session_controller.dart';
import '../../preferences/presentation/preferences_screen.dart';

class AuthenticatedShell extends StatelessWidget {
  const AuthenticatedShell({
    required this.catalogue,
    required this.controller,
    super.key,
  });

  static const tabletBreakpoint = 700.0;

  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    String text(String key) => catalogue.text(key, locale);
    final principal = controller.principal!;
    final appName = text('webui.index.label.wathiq_d1dfb800');
    final dashboard = text('navigation.item.dashboard');
    final signOut = text('webui.index.button.sign_out_a4610dd4');
    final preferences = text('preferences.action.open');
    final profile = text('mobile.navigation.user_profile');
    final entries = <_ShellDestination>[
      _ShellDestination(
        'global-search',
        text('mobile.navigation.global_search'),
        Icons.search,
      ),
      _ShellDestination(
        'classification-browser',
        text('mobile.navigation.classification_browser'),
        Icons.account_tree_outlined,
      ),
      _ShellDestination(
        'favourites',
        text('mobile.navigation.favourites'),
        Icons.star_outline,
      ),
      _ShellDestination(
        'recent-activity',
        text('mobile.navigation.recent_activity'),
        Icons.history,
      ),
    ].where((entry) => controller.destinations.contains(entry.id)).toList();
    Future<bool> authorizeNavigation() async {
      final allowed = await controller.authorizeNavigation();
      return context.mounted && allowed;
    }

    void openDestination(_ShellDestination entry) async {
      if (!await authorizeNavigation()) return;
      if (!context.mounted) return;
      if (!controller.destinations.contains(entry.id)) return;
      // Phase 1 owns navigation; resource workflows are delivered in phases 3, 5 and 6.
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => Scaffold(
            key: ValueKey('destination-${entry.id}'),
            appBar: AppBar(title: Text(entry.label)),
            body: SafeArea(
              child: Align(
                alignment: AlignmentDirectional.topStart,
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    entry.label,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final tablet = constraints.maxWidth >= tabletBreakpoint;
        final navigation = _ShellNavigation(
          appName: appName,
          entries: entries,
          onDestination: openDestination,
          dashboardLabel: dashboard,
          preferencesLabel: preferences,
          profileLabel: profile,
          showDashboard: controller.destinations.contains('dashboard'),
          showProfile: controller.destinations.contains('user-profile'),
          showSignOut: controller.destinations.contains('sign-out'),
          signOutLabel: signOut,
          userName: principal.user.localizedName ?? principal.user.name,
          userEmail: principal.user.email,
          authorizeNavigation: authorizeNavigation,
          onDashboard: tablet
              ? null
              : () async {
                  if (!await authorizeNavigation()) return;
                  if (!context.mounted) return;
                  Navigator.pop(context);
                },
          onPreferences: () async {
            if (!await authorizeNavigation()) return;
            if (!context.mounted) return;
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => PreferencesScreen(
                  catalogue: catalogue,
                  controller: controller,
                ),
              ),
            );
          },
          onSignOut: controller.status == SessionStatus.signingOut
              ? null
              : controller.signOut,
        );

        return Scaffold(
          key: const ValueKey('authenticated-shell'),
          appBar: AppBar(
            leading: tablet ? const SizedBox.shrink() : null,
            automaticallyImplyLeading: !tablet,
            actions: [
              for (final entry in entries.where(
                (entry) => entry.id == 'global-search',
              ))
                IconButton(
                  key: const ValueKey('shell-search-action'),
                  tooltip: entry.label,
                  icon: const Icon(Icons.search),
                  onPressed: () => openDestination(entry),
                ),
            ],
            title: Row(
              children: [
                const WathiqBrand(showName: false, markSize: 30),
                const SizedBox(width: 10),
                Expanded(child: Text(dashboard)),
              ],
            ),
          ),
          drawer: tablet ? null : Drawer(child: navigation),
          body: SafeArea(
            child: Row(
              children: [
                if (tablet)
                  SizedBox(
                    width: 250,
                    child: DecoratedBox(
                      decoration: const BoxDecoration(
                        color: Colors.white,
                        border: BorderDirectional(
                          end: BorderSide(color: Color(0xFFE2E8F0)),
                        ),
                      ),
                      child: Material(color: Colors.white, child: navigation),
                    ),
                  ),
                Expanded(
                  child: _DashboardFoundation(
                    title: dashboard,
                    userName:
                        principal.user.localizedName ?? principal.user.name,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _ShellNavigation extends StatelessWidget {
  const _ShellNavigation({
    required this.appName,
    required this.entries,
    required this.onDestination,
    required this.profileLabel,
    required this.showDashboard,
    required this.showProfile,
    required this.showSignOut,
    required this.dashboardLabel,
    required this.preferencesLabel,
    required this.signOutLabel,
    required this.userName,
    required this.userEmail,
    required this.authorizeNavigation,
    required this.onDashboard,
    required this.onPreferences,
    required this.onSignOut,
  });

  final String appName;
  final List<_ShellDestination> entries;
  final ValueChanged<_ShellDestination> onDestination;
  final String profileLabel;
  final bool showDashboard;
  final bool showProfile;
  final bool showSignOut;
  final String dashboardLabel;
  final String preferencesLabel;
  final String signOutLabel;
  final String userName;
  final String userEmail;
  final Future<bool> Function() authorizeNavigation;
  final VoidCallback? onDashboard;
  final VoidCallback onPreferences;
  final VoidCallback? onSignOut;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 14),
            child: WathiqBrand(name: appName, markSize: 38),
          ),
          const Divider(height: 1),
          for (final entry in entries.where(
            (entry) => entry.id == 'global-search',
          ))
            _destinationTile(context, entry),
          if (showDashboard)
            Padding(
              padding: const EdgeInsets.all(12),
              child: ListTile(
                key: const ValueKey('shell-dashboard'),
                selected: true,
                selectedColor: const Color(0xFF087AC1),
                selectedTileColor: const Color(0xFFE0F2FE),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                leading: const Icon(Icons.home_outlined),
                title: Text(dashboardLabel),
                onTap: onDashboard,
              ),
            ),
          for (final entry in entries.where(
            (entry) => entry.id != 'global-search',
          ))
            _destinationTile(context, entry),
          const SizedBox(height: 24),
          const Divider(height: 1),
          if (showProfile)
            ListTile(
              key: const ValueKey('shell-profile'),
              onTap: () async {
                if (!await authorizeNavigation()) return;
                if (!context.mounted) return;
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => Scaffold(
                      appBar: AppBar(title: Text(profileLabel)),
                      body: SafeArea(
                        child: ListView(
                          padding: const EdgeInsets.all(24),
                          children: [
                            Text(
                              userName,
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 12),
                            Text(userEmail),
                            const SizedBox(height: 24),
                            ListTile(
                              title: Text(preferencesLabel),
                              leading: const Icon(Icons.language),
                              onTap: onPreferences,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
              leading: CircleAvatar(
                backgroundColor: const Color(0xFFE0F2FE),
                foregroundColor: const Color(0xFF087AC1),
                child: Text(_initials(userName)),
              ),
              title: Text(
                userName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                userEmail,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          if (showProfile)
            ListTile(
              key: const ValueKey('shell-preferences'),
              leading: const Icon(Icons.language),
              title: Text(preferencesLabel),
              onTap: onPreferences,
            ),
          if (showSignOut)
            ListTile(
              key: const ValueKey('shell-sign-out'),
              leading: const Icon(Icons.logout),
              title: Text(signOutLabel),
              onTap: onSignOut,
            ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );

  Widget _destinationTile(BuildContext context, _ShellDestination entry) =>
      ListTile(
        key: ValueKey('shell-${entry.id}'),
        leading: Icon(entry.icon),
        title: Text(entry.label),
        onTap: () {
          Scaffold.of(context).closeDrawer();
          onDestination(entry);
        },
      );

  static String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    return parts
        .where((part) => part.isNotEmpty)
        .take(2)
        .map((part) => part[0])
        .join()
        .toUpperCase();
  }
}

class _DashboardFoundation extends StatelessWidget {
  const _DashboardFoundation({required this.title, required this.userName});

  final String title;
  final String userName;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: const Color(0xFFF6FAFD),
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Align(
        alignment: AlignmentDirectional.topStart,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 960),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 20),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.account_circle_outlined,
                        size: 34,
                        color: Color(0xFF087AC1),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          userName,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _ShellDestination {
  const _ShellDestination(this.id, this.label, this.icon);
  final String id;
  final String label;
  final IconData icon;
}

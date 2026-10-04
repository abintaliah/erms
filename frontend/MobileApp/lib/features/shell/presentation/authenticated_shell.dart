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

    return LayoutBuilder(
      builder: (context, constraints) {
        final tablet = constraints.maxWidth >= tabletBreakpoint;
        final navigation = _ShellNavigation(
          appName: appName,
          dashboardLabel: dashboard,
          preferencesLabel: preferences,
          signOutLabel: signOut,
          userName: principal.user.localizedName ?? principal.user.name,
          userEmail: principal.user.email,
          onDashboard: tablet ? null : () => Navigator.pop(context),
          onPreferences: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => PreferencesScreen(
                catalogue: catalogue,
                controller: controller,
              ),
            ),
          ),
          onSignOut: controller.status == SessionStatus.signingOut
              ? null
              : controller.signOut,
        );

        return Scaffold(
          key: const ValueKey('authenticated-shell'),
          appBar: AppBar(
            leading: tablet ? const SizedBox.shrink() : null,
            automaticallyImplyLeading: !tablet,
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
                        border: Border(
                          right: BorderSide(color: Color(0xFFE2E8F0)),
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
    required this.dashboardLabel,
    required this.preferencesLabel,
    required this.signOutLabel,
    required this.userName,
    required this.userEmail,
    required this.onDashboard,
    required this.onPreferences,
    required this.onSignOut,
  });

  final String appName;
  final String dashboardLabel;
  final String preferencesLabel;
  final String signOutLabel;
  final String userName;
  final String userEmail;
  final VoidCallback? onDashboard;
  final VoidCallback onPreferences;
  final VoidCallback? onSignOut;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 14),
          child: WathiqBrand(name: appName, markSize: 38),
        ),
        const Divider(height: 1),
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
        const Spacer(),
        const Divider(height: 1),
        ListTile(
          leading: CircleAvatar(
            backgroundColor: const Color(0xFFE0F2FE),
            foregroundColor: const Color(0xFF087AC1),
            child: Text(_initials(userName)),
          ),
          title: Text(userName, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(
            userEmail,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        ListTile(
          key: const ValueKey('shell-preferences'),
          leading: const Icon(Icons.language),
          title: Text(preferencesLabel),
          onTap: onPreferences,
        ),
        ListTile(
          key: const ValueKey('shell-sign-out'),
          leading: const Icon(Icons.logout),
          title: Text(signOutLabel),
          onTap: onSignOut,
        ),
        const SizedBox(height: 8),
      ],
    ),
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

import 'package:flutter/material.dart';

import '../../../core/localization/message_catalogue.dart';
import '../../auth/application/session_controller.dart';

class PreferencesScreen extends StatefulWidget {
  const PreferencesScreen({
    required this.catalogue,
    required this.controller,
    super.key,
  });

  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  State<PreferencesScreen> createState() => _PreferencesScreenState();
}

class _PreferencesScreenState extends State<PreferencesScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.controller.loadPreferences();
    });
  }

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    String text(String key) => widget.catalogue.text(key, locale);
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final preferences = widget.controller.preferences;
        return Scaffold(
          appBar: AppBar(title: Text(text('preferences.heading.personal'))),
          body: SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 620),
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Text(
                      text('preferences.guidance.personal'),
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 24),
                    if (preferences == null &&
                        widget.controller.preferencesBusy)
                      const Center(child: CircularProgressIndicator())
                    else if (preferences == null)
                      Text(text('common.error.service_unavailable'))
                    else ...[
                      Text(
                        text('preferences.field.language'),
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 10),
                      Directionality(
                        textDirection: TextDirection.ltr,
                        child: SegmentedButton<String>(
                          key: const ValueKey('preference-language'),
                          showSelectedIcon: false,
                          segments: widget.controller.supportedLanguages
                              .map(
                                (language) => ButtonSegment(
                                  value: language.languageTag,
                                  label: Text(language.nativeName),
                                ),
                              )
                              .toList(growable: false),
                          selected: {preferences.languageTag},
                          onSelectionChanged: widget.controller.preferencesBusy
                              ? null
                              : (selection) => widget.controller.updateLanguage(
                                  selection.single,
                                ),
                        ),
                      ),
                      const SizedBox(height: 28),
                      Text(
                        text('preferences.field.working_timezone'),
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      Text(preferences.workingTimezone),
                      const SizedBox(height: 8),
                      Text(text('preferences.guidance.working_timezone')),
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

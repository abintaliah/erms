import 'package:flutter/material.dart';

import '../../../core/design/wathiq_brand.dart';
import '../../../core/localization/message_catalogue.dart';
import '../application/session_controller.dart';

class PasswordChangeScreen extends StatefulWidget {
  const PasswordChangeScreen({
    required this.catalogue,
    required this.controller,
    super.key,
  });

  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  State<PasswordChangeScreen> createState() => _PasswordChangeScreenState();
}

class _PasswordChangeScreenState extends State<PasswordChangeScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirmation = TextEditingController();

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    String text(String key) => widget.catalogue.text(key, locale);
    final busy = widget.controller.status == SessionStatus.changingPassword;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(
                    child: WathiqBrand(showName: false, markSize: 48),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    text(
                      'webui.show_change_password.label.set_a_new_password_f6a268ba',
                    ),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    text(
                      'webui.show_change_password.label.your_temporary_password_must_be_replaced_b_2cba2da1',
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 22),
                  _passwordField(
                    key: const ValueKey('current-password'),
                    controller: _current,
                    label: text(
                      'webui.show_change_password.input.current_password_00f4f73a',
                    ),
                    enabled: !busy,
                  ),
                  const SizedBox(height: 14),
                  _passwordField(
                    key: const ValueKey('new-password'),
                    controller: _next,
                    label: text(
                      'webui.show_change_password.input.new_password_28399c5b',
                    ),
                    enabled: !busy,
                  ),
                  const SizedBox(height: 14),
                  _passwordField(
                    key: const ValueKey('confirm-password'),
                    controller: _confirmation,
                    label: text(
                      'webui.show_change_password.input.confirm_new_password_abd1d774',
                    ),
                    enabled: !busy,
                  ),
                  if (widget.controller.failure != null) ...[
                    const SizedBox(height: 14),
                    Text(
                      text('common.error.validation_failed'),
                      key: const ValueKey('password-change-error'),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ],
                  const SizedBox(height: 22),
                  FilledButton(
                    key: const ValueKey('password-change-submit'),
                    onPressed:
                        busy ||
                            _next.text.isEmpty ||
                            _next.text != _confirmation.text
                        ? null
                        : _submit,
                    child: busy
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(
                            text(
                              'webui.show_change_password.button.set_new_password_067753d1',
                            ),
                          ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _passwordField({
    required Key key,
    required TextEditingController controller,
    required String label,
    required bool enabled,
  }) => TextField(
    key: key,
    controller: controller,
    enabled: enabled,
    obscureText: true,
    onChanged: (_) => setState(() {}),
    decoration: InputDecoration(
      labelText: label,
      prefixIcon: const Icon(Icons.lock_outline),
    ),
  );

  Future<void> _submit() => widget.controller.changePassword(
    currentPassword: _current.text,
    newPassword: _next.text,
  );
}

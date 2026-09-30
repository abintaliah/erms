import 'package:flutter/material.dart';

import '../../../core/design/wathiq_brand.dart';
import '../../../core/localization/message_catalogue.dart';
import '../../../core/network/api_failure.dart';
import '../application/session_controller.dart';

class AuthenticationScreen extends StatefulWidget {
  const AuthenticationScreen({
    required this.catalogue,
    required this.controller,
    super.key,
  });

  final MessageCatalogue catalogue;
  final SessionController controller;

  @override
  State<AuthenticationScreen> createState() => _AuthenticationScreenState();
}

class _AuthenticationScreenState extends State<AuthenticationScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscurePassword = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context);
    String text(String key) => widget.catalogue.text(key, locale);
    final busy = widget.controller.status == SessionStatus.signingIn;
    final failure = widget.controller.failure;
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(
            child: IgnorePointer(
              child: CustomPaint(painter: _SignInWavePainter()),
            ),
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420),
                  child: AutofillGroup(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Center(
                          child: WathiqBrand(
                            name: text('webui.index.label.wathiq_d1dfb800'),
                            markSize: 58,
                          ),
                        ),
                        const SizedBox(height: 34),
                        Text(
                          text('webui.index.label.sign_in_01f3842a'),
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                        const SizedBox(height: 22),
                        TextField(
                          key: const ValueKey('sign-in-email'),
                          controller: _email,
                          enabled: !busy,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.username],
                          decoration: InputDecoration(
                            labelText: text(
                              'webui.index.input.email_address_2569f0e9',
                            ),
                            prefixIcon: const Icon(Icons.person_outline),
                          ),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          key: const ValueKey('sign-in-password'),
                          controller: _password,
                          enabled: !busy,
                          obscureText: _obscurePassword,
                          autofillHints: const [AutofillHints.password],
                          onSubmitted: busy ? null : (_) => _submit(),
                          decoration: InputDecoration(
                            labelText: text(
                              'webui.index.input.password_f76ddde6',
                            ),
                            prefixIcon: const Icon(Icons.lock_outline),
                            suffixIcon: IconButton(
                              onPressed: () => setState(
                                () => _obscurePassword = !_obscurePassword,
                              ),
                              icon: Icon(
                                _obscurePassword
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined,
                              ),
                            ),
                          ),
                        ),
                        if (failure != null) ...[
                          const SizedBox(height: 14),
                          Text(
                            text(_failureKey(failure.kind)),
                            key: const ValueKey('sign-in-error'),
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ],
                        const SizedBox(height: 22),
                        FilledButton(
                          key: const ValueKey('sign-in-submit'),
                          onPressed: busy ? null : _submit,
                          child: busy
                              ? const SizedBox.square(
                                  dimension: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Text(
                                  text('webui.index.label.sign_in_01f3842a'),
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _submit() => widget.controller.signIn(
    email: _email.text.trim(),
    password: _password.text,
  );

  String _failureKey(ApiFailureKind kind) => switch (kind) {
    ApiFailureKind.offline ||
    ApiFailureKind.server => 'common.error.service_unavailable',
    ApiFailureKind.forbidden => 'common.error.forbidden',
    _ => 'common.error.bad_request',
  };
}

class _SignInWavePainter extends CustomPainter {
  const _SignInWavePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final light = Path()
      ..moveTo(0, size.height * .82)
      ..cubicTo(
        size.width * .28,
        size.height * .76,
        size.width * .48,
        size.height * .94,
        size.width,
        size.height * .78,
      )
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(light, Paint()..color = const Color(0xFFE2F4FE));

    final blue = Path()
      ..moveTo(0, size.height * .90)
      ..cubicTo(
        size.width * .32,
        size.height * .82,
        size.width * .58,
        size.height * .98,
        size.width,
        size.height * .86,
      )
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(blue, Paint()..color = const Color(0xFFB9E3FB));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

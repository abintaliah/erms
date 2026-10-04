import 'package:flutter/services.dart';

import 'session_controller.dart';

/// Only generic localized wording crosses the platform boundary, never identity
/// or session material. OS delivery remains best effort.
class PlatformSessionWarningScheduler implements SessionWarningScheduler {
  PlatformSessionWarningScheduler({
    required this.title,
    required this.body,
    MethodChannel? channel,
  }) : _channel = channel ?? const MethodChannel('erms.wathiq/session-warning');

  final String Function() title;
  final String Function() body;
  final MethodChannel _channel;

  Future<void> prepare() async {
    try {
      await _channel.invokeMethod<void>('prepare');
    } catch (_) {
      // Permission denial or unavailable platform never prevents authentication.
    }
  }

  @override
  Future<void> schedule(Duration delay) => _channel.invokeMethod<void>(
    'schedule',
    {'delaySeconds': delay.inSeconds, 'title': title(), 'body': body()},
  );

  @override
  Future<void> cancel() => _channel.invokeMethod<void>('cancel');
}

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/features/auth/application/platform_session_warning.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'warning sends only generic localized wording and cancels explicitly',
    () async {
      const channel = MethodChannel('erms.wathiq/session-warning');
      final calls = <MethodCall>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            calls.add(call);
            return null;
          });
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, null),
      );
      final scheduler = PlatformSessionWarningScheduler(
        title: () => 'جلسة وثق',
        body: () => 'سيُطلب تسجيل الدخول',
        channel: channel,
      );
      await scheduler.prepare();
      await scheduler.schedule(const Duration(minutes: 10));
      await scheduler.cancel();
      expect(calls.map((call) => call.method), [
        'prepare',
        'schedule',
        'cancel',
      ]);
      expect(calls[1].arguments, {
        'delaySeconds': 600,
        'title': 'جلسة وثق',
        'body': 'سيُطلب تسجيل الدخول',
      });
    },
  );
}

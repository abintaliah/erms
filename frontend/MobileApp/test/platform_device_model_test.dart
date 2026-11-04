import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/features/auth/application/platform_device_model.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('erms.wathiq/device-model');
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );

  test('native model and unavailable channel', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          expect(call.method, 'model');
          return 'Google Pixel 8';
        });
    expect(await PlatformDeviceModel.load(), 'Google Pixel 8');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          channel,
          (call) async => throw PlatformException(code: 'unavailable'),
        );
    expect(await PlatformDeviceModel.load(), isNull);
  });
}

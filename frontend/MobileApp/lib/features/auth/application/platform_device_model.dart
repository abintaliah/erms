import 'package:flutter/services.dart';

/// Collects a model shared by a device family, never a device identifier/name.
class PlatformDeviceModel {
  static const _channel = MethodChannel('erms.wathiq/device-model');

  static Future<String?> load() async {
    try {
      return await _channel
          .invokeMethod<String>('model')
          .timeout(const Duration(seconds: 2));
    } catch (_) {
      return null;
    }
  }
}

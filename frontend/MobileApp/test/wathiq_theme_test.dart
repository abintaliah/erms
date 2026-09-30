import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/core/design/wathiq_theme.dart';

void main() {
  test('mobile colors match the canonical Wathiq WebUI tokens', () {
    expect(WathiqColors.primary, const Color(0xFF268BD2));
    expect(WathiqColors.primaryDeep, const Color(0xFF176DA8));
    expect(WathiqColors.information, const Color(0xFFEAF5FC));
    expect(WathiqColors.onSurface, const Color(0xFF172033));
    expect(WathiqColors.muted, const Color(0xFF687386));
    expect(WathiqColors.surface, const Color(0xFFFFFFFF));
    expect(WathiqColors.outline, const Color(0xFFE1E6EB));
    expect(WathiqColors.positive, const Color(0xFF2F9E44));
    expect(WathiqColors.warning, const Color(0xFFE9A23B));
    expect(WathiqColors.error, const Color(0xFFDC5050));
  });

  test('initial theme is light and uses the canonical primary color', () {
    expect(WathiqTheme.light.brightness, Brightness.light);
    expect(WathiqTheme.light.colorScheme.primary, WathiqColors.primary);
    expect(WathiqTheme.light.scaffoldBackgroundColor, WathiqColors.surface);
  });
}

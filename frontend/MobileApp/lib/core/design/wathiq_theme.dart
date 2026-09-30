import 'package:flutter/material.dart';

abstract final class WathiqColors {
  static const primary = Color(0xFF268BD2);
  static const primaryDeep = Color(0xFF176DA8);
  static const onPrimary = Color(0xFFFFFFFF);
  static const surface = Color(0xFFFFFFFF);
  static const onSurface = Color(0xFF172033);
  static const muted = Color(0xFF687386);
  static const information = Color(0xFFEAF5FC);
  static const outline = Color(0xFFE1E6EB);
  static const positive = Color(0xFF2F9E44);
  static const warning = Color(0xFFE9A23B);
  static const error = Color(0xFFDC5050);
}

abstract final class WathiqSpacing {
  static const xSmall = 4.0;
  static const small = 8.0;
  static const medium = 16.0;
  static const large = 24.0;
  static const xLarge = 32.0;
}

abstract final class WathiqTheme {
  static final light = ThemeData(
    brightness: Brightness.light,
    colorScheme: const ColorScheme.light(
      primary: WathiqColors.primary,
      onPrimary: WathiqColors.onPrimary,
      surface: WathiqColors.surface,
      onSurface: WathiqColors.onSurface,
      outline: WathiqColors.outline,
      error: WathiqColors.error,
    ),
    scaffoldBackgroundColor: WathiqColors.surface,
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: WathiqColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: WathiqColors.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: WathiqColors.outline),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    useMaterial3: true,
  );
}

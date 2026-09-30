import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wathiq_mobile/app/app.dart';
import 'package:wathiq_mobile/core/localization/message_catalogue.dart';

void main() {
  testWidgets('foundation shell resolves canonical English text', (
    tester,
  ) async {
    const catalogue = MessageCatalogue(
      english: {'navigation.item.dashboard': 'Dashboard'},
      arabic: {'navigation.item.dashboard': 'لوحة المعلومات'},
    );

    await tester.pumpWidget(const WathiqApp(catalogue: catalogue));

    expect(find.text('Wathiq'), findsOneWidget);
    expect(find.text('Dashboard'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.text('Dashboard'))),
      TextDirection.ltr,
    );
  });

  testWidgets('foundation shell resolves Arabic with RTL direction', (
    tester,
  ) async {
    const catalogue = MessageCatalogue(
      english: {'navigation.item.dashboard': 'Dashboard'},
      arabic: {'navigation.item.dashboard': 'لوحة المعلومات'},
    );

    await tester.pumpWidget(
      const WathiqApp(catalogue: catalogue, locale: Locale('ar')),
    );

    expect(find.text('لوحة المعلومات'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.text('لوحة المعلومات'))),
      TextDirection.rtl,
    );
  });
}

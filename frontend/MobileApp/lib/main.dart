import 'package:flutter/widgets.dart';

import 'app/app.dart';
import 'core/config/app_environment.dart';
import 'core/localization/message_catalogue.dart';
import 'features/auth/application/session_controller.dart';
import 'features/auth/application/platform_session_warning.dart';
import 'features/auth/data/auth_api.dart';
import 'features/auth/application/platform_device_model.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final catalogue = await MessageCatalogue.load();
  final environment = AppEnvironment.fromCompileTime();
  late final SessionController sessionController;
  final warning = PlatformSessionWarningScheduler(
    title: () => catalogue.text(
      'mobile.session.warning_title',
      Locale(sessionController.effectiveLanguageTag),
    ),
    body: () => catalogue.text(
      'mobile.session.warning_body',
      Locale(sessionController.effectiveLanguageTag),
    ),
  );
  sessionController = SessionController(
    IoAuthApi(
      environment.apiBaseUrl,
      deviceModel: await PlatformDeviceModel.load(),
    ),
    warningScheduler: warning,
  );
  sessionController.addListener(() {
    if (sessionController.status == SessionStatus.authenticated) {
      warning.prepare();
    }
  });
  runApp(WathiqApp(catalogue: catalogue, sessionController: sessionController));
}

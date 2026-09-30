import 'package:flutter/widgets.dart';

import 'app/app.dart';
import 'core/config/app_environment.dart';
import 'core/localization/message_catalogue.dart';
import 'features/auth/application/session_controller.dart';
import 'features/auth/data/auth_api.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final catalogue = await MessageCatalogue.load();
  final environment = AppEnvironment.fromCompileTime();
  final sessionController = SessionController(
    IoAuthApi(environment.apiBaseUrl),
  );
  runApp(WathiqApp(catalogue: catalogue, sessionController: sessionController));
}

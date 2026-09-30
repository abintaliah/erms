import 'package:flutter/widgets.dart';

import 'app/app.dart';
import 'core/localization/message_catalogue.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final catalogue = await MessageCatalogue.load();
  runApp(WathiqApp(catalogue: catalogue));
}

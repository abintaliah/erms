package erms.wathiq

import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "erms.wathiq/device-model")
            .setMethodCallHandler { call, result ->
                if (call.method == "model") {
                    val model = Build.MODEL.orEmpty()
                    val maker = Build.MANUFACTURER.orEmpty()
                    result.success(if (model.startsWith(maker, ignoreCase = true)) model else "$maker $model")
                } else result.notImplemented()
            }
        cancelLegacySessionWarning()
    }

    // Clear alarms/notifications left by a previously installed build. Never schedule new ones.
    private fun cancelLegacySessionWarning() {
        val pending = PendingIntent.getBroadcast(this, 10,
            Intent().setClassName(this, "erms.wathiq.SessionWarningReceiver"),
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)
        if (pending != null) {
            (getSystemService(ALARM_SERVICE) as AlarmManager).cancel(pending)
            pending.cancel()
        }
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).cancel(10)
    }
}

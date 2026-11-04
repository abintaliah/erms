package erms.wathiq

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.SystemClock
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var permissionRequested = false

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
        cancelWarning()
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "erms.wathiq/session-warning")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "prepare" -> {
                        if (!permissionRequested && Build.VERSION.SDK_INT >= 33 &&
                            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                            permissionRequested = true
                            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 10)
                        }
                        result.success(null)
                    }
                    "cancel" -> { cancelWarning(); result.success(null) }
                    "schedule" -> {
                        val delay = call.argument<Number>("delaySeconds")?.toLong()
                        val title = call.argument<String>("title")
                        val body = call.argument<String>("body")
                        if (delay == null || delay <= 0 || title == null || body == null) {
                            result.error("invalid_warning", "Invalid warning parameters", null)
                        } else {
                            if ((applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
                                android.util.Log.d("WathiqSessionWarning", "schedule delaySeconds=$delay elapsedMs=${SystemClock.elapsedRealtime()}")
                            }
                            val intent = Intent(this, SessionWarningReceiver::class.java)
                                .putExtra("title", title).putExtra("body", body)
                                .putExtra("expiresAt", SystemClock.elapsedRealtime() + delay * 1000 + 5 * 60 * 1000)
                            val pending = PendingIntent.getBroadcast(this, 10, intent,
                                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                            (getSystemService(ALARM_SERVICE) as AlarmManager).setAndAllowWhileIdle(
                                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                                SystemClock.elapsedRealtime() + delay * 1000, pending)
                            result.success(null)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun cancelWarning() {
        if ((applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            android.util.Log.d("WathiqSessionWarning", "cancel elapsedMs=${SystemClock.elapsedRealtime()}")
        }
        val pending = PendingIntent.getBroadcast(this, 10,
            Intent(this, SessionWarningReceiver::class.java),
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)
        if (pending != null) {
            (getSystemService(ALARM_SERVICE) as AlarmManager).cancel(pending)
            pending.cancel()
        }
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).cancel(10)
    }
}

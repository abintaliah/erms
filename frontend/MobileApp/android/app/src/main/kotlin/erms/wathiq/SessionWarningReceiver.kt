package erms.wathiq

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.SystemClock

class SessionWarningReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val diagnostic = (context.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        fun trace(event: String) {
            if (diagnostic) android.util.Log.d("WathiqSessionWarning", "$event elapsedMs=${SystemClock.elapsedRealtime()}")
        }
        trace("received expiresAtMs=${intent.getLongExtra("expiresAt", 0)}")
        // Inexact OS scheduling may deliver too late; never show a stale warning.
        if (SystemClock.elapsedRealtime() >= intent.getLongExtra("expiresAt", 0)) { trace("suppressed_expired"); return }
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) { trace("suppressed_permission"); return }
        val title = intent.getStringExtra("title") ?: return
        val body = intent.getStringExtra("body") ?: return
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = "session-warning"
        val builder = if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(channel, title, NotificationManager.IMPORTANCE_DEFAULT))
            Notification.Builder(context, channel)
        } else Notification.Builder(context)
        trace("posting_notification")
        manager.notify(10, builder.setSmallIcon(R.drawable.ic_session_warning)
            .setContentTitle(title).setContentText(body).setAutoCancel(true).build())
    }
}

import Flutter
import UIKit
import Darwin
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "SessionWarning") else { return }
    let modelChannel = FlutterMethodChannel(name: "erms.wathiq/device-model", binaryMessenger: registrar.messenger())
    modelChannel.setMethodCallHandler { call, result in
      guard call.method == "model" else { result(FlutterMethodNotImplemented); return }
      var system = utsname()
      uname(&system)
      let hardware = withUnsafePointer(to: &system.machine) {
        $0.withMemoryRebound(to: CChar.self, capacity: 256) {
          String(cString: $0)
        }
      }
      #if targetEnvironment(simulator)
      let model = ProcessInfo.processInfo.environment["SIMULATOR_MODEL_IDENTIFIER"] ?? hardware
      result("\(model) Simulator")
      #else
      result(hardware)
      #endif
    }
    let center = UNUserNotificationCenter.current()
    let identifier = "wathiq-session-warning"
    center.removePendingNotificationRequests(withIdentifiers: [identifier])
    center.removeDeliveredNotifications(withIdentifiers: [identifier])
    let channel = FlutterMethodChannel(name: "erms.wathiq/session-warning", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "prepare":
        center.requestAuthorization(options: [.alert]) { _, _ in
          DispatchQueue.main.async { result(nil) }
        }
      case "cancel":
        center.removePendingNotificationRequests(withIdentifiers: [identifier])
        center.removeDeliveredNotifications(withIdentifiers: [identifier])
        result(nil)
      case "schedule":
        guard let args = call.arguments as? [String: Any],
              let seconds = args["delaySeconds"] as? NSNumber, seconds.doubleValue > 0,
              let title = args["title"] as? String, let body = args["body"] as? String else {
          result(FlutterError(code: "invalid_warning", message: "Invalid warning parameters", details: nil))
          return
        }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: seconds.doubleValue, repeats: false)
        center.add(UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)) { error in
          DispatchQueue.main.async {
            if error != nil { result(FlutterError(code: "warning_unavailable", message: "Warning unavailable", details: nil)) }
            else { result(nil) }
          }
        }
      default: result(FlutterMethodNotImplemented)
      }
    }
  }
}

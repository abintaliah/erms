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
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "DeviceModel") else { return }
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
    // Cancel reminders created by older builds; no permission request or scheduling remains.
  }
}

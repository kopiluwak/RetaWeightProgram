import Expo
import React
import ReactAppDependencyProvider

@UIApplicationMain
public class AppDelegate: ExpoAppDelegate {
  var window: UIWindow?

  var reactNativeDelegate: ExpoReactNativeFactoryDelegate?
  var reactNativeFactory: RCTReactNativeFactory?

  public override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    let delegate = ReactNativeDelegate()
    let factory = ExpoReactNativeFactory(delegate: delegate)
    delegate.dependencyProvider = RCTAppDependencyProvider()

    reactNativeDelegate = delegate
    reactNativeFactory = factory
    bindReactNativeFactory(factory)

    // iOS 27 (Xcode 27 SDK) terminates apps that haven't adopted the UIScene
    // lifecycle (crash in _UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption).
    // The window is therefore created in SceneDelegate below, not here.
    // Added 2026-11-05. NOTE: `npx expo prebuild --clean` regenerates this
    // file from the SDK 54 template and would drop this — re-apply if so.
    self.launchOptions = launchOptions

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  /// Launch options captured for SceneDelegate to hand to React Native.
  var launchOptions: [UIApplication.LaunchOptionsKey: Any]?

  // The scene delegate class is declared in Info.plist (UIApplicationSceneManifest).

  // Linking API
  public override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    return super.application(app, open: url, options: options) || RCTLinkingManager.application(app, open: url, options: options)
  }

  // Universal Links
  public override func application(
    _ application: UIApplication,
    continue userActivity: NSUserActivity,
    restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
  ) -> Bool {
    let result = RCTLinkingManager.application(application, continue: userActivity, restorationHandler: restorationHandler)
    return super.application(application, continue: userActivity, restorationHandler: restorationHandler) || result
  }
}

/// Owns the app window under the UIScene lifecycle (required from iOS 27).
class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    guard let windowScene = scene as? UIWindowScene,
          let appDelegate = UIApplication.shared.delegate as? AppDelegate,
          let factory = appDelegate.reactNativeFactory else { return }

    let window = UIWindow(windowScene: windowScene)
    self.window = window
    appDelegate.window = window
    factory.startReactNative(
      withModuleName: "main",
      in: window,
      launchOptions: appDelegate.launchOptions)
    window.makeKeyAndVisible()

    // Cold-start deep links / universal links arrive here under scenes.
    for ctx in connectionOptions.urlContexts {
      _ = RCTLinkingManager.application(UIApplication.shared, open: ctx.url, options: [:])
    }
    if let activity = connectionOptions.userActivities.first {
      _ = RCTLinkingManager.application(UIApplication.shared, continue: activity,
                                        restorationHandler: { _ in })
    }
  }

  // Warm deep links: under scenes these come to the scene, not the app delegate.
  func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
    for ctx in URLContexts {
      _ = RCTLinkingManager.application(UIApplication.shared, open: ctx.url, options: [:])
    }
  }

  func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    _ = RCTLinkingManager.application(UIApplication.shared, continue: userActivity,
                                      restorationHandler: { _ in })
  }
}

class ReactNativeDelegate: ExpoReactNativeFactoryDelegate {
  // Extension point for config-plugins

  override func sourceURL(for bridge: RCTBridge) -> URL? {
    // needed to return the correct URL for expo-dev-client.
    bridge.bundleURL ?? bundleURL()
  }

  override func bundleURL() -> URL? {
#if DEBUG
    return RCTBundleURLProvider.sharedSettings().jsBundleURL(forBundleRoot: ".expo/.virtual-metro-entry")
#else
    return Bundle.main.url(forResource: "main", withExtension: "jsbundle")
#endif
  }
}

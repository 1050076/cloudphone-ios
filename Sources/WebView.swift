import SwiftUI
import WebKit

// MARK: - WKWebView 壳
struct WebViewContainer: UIViewRepresentable {
    let startURL: URL
    let reloadToken: UUID

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        // 禁止页面缩放：注入 viewport user-scalable=no（Vue SPA 自带的 meta 没写）
        let noZoomMeta = """
        (function () {
            var c = 'width=device-width, initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no';
            var m = document.querySelector('meta[name=viewport]');
            if (m) { m.setAttribute('content', c); }
            else { var n = document.createElement('meta'); n.name = 'viewport'; n.content = c; document.head.appendChild(n); }
            document.addEventListener('gesturestart', function (e) { e.preventDefault(); });
            var lastTouch = 0;
            document.addEventListener('touchend', function (e) {
                var now = Date.now();
                if (now - lastTouch <= 300) { e.preventDefault(); }
                lastTouch = now;
            }, { passive: false });
        })();
        """
        config.userContentController.addUserScript(
            WKUserScript(source: noZoomMeta, injectionTime: .atDocumentEnd, forMainFrameOnly: true)
        )
        // 持久化 Cookie / localStorage，登录态不丢
        config.websiteDataStore = .default()
        // 云手机视频流一般走 WebRTC
        config.mediaPlaybackRequiresUserAction = false
        config.allowsInlineMediaPlayback = true
        if #available(iOS 15.4, *) {
            // 需要时可开相机/麦克风透传（iOS 15+ 才能对非 Safari WebView 开）
            // config.preferences.isElementFullscreenEnabled = true
        }

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.bounces = false               // 禁下拉橡皮筋
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.scrollView.minimumZoomScale = 1.0        // 钉死缩放
        webView.scrollView.maximumZoomScale = 1.0
        webView.scrollView.isScrollEnabled = false       // 页面自己管理滚动
        // 双指/双击缩放手势关掉
        webView.scrollView.pinchGestureRecognizer?.isEnabled = false
        for v in webView.subviews {
            for g in v.gestureRecognizers ?? [] {
                if let tap = g as? UITapGestureRecognizer, tap.numberOfTapsRequired >= 2 {
                    tap.isEnabled = false
                }
                if g is UIPinchGestureRecognizer { g.isEnabled = false }
            }
        }
        webView.allowsBackForwardNavigationGestures = true
        context.coordinator.webView = webView
        webView.load(URLRequest(url: startURL))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        // 目前无需增量更新；刷新按钮通过重建整树实现重新加载
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var parent: WebViewContainer
        weak var webView: WKWebView?

        init(_ parent: WebViewContainer) { self.parent = parent }

        // 新窗口/外链 → 交给系统 Safari
        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            if navigationAction.targetFrame == nil {
                UIApplication.shared.open(navigationAction.request.url!)
            }
            return nil
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let url = navigationAction.request.url
            if let url, let scheme = url.scheme?.lowercased(),
               ["tel", "mailto", "sms", "itms-apps", "wechat", "alipays"].contains(scheme) {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        // 页面内 JS 的 alert/confirm 也透出来
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedBy frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler() })
            topViewController()?.present(alert, animated: true)
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedBy frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(false) })
            alert.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler(true) })
            topViewController()?.present(alert, animated: true)
        }

        // 网页申请摄像头/麦克风 → 弹系统权限框并放行（iOS 15+）
        func webView(_ webView: WKWebView,
                     requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo,
                     type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(.prompt) // 触发系统 麦克风/摄像头 权限弹窗（首次）
        }

        private func topViewController() -> UIViewController? {
            var top = UIApplication.shared.connectedScenes
                .compactMap { ($0 as? UIWindowScene)?.keyWindow?.rootViewController }
                .first
            while let presented = top?.presentedViewController { top = presented }
            return top
        }
    }
}

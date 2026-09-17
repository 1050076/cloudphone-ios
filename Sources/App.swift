import SwiftUI
import WebKit
import Combine

// MARK: - 要加载的地址（改这里）
let kStartURL = URL(string: "https://www.oj8kclub.com/mobile.html#/login")!

@main
struct CloudPhoneApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @State private var reloadToken = UUID()
    @State private var showDebug = false

    var body: some View {
        WebViewContainer(startURL: kStartURL, reloadToken: reloadToken)
            .ignoresSafeArea()                       // 全屏：上下安全区都铺满
            .background(Color.black.ignoresSafeArea())
            .overlay(alignment: .topTrailing) {
                HStack(spacing: 12) {
                    // 🐞 调试面板：长按 0.5s 弹出（用 emoji，避免 SF Symbols 版本差异不显示）
                    Text("🐞")
                        .font(.system(size: 24))
                        .onLongPressGesture(minimumDuration: 0.5) { showDebug = true }
                    // 轻量刷新按钮
                    Button {
                        reloadToken = UUID()
                    } label: {
                        Image(systemName: "arrow.clockwise.circle.fill")
                            .font(.title2)
                            .foregroundStyle(.white.opacity(0.85))
                            .shadow(radius: 2)
                    }
                }
                .padding(.trailing, 10)
                .padding(.top, 56)   // 避开状态栏/刘海
            }
            .sheet(isPresented: $showDebug) {
                DebugConsoleView(isPresented: $showDebug)
            }
    }
}

// MARK: - 调试控制台（网页 console + JS 错误）
struct DebugConsoleView: View {
    @Binding var isPresented: Bool
    @State private var live: [String] = WebViewContainer.Coordinator.logs
    @State private var autoScroll = true

    var body: some View {
        NavigationView {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(live.enumerated()), id: \.offset) { idx, line in
                            Text(line)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(line.contains("error") ? .red : .primary)
                                .textSelection(.enabled)
                                .id(idx)
                        }
                    }
                    .padding(8)
                }
                .onChange(of: live.count) { _ in
                    if autoScroll, !live.isEmpty {
                        proxy.scrollTo(live.count - 1, anchor: .bottom)
                    }
                }
            }
            .navigationTitle("Console (\(live.count))")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("清空") {
                        WebViewContainer.Coordinator.logs.removeAll()
                        live = []
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("WS测试") {
                        let js = """
                        (function () {
                          try {
                            var url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
                            console.log('[WS测试] 开始连接 ' + url);
                            var ws = new WebSocket(url);
                            var done = false;
                            setTimeout(function () {
                              if (!done) { done = true; console.log('error| [WS测试] 超时：8秒内未连上也未报错 readyState=' + ws.readyState); try { ws.close(); } catch (e) {} }
                            }, 8000);
                            ws.onopen = function () { if (!done) { done = true; console.log('log| [WS测试] ✓ 连接成功，2秒后关闭'); setTimeout(function(){ ws.close(); }, 2000); } };
                            ws.onclose = function (e) { if (!done) { done = true; console.log('error| [WS测试] ✗ 连接失败 code=' + e.code + ' wasClean=' + e.wasClean + ' reason=' + (e.reason || '无')); } };
                            ws.onerror = function () { console.log('error| [WS测试] onerror 触发 readyState=' + ws.readyState); };
                          } catch (e) { console.log('error| [WS测试] 异常: ' + e.message); }
                        })();
                        """
                        WebViewContainer.Coordinator.currentWebView?.evaluateJavaScript(js)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("关闭") { isPresented = false }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Toggle("跟随", isOn: $autoScroll).toggleStyle(.switch).labelsHidden()
                }
            }
        }
        .onReceive(WebViewContainer.Coordinator.logPing) { _ in
            live = WebViewContainer.Coordinator.logs
        }
    }
}

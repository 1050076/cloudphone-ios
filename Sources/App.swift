import SwiftUI
import WebKit

// MARK: - 要加载的地址（改这里）
let kStartURL = URL(string: "https://www.oj8kclub.com/mobile.html#/login")!

@main
struct CloudPhoneApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .statusBarHidden(false)
        }
    }
}

struct ContentView: View {
    @State private var reloadToken = UUID()

    var body: some View {
        WebViewContainer(startURL: kStartURL, reloadToken: reloadToken)
            .ignoresSafeArea()                       // 全屏：上下安全区都铺满
            .background(Color.black.ignoresSafeArea())
            .overlay(alignment: .topTrailing) {
                // 轻量刷新按钮：滑到底部也不会丢
                Button {
                    reloadToken = UUID()
                } label: {
                    Image(systemName: "arrow.clockwise.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.white.opacity(0.85))
                        .shadow(radius: 2)
                }
                .padding(.trailing, 10)
                .padding(.top, 6)
            }
    }
}

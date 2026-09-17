# CloudPhone (iOS 壳应用)

安卓 APK（吊手机）本质是 WebView 壳，加载 `https://www.oj8kclub.com/mobile.html#/login`（Vue SPA 云手机控制端）。本项目是其 iOS 等价物：一个 WKWebView 壳。

## 结构
```
project.yml            # XcodeGen 工程定义
Sources/App.swift     # 入口 + 刷新按钮
Sources/WebView.swift # WKWebView 封装（Cookie 持久化、UA 伪装、外链转 Safari）
.github/workflows/build.yml  # GitHub Actions 云编译（无需 Mac）
```

## 编译（无需 Mac）
1. 在 GitHub 建一个仓库（公开仓库 macOS runner 免费），push 本目录。
2. Actions → build-ipa → 运行，结束后下载 artifact `CloudPhone-unsigned-ipa`。

## 安装（Windows）
用 Sideloadly（https://sideloadly.io）+ 你的 Apple ID 给 ipa 签名后安装到 iPhone：
- 免费 Apple ID：7 天有效期，过期重签重装。
- 付费开发者账号（$99/年）：可用 AltStore/Sidestore 自动续签。

## 改地址
`Sources/App.swift` 顶部 `kStartURL`。

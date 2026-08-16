<img src="src/assets/icons/light.png" height="64">

![GitHub Release](https://img.shields.io/github/v/release/ch-BookBanana/BookMdtLauncher?include_prereleases&label=Latest%20Version&labelColor=blue&color=green)  ![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/ch-BookBanana/BookMdtLauncher/total?label=Downloads)  ![GitHub License](https://img.shields.io/github/license/ch-BookBanana/BookMdtLauncher?label=License)

# BookMdtLauncher

基于 PyQt5 的 Mindustry 启动器：自动检测 Java、一键下载游戏、多端管理，**装好就能玩**。

## 简介

BookMdtLauncher（简称 BML）是一个开源、轻量的 Mindustry 启动器，目标是把你从"手动下 Java、手动找 jar、手动整理目录"的琐事里解放出来：

- **Java 全自动**：启动前自动检测 Java，缺失时自动下载、解压、部署，无需手动安装
- **游戏一键下载**：从 GitHub Release 直接下载游戏本体（`mdt.jar`），多线程分块 + 断点续传
- **多语言支持**：简体中文 / English / 日本語 / 한국어 / 繁體中文 / 文言文彩蛋模式）

## 版本号规则

测试版：`{年}-T{月}{日}(.{构建})`，例如 `26-T0816` 表示 2026 年 8 月 16 日的唯一一次测试版构建。
正式版：`{年}-B{月}{日}(.{构建})`，例如 `26-B0902.1` 表示 2026 年 9 月 2 日的第二次正式版构建。

## 安装方式

正式版在 [Releases](https://github.com/ch-BookBanana/BookMdtLauncher/releases) 中下载对应平台包：

* **Windows**：下载 `BookMindustryLauncher.exe`
* **源码运行**：需要 Python 3.10+ 与依赖库（见下方"从源码运行"）

> 首次启动会自动创建 `BML/` 数据目录（游戏目录、日志、配置），无需手动建目录。

### 从源码运行

```bash
git clone https://github.com/ch-BookBanana/BookMdtLauncher.git
cd BookMdtLauncher

# 安装依赖
pip install -r requirements.txt   # PyQt5、requests 等

# 运行
python main.py
```

**源码运行仅支持Windows平台，需求其他平台请自行fork**

## 功能特性

### ☕ Java 自动化
- 启动前检测 Java，缺失/版本不符时自动进入下载流程
- 多镜像源**竞速选优**：并行测速，自动选择最快的下载源
- 断点续传、暂停/恢复/取消；未完成的下载在下次启动时自动接管续传
- 解压部署全自动，完成后自动重新启动游戏

### 🎮 游戏管理
- 自动扫描 `.Mindustrys` 目录，识别已安装游戏并整理到游戏列表
- 游戏信息自动检索与缓存，切换界面不卡顿
- 支持多版本共存，默认游戏可配置

### ⬇️ 游戏下载
- 从 GitHub Release 直接下载游戏本体（`mdt.jar`），支持断点续传
- 下载列表实时进度：运行中 / 已暂停 / 待续传 三种状态一目了然
- **暂停状态持久化**：写入 `downloading.json`，重启后自动接管并保持暂停，点"继续"接着下
- **取消即清理**：临时文件与目标文件夹一并删除，不留残留

### 🎨 界面与体验
- 深/浅双主题，图标随主题自动换色
- 系统托盘常驻，关闭窗口最小化到托盘
- GitHub Token 可配置：透明显示 API 限流状态
- 全局日志：控制台 + 滚动文件日志，关键流程全程可追溯

## 技术栈

- **Python 3.10+ / PyQt5**：界面与事件循环
- **自研 QDownloader**：多线程分块下载器（并发分块、状态持久化、稳健续传）
- **requests**：网络请求（自动尊重系统代理，兼容加速器/VPN）

## 目录结构

```
BookMdtLauncher/
├── main.py              # 程序入口
├── src/
│   ├── utils/           # 核心模块（下载器、扫描器、启动器、GitHub API）
│   ├── lang/            # 多语言文件（zh-CN/en-US/ja-JP/ko-KR/zh-TW/lzh）
│   ├── assets/          # 图标与资源
│   └── resources/       # 样式表（dark.qss / light.qss）
└── BML/                 # 运行时数据（自动生成）
    ├── .Mindustrys/     # 游戏目录
    ├── logs/            # 日志
    └── settings.json    # 配置

```

## 常见问题

**Q：下载很慢 / 失败？**
A：游戏数据源依赖 GitHub，网络不佳时建议配置加速器或代理（程序自动尊重系统代理）。


**Q：游戏下载一半退出了怎么办？**
A：无需担心，进度已持久化。下次启动会自动续传，暂停状态也会保留。

## 贡献代码

欢迎提交 Issue 与 PR！

1. Fork 本仓库并克隆到本地
2. 新建分支：`git checkout -b feature/xxx`
3. 提交改动：`git commit -m "feat: xxx"`
4. 推送并提交 PR：`git push origin feature/xxx`

## Star History

<a href="https://www.star-history.com/#ch-BookBanana/BookMdtLauncher&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ch-BookBanana/BookMdtLauncher&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ch-BookBanana/BookMdtLauncher&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ch-BookBanana/BookMdtLauncher&type=Date" />
 </picture>
</a>

## License

[GPL-3.0](LICENSE)

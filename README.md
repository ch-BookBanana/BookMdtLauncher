<div align="center">

# Book MDT Launcher

![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Language](https://img.shields.io/badge/Language-Python%20%2B%20PySide6-green)
![Version](https://img.shields.io/badge/Version-V26--T0816-green)

**基于 PySide6 的 Windows 桌面端 Mindustry 启动器** —— 从 GitHub Release 一键下载、管理并启动多版本 Mindustry 服务端（`mdt.jar`），Java 运行时全自动配置。

</div>

---

## 简介

Book MDT Launcher（简称 **BML**）是一款面向 Windows 的 Mindustry 启动器：

- 游戏本体与 Java 运行时均**自动下载**，开箱即用；
- 每个游戏副本**相互隔离**（独立数据目录），多版本可并存、互不干扰；
- 同时支持 **原版（Anuken/Mindustry）** 与 **MindustryX（TinyLake/MindustryX）** 两个上游的 Release 下载；
- 内置多线程断点续传、GitHub API 集成、6 种界面语言与深浅双主题。

## 功能特性

- **多来源游戏下载**：实时拉取 GitHub Release 列表，区分原版 / MindustryX 的 alpha、beta 版本（beta 为时效性版本，附黄色提示条）
- **多版本并存**：每份游戏副本独立目录（`BML/.Mindustrys/<名称>/`），重名自动追加 `(1)(2)`，启动时可自由切换默认游戏
- **Java 全自动管理**：并发嗅探 PATH、注册表、常见目录中的 JDK；缺失时自动从清华镜像 / Adoptium 多源竞速下载 JDK 17 并解压，支持断点续传
- **多线程断点续传下载器**：多源测速选优、分块并发（最高 8 线程）、HTTP Range 续传、SSL 降级重试、系统代理自动检测，下载任务可暂停 / 继续 / 取消
- **下载状态持久化**：暂停状态写入 `downloading.json`，重启后自动接管并保持暂停状态
- **取消即清理**：取消游戏下载时连同临时文件、目标文件夹一并删除，不留残留
- **GitHub Token 集成**：设置页粘贴 Token 即校验并显示头像与 API 剩余额度（core / search 分开计数，到点自动重置）
- **Markdown 渲染**：Release 说明以 Markdown（含表格）渲染展示，图片缓存本地、后台逐张加载
- **系统托盘**：按 Windows 主题自动切换图标，左键单击恢复窗口，支持最小化到托盘
- **单实例运行**：二次启动自动唤起已有实例
- **无边框窗口**：支持 5px 边缘拖拽缩放、最大化检测、系统主题变化响应
- **多语言**：中 / 英 / 日 / 韩 / 繁体 / 文言文，运行时热切换无需重启，默认跟随系统语言
- **深浅主题**：内置 dark / light 两套 QSS，图标运行时按主题自动改色
- **完整日志**：日志按时间戳留存并自动清理，异常弹窗直接引导跳转 Issues 反馈

## 支持的游戏来源

| 来源 | 仓库 | 说明 |
| --- | --- | --- |
| 原版 | [Anuken/Mindustry](https://github.com/Anuken/Mindustry) | 按版本号分类（如 v146 / v147 / v159 等） |
| MindustryX | [TinyLake/MindustryX](https://github.com/TinyLake/MindustryX) | 名称含 `X` 为 alpha、含 `B` 为 beta |

已安装的游戏副本会被自动扫描并加入列表（每 2 秒刷新），删除副本目录后也会自动移除。

## 版本号规则

- **版本名**：`V26-T0816`，前两位为年份，`T0816` 为构建日期（8 月 16 日）；
- **版本标识**：`T` 为 test 测试版（Pre-release），`B` 为正式发布版；如 `V26-B0000` 即为正式版；
- **构建码**：`10000.00`，与 GitHub Release 的 tag（`v10000.00`）对应。

## 快速开始

### 下载安装

从 [Releases](https://github.com/ch-BookBanana/BookMdtLauncher/releases) 下载最新版可执行文件（`BookMindustryLauncher.exe`，Nuitka 单文件打包），双击运行即可。程序为绿色便携式，所有数据保存在 exe 同目录的 `BML/` 文件夹中。

> ⚠️ 游戏数据源依赖 GitHub，网络不佳时建议配置代理。

### 首次启动

1. 启动器自动创建 `BML/`、`BML/logs/`、`BML/.Mindustrys/` 目录；
2. 自动检测系统语言与 Java；若本机没有可用的 JDK 17，启动游戏时会提示并自动下载；
3. 进入「下载」页选择游戏版本 → 点击下载 → 下载完成后即可一键启动。

> 建议在「设置」页填入 GitHub Token，可显著提高 API 请求限额，避免下载列表加载受限。

## 构建

项目使用 Python 3.13 + PySide6，目前使用 **Pyinstaller** 打包。

> 由于在使用Nutika打包本项目时经常出现在开发者使用的设备上不可复现且难以排查的报错，故舍弃Nuitka转而使用Pyinstaller打包。即使Nuitka打包的产物体积更小且运行速度更快，但是排查问题所耗费的时间也绝非一个高中开发者所能承受的，如果能有大佬发现并指出我在代码、打包程序中任何可能影响Nutika使用的漏洞或不良编码习惯，麻烦提个Issue，谢谢！


## 项目结构

```
BookMDTLauncher/
├── main.py                   # 主程序（UI 与全部主逻辑）
├── nuitka.cmd                # Nuitka 打包脚本
├── pyinstaller.cmd           # PyInstaller 打包脚本
├── BML/                      # 运行时数据（exe 同目录）
│   ├── .Java/                # 自动下载的 JDK
│   ├── .Mindustrys/          # 游戏副本（每实例含 mdt.jar / icon.png / BML.json）
│   ├── .tmp/                 # 缓存与下载任务状态
│   ├── logs/                 # 日志
│   └── settings.json         # 用户设置
└── src/
    ├── assets/               # 图标与背景资源
    ├── lang/                 # 6 种语言翻译
    ├── resources/            # 主题样式（dark.qss / light.qss）
    └── utils/                # 核心工具模块
        ├── mdtScanner.py     # 游戏副本扫描与版本解析
        ├── mdtLauncher.py    # 游戏进程启动器（QProcess）
        ├── javaScanner.py    # Java 并发嗅探
        ├── javaDownload.py   # Java 自动下载 / 解压
        ├── mdtServer.py      # Mindustry 服务器 UDP 查询
        ├── api/              # 网络 API 封装
        │   ├── githubAPI.py      # GitHub REST API 封装
        │   └── wayzer_mapAPI.py  # WayZer 地图站 (www.mindustry.top) API
        ├── QDownloader.py    # 多线程断点续传下载器
        ├── QThTimer.py       # 跨线程定时器框架
        └── path_utils.py     # 多环境（开发 / PyInstaller / Nuitka）路径解析
```

## 语言支持

| 语言 | 代码 |
| --- | --- |
| 简体中文 | `zh-CN` |
| 繁体中文 | `zh-TW` |
| English | `en-US` |
| 日本語 | `ja-JP` |
| 한국어 | `ko-KR` |
| 文言文 | `lzh` |

## 参与贡献

欢迎提交 Issue 与 Pull Request！

- 功能建议 / Bug 反馈：请在 [Issues](https://github.com/ch-BookBanana/BookMdtLauncher/issues) 中提出；
- 翻译补充：直接修改 `src/lang/` 下对应语言的 JSON 文件；
- 代码风格：模块职责清晰、保持 `src/utils/` 各模块独立可复用。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ch-BookBanana/BookMdtLauncher&type=Date)](https://star-history.com/#ch-BookBanana/BookMdtLauncher&Date)

## 许可证

本项目基于 **GNU General Public License v3.0** 开源，详见 [LICENSE](LICENSE)。

> Mindustry 及其资源版权归 [Anuken](https://github.com/Anuken) 所有，MindustryX 版权归 [TinyLake(wayzer)](https://github.com/TinyLake) 所有；本项目为独立的第三方启动器，与上述项目无直接关联，版权归[BookBanana](https://github.com/ch-BookBanana)所有。

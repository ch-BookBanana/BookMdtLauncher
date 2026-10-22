<div align="center">

# Book MDT Launcher

![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Language](https://img.shields.io/badge/Language-Python%20%2B%20PySide6-green)
[![Version](https://img.shields.io/badge/dynamic/xml?url=https%3A%2F%2Fgithub.com%2Fch-BookBanana%2FBookMdtLauncher%2Freleases.atom&query=%2F%2F*%5Blocal-name()%3D%27entry%27%5D%5B1%5D%2F*%5Blocal-name()%3D%27title%27%5D&label=Version&color=green)](https://github.com/ch-BookBanana/BookMdtLauncher/releases)
[![QQ群](https://img.shields.io/badge/QQ群-337396920-blue.svg)](https://qm.qq.com/q/JoZzCNH0SQ)

**基于 PySide6 的 Windows 桌面端 Mindustry 启动器**

</div>

---

## 简介

Book MDT Launcher（简称 **BML**）是一款面向 Windows 的 Mindustry 启动器，致力于辅助玩家下载/管理**游戏/蓝图/地图**等，并进行**存档/数据**的管理。

>项目处于快速构建迭代期，未来可能会出现部分兼容性问题，请理性使用

## 功能特性

- **多来源游戏下载**：实时拉取 GitHub Release 列表，区分原版 / MindustryX 等不同源
- **多版本并存**：每份游戏副本独立目录，启动时可自由切换目标游戏
- **Java 全自动管理**：并发嗅探 PATH、注册表、常见目录中的 JDK；缺失时自动从清华镜像 / Adoptium 等多源竞速下载 JDK 17 并解压，支持断点续传
- **GitHub Token 集成**：设置页粘贴 Token 即校验并显示头像与 API 剩余额度（core / search 分开计数，到点自动重置）
- **Markdown 渲染**：Release 说明以 Markdown渲染展示，图片缓存本地、后台逐张加载

## 支持的游戏来源

| 来源 | 仓库 | 说明 |
| --- | --- | --- |
| 原版 | [Anuken/Mindustry](https://github.com/Anuken/Mindustry) | 按版本号分类（如 v5 / v6 等） |
| MindustryX | [TinyLake/MindustryX](https://github.com/TinyLake/MindustryX) | 名称含 `X` 为 alpha、含 `B` 为 beta |
| MindustryARC | [TinyLake/MindustryARC](https://github.com/TinyLake/MindustryARC) | 无分类 |

已安装的游戏副本会被自动扫描并加入列表，删除副本目录后也会自动移除。

## 版本号规则

- **版本名**：`V26-T0816`，前两位为年份，`T0816` 为构建日期（8 月 16 日）；
- **版本标识**：`T` 为 test 测试版（Pre-release），`B` 为正式发布版；如 `V26-B0000` 即为正式版；
- **构建码**：`10000.00`，与 GitHub Release 的 tag（`v10000.00`）对应。

## 快速开始

### 下载安装

从 [Releases](https://github.com/ch-BookBanana/BookMdtLauncher/releases) 下载最新版可执行文件（`BookMindustryLauncher.exe`，Nuitka 单文件打包），双击运行即可。程序为绿色便携式，所有数据保存在 exe 同目录的 `BML/` 文件夹中。

> ⚠️ 游戏数据源依赖 GitHub，网络不佳时建议配置代理。

### 首次启动

1. 启动器自动创建 `BML/`数据目录；
2. 自动检测系统语言与 Java；若本机没有可用的 JDK 17，启动游戏时会提示并自动下载；
3. 进入「下载」页选择游戏版本 → 点击下载 → 下载完成后即可一键启动。

> 建议在「设置」页填入 GitHub Token，可显著提高 API 请求限额，避免下载列表加载受限。

## 参与贡献

欢迎提交 Issue 与 Pull Request。构建方式、项目结构与贡献者名单见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## Star History

<a href="https://www.star-history.com/?repos=ch-BookBanana%2FBookMdtLauncher&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ch-BookBanana/BookMdtLauncher&type=date&theme=dark&legend=top-left&sealed_token=Ks5X78jKPBYIG8rvUTdHhdGXcZ-TOmeAJnAAQi0ZMkXjtOxvSmmrUaBs_QC04gesyX0YtsWGHxGAwUQFLrtpC0gBW24RAUUccHxNQcANodzoIa1EkVBDtg" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ch-BookBanana/BookMdtLauncher&type=date&legend=top-left&sealed_token=Ks5X78jKPBYIG8rvUTdHhdGXcZ-TOmeAJnAAQi0ZMkXjtOxvSmmrUaBs_QC04gesyX0YtsWGHxGAwUQFLrtpC0gBW24RAUUccHxNQcANodzoIa1EkVBDtg" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ch-BookBanana/BookMdtLauncher&type=date&legend=top-left&sealed_token=Ks5X78jKPBYIG8rvUTdHhdGXcZ-TOmeAJnAAQi0ZMkXjtOxvSmmrUaBs_QC04gesyX0YtsWGHxGAwUQFLrtpC0gBW24RAUUccHxNQcANodzoIa1EkVBDtg" />
 </picture>
</a>


## 许可证

本项目基于 **GNU General Public License v3.0** 开源，详见 [LICENSE](LICENSE)。

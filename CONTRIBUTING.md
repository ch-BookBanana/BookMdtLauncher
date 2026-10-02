# 参与开发

本文档面向希望构建、调试或为 Book MDT Launcher（BML）提交代码的开发者。普通用户请看 [README](README.md)。

## 项目结构

```
BookMDTLauncher/
├── main.py                     # 主程序：Main / Window / Tray / Logger / Langer / Signals / Winreg
├── nuitka.cmd                  # Nuitka 打包脚本（当前使用）
├── pyinstaller.cmd             # PyInstaller 打包脚本（备用）
└── src/
    ├── assets/                 # 图标资源
    │                           #   actions / backg / brands / buttons / editor / files
    │                           #   icons / mindustry / nav / tribtns
    ├── lang/                   # 语言翻译（zh-CN / zh-TW / en-US / ja-JP / ko-KR / lzh）
    ├── resources/styles/       # 主题样式（dark.qss / light.qss）
    └── utils/                  # 核心工具模块
        ├── mdtManager.py       # 游戏副本扫描与版本解析
        ├── mdtLauncher.py      # 游戏进程启动器（QProcess）
        ├── mdtLocker.py        # 游戏实例锁：运行期间禁止改名 / 删除实例
        ├── mdtServer.py        # Mindustry 服务器 UDP 查询
        ├── javaScanner.py      # 本地 Java 并发嗅探（轻量）
        ├── javaDownload.py     # Java 自动下载 / 解压
        ├── QDownloader.py      # 多线程断点续传下载器
        ├── QThTimer.py         # 跨线程定时器框架
        ├── path_utils.py       # 多环境（开发 / PyInstaller / Nuitka）路径解析
        ├── utils.py            # 通用工具：翻译取用、图标改色、Markdown 渲染
        ├── bus.py              # 全局总线：主题/语言变化广播，控件用 bus.bind(self) 自行接入
        ├── options/            # 可复用的界面单元（不自插布局，由页面的 add() 挂载）
        │   ├── _init.py        # 公共导入：Qt 控件、getPath、change_color、bus 的汇总出口
        │   ├── items.py        # Bool/Slider/DropBtnCombo/Combo
        │   ├── scrolls.py      # Scroll：自带浮条的滚动区（横/竖、可选拖动）
        │   └── texts.py        # Title/Line
        ├── api/                # 网络 API 封装
        │   ├── githubAPI.py         # GitHub REST API 封装
        │   ├── wayzer_mapAPI.py     # WayZer 地图站 (www.mindustry.top) API
        │   └── stng_blueprintAPI.py # STNG 蓝图工坊 (www.stng.pw) API
        ├── on_start/           # 启动期流程编排
        │   ├── startup.py      # 注册入口
        │   ├── java.py         # Java 检测 / 下载 / 解压流程
        │   └── game.py         # 游戏下载续传与完成回调
        └── pages/              # 页面层（三栏框架：Leftw / Mainw / Rightw / Page）
            ├── _init.py        # 页面基类与三栏容器
            ├── start.py        # 启动页
            ├── download.py     # 下载页
            ├── game.py         # 游戏页
            ├── setting.py      # 设置页：Setting（左栏 Left、右栏 Main）及其子页 Launcher
            ├── downloads/
            │   └── game.py     # 各下载源的游戏列表
            ├── fOverlay/
            │   └── _init.py    # 浮动叠加层
            └── fStack/
                ├── _init.py    # 浮动页面栈
                └── gameManage.py  # 游戏管理
```

## 构建

项目使用 Python 3.13 + PySide6，通过 **Nuitka** 打包为单文件 exe。

### 环境要求

| 项 | 要求 |
| --- | --- |
| Python | 3.13（推荐 python.org 安装版） |
| 依赖 | `python -m pip install nuitka` |
| C 编译器 | MSVC —— Visual Studio Build Tools，需勾选 C++ 工作负载 |

### 打包

```cmd
nuitka.cmd
```

> `nuitka.cmd` 中的 `set PYTHON=` 指向作者本机的解释器路径，请改为你自己的 Python，或直接改成 `python`（已在 PATH 中时）。

等价于：

```cmd
python -m nuitka ^
  --onefile ^
  --enable-plugin=pyside6 ^
  --include-qt-plugins=sensible ^
  --include-data-dir=src=src ^
  --windows-console-mode=attach ^
  --msvc=latest ^
  --output-filename="Book Mindustry Launcher.exe" ^
  main.py
```

产物为单文件 `Book Mindustry Launcher.exe`；发布到 Release 时以 `BookMindustryLauncher.exe` 为名上传。

### ⚠️ 必须强制 MSVC，禁止 zig

`--msvc=latest` 是**强制**参数。Nuitka 不能可靠地自动探测 VS Build Tools——本机已装 VS 2026 Build Tools（MSVC 14.5），Nuitka 仍静默回退到 zig。

zig 不传 `-target` / `-mcpu`，默认按**构建机 CPU** 生成指令。同一份源码：

| 编译器 | exe 中的 AVX / AVX2 / FMA / BMI 指令数 |
| --- | --- |
| zig | 5089 |
| MSVC | 0（基线 x86-64） |

因此 zig 产物要求运行机器支持 AVX2。在没有 AVX2 的 CPU 上（Windows on ARM 的 x64 模拟、2011 年前的 Intel 等），解释器启动阶段即触发非法指令 `0xC000001D`，窗口尚未创建就报「已停止工作」。同样的字节在不同机器上结果不同，所以现象看起来像"挑机器"，实际是编译目标不同。

**发布前验收（必做）**：

```cmd
python nuitka_bisect\scan_isa.py "<exe 路径>"
```

必须输出 `AVX/AVX2/FMA  : 0`，否则不要发布。

核对某次构建实际使用的编译器：查看 `<name>.build\scons-report.txt` 中的 `CC=`，应为 `cl.exe`，不能是 `ziglang\zig.exe`。

### 其他说明

- `--windows-console-mode=attach`：双击运行时无控制台窗口；从 cmd 启动则日志输出到该 cmd 窗口（cmd 不会等待进程结束）。调试时改用 `=force`，否则启动期的 traceback 会被静默丢弃。
- `--enable-plugin=pyside6` 自动收集 Qt 插件与 DLL；`--include-data-dir=src=src` 打包语言包、主题、图标等非代码资源（`.py` 按代码编译，不复制）。
- `BML/` 不参与打包，它是 exe 同目录下的运行时用户数据（settings.json、logs、下载缓存），由 `getPath()` 的「非 src 路径 → exe 目录」分支解析。
- 首次编译较慢，后续构建复用缓存。构建产物 `main.build/`、`main.dist/`、`main.onefile-build/` 已加入 `.gitignore`。

> `pyinstaller.cmd` 保留作备用。历史版本 `V10000.01` 曾因 Nuitka 打包故障临时切回 PyInstaller（产物约 51 MB，Nuitka 约 26 MB），自 `v10000.02` 起已恢复 Nuitka。

## 参与贡献

欢迎提交 Issue 与 Pull Request！

- 功能建议 / Bug 反馈：请在 [Issues](https://github.com/ch-BookBanana/BookMdtLauncher/issues) 中提出；
- 翻译补充：直接修改 `src/lang/` 下对应语言的 JSON 文件；
- 代码风格：模块职责清晰、保持 `src/utils/` 各模块独立可复用。

## 贡献者

| 资源 | 贡献者 | 来源 |
| --- | --- | --- |
| 原版游戏 | [Anuken](https://github.com/Anuken) | [GitHub](https://github.com/Anuken/Mindustry) |
| MindustryX | [wayzer](https://github.com/Way-zer) | [GitHub](https://github.com/TinyLake/MindustryX) |
| MindustryARC | [squi2rel](https://github.com/squi2rel) | [GitHub](https://github.com/squi2rel/MindustryARC) |
| Mindustry地图站(未集成) | [wayzer](https://github.com/Way-zer) | [Mindustry地图站](https://www.mindustry.top/) |
| STNG 蓝图工坊(未集成) | --- | [STNG 蓝图工坊](https://www.stng.pw/) |

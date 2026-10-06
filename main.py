# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 BookBanana
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
"""
版本信息见上方英文，以下为中文摘要：
本程序为自由软件，您可以根据GNU通用公共许可证的条款重新分发和修改它，许可证版本为3或（由您选择）更高版本。
本程序的发布目的是希望它能有用，但不提供任何保证，包括但不限于适销性或特定用途的适用性的隐含保证。有关更多细节，请参阅GNU通用公共许可证。
您应该已经收到GNU通用公共许可证的副本，如果没有，请访问http://www.gnu.org/licenses/。
"""

init = {
    "version": "26-T1002",
    "BuildCode": "10000.03"
}

from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QSize, QByteArray, Signal
from PySide6.QtGui import (
    QColor, QPixmap, QPainter, QIcon, QFont, QFontMetrics, QPainterPath, QCursor, QAction
)
from PySide6.QtWidgets import (
    QWidget, QScrollBar, QApplication, QHBoxLayout, QVBoxLayout, QStackedWidget, QLineEdit, QPushButton, QLabel,
    QButtonGroup,QSystemTrayIcon, QMenu, QDialog, QTextEdit, QProgressBar
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import sys, os, json, copy, winreg, logging, locale, time, shutil, traceback, webbrowser
from datetime import datetime
import ctypes
import ctypes.wintypes


def _safe_fmt_exc(exc=None, limit=None):
    """把异常格式化成字符串 —— 连格式化都炸时退回最朴素的写法。

    why：traceback 要回读源码（linecache），而取源码本身还得 import。万一崩的
    正是 import 机制（插件那个替换 builtins.__import__ 的闸门撞上别人家的钩子
    出过这种事），format_exc() 会二次崩溃：下面那个「启动失败」弹窗还没弹，
    进程就先没了，用户只看到一串裸栈。报错的路子自己不能先倒。
    """
    try:
        return traceback.format_exc(limit=limit)
    except BaseException:
        pass
    if exc is None:
        exc = sys.exc_info()[1]
    if exc is None:
        return "（异常信息也取不到了）"
    try:
        return "".join(traceback.format_exception_only(type(exc), exc))
    except BaseException:
        return "%s: %s" % (type(exc).__name__, exc)


try:
    from src.utils.langer import Langer
    from src.utils.logger import Logger
    from src.utils.path_utils import getPath
    from src.utils.pages._init import open_overlay
    from src.utils.settings import Settings, ask_close
    from src.utils.mdtManager import mdtManager
    from src.utils.mdtLauncher import mdtLauncher, set_tr_func as mdt_set_tr_func
    from src.utils.QThTimer import QThTimer
    from src.utils.api import githubAPI
    from src.utils.api.githubAPI import GithubAPI
    from src.utils.javaManager import javaManager
    from src.utils import javaDownload
    from src.utils.QDownloader import QDownloader, shutdown_all as _qd_shutdown_all
    from src.utils.utils import _is_mdt_download, change_color, t
    from src.utils.options.scrolls import Scroll
    from src.utils.bus import bus
    from src.utils.events import events
    from src.utils.resources import (ACT_DL_LIST, ACT_TIPS, BRAND_GITHUB, ICON_APP_DARK,
                                     ICON_APP_LIGHT, TBT_CLOSE, TBT_MAXIMIZE, TBT_MAXIMIZE2,
                                     TBT_MINIMIZE, app_icon)
    from src.utils.on_start import startup
    from src.utils.on_start.java import attach as _attach_java_ui
    from src.utils.registry import Box, registry
    from src.utils import pluginLoader
    from src.utils.pages.fOverlay._init import FloatingOverlay
    from src.utils.pages.fStack._init import FloatingStack
    # import 内置页面包即完成登记：各页面模块在自己末尾往 core.pages 登记条目
    # （契约声明与那些 import 都收在 pages/builtin.py 里）。main.py 因此不必
    # 认识任何一个页面类 —— 加页面只改那个包，不动这里。
    from src.utils.pages import builtin as _builtin_pages    # noqa: F401



    class Main():
        def __init__(self,app):
            self.app = app
        
            # 全局拦截滚动条右键菜单
            class _ScrollBarFilter(QObject):
                def eventFilter(self, obj, event):
                    if event.type() == QEvent.ContextMenu and isinstance(obj, QScrollBar):
                        return True
                    return super().eventFilter(obj, event)
            self._scroll_bar_filter = _ScrollBarFilter()
            self.app.installEventFilter(self._scroll_bar_filter)

            # 只建 BML 这个根。它下面的目录各有归属方，各自建自己的：
            #   BML/logs        → Logger.__init__（它要用的时候自己 makedirs）
            #   BML/badSettings → Settings 的损坏备份（真出损坏才需要，见 utils/settings.py）
            #   BML/.Mindustrys → mdtManager.ensure_dirs()
            #   BML/plugins     → pluginLoader.ensure_dirs()
            # 原先这里把它们连路径一起抄了一遍 —— 而「插件装在哪」是
            # pluginLoader.PLUGIN_DIR 的事。抄错的代价是静默的：目录没建出来，
            # discover 只是返回空表，插件全不加载、没有报错也没有日志。
            os.makedirs(getPath("BML"), exist_ok=True)
            mdtManager.ensure_dirs()
            pluginLoader.ensure_dirs()
            # 事件总线：模块级单例，宿主与插件共用（见 src/utils/events.py）。
            # 原先它是 Main 里的一个嵌套类、挂在 self.signals 上，插件想发事件
            # 就得先拿到 Main —— 那等于把这一堆隐式属性一起递出去。
            self.signals = events
            # 宿主工具挂到全局单例上：组件与插件从 events.logger / .settings /
            # .lang / .shell 取，不必攥着 Main。property 转发，宿主换掉
            # self.settings 时这里跟着走。
            events.bind(self)
            self.winreg = self.Winreg(self, self)
            self.logger = Logger()
            self.logger.info("\n------------Book MDT Launcher------------"
                            f"\n-time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
                            f"\n-version: {init['version']}"
                            f"\n-BuildVersion: {init['BuildCode']}"
                            f"\n-logLevel: {logging.getLevelName(self.logger.level)}"
                            "\n-----------------------------------------")
            # ── L0 基层：设置 ──
            # schema（键与默认值）在 src/utils/settings.py 的 DEFAULT_SCHEMA 里，
            # 原来它是这里的一段字面量。那个类不依赖宿主：日志与翻译都是注入的，
            # 所以它能单独测（scripts/test_settings.py）。
            self.settings = Settings(logger=self.logger)
            # 日志要读 maxLogNum，但它建得比设置早 —— 这边建完回填给它
            self.logger.set_settings(self.settings)
            # 设置改动的存盘要落在**主线程**：设置会被工作线程写（rate 同步、
            # 下载收尾…），而 QTimer 不能在别的线程里 start。信号跨线程是排队
            # 投递的，所以写入方 emit，主线程收到再起防抖计时器。
            self._settings_dirty = self._SettingsSaveTrigger()
            self._settings_dirty.fired.connect(self._schedule_settings_save)
            app.aboutToQuit.connect(self.saveSettings)
            self.loadSettings()

            # L1：翻译。插件覆盖项走注入（plugin_langs），于是这里不必 import
            # 插件层，也就不存在「次基层 ← 插件层」那条反依赖。
            # revision 同理注入：插件集合变了没有，只有插件层自己知道，而
            # 「语言名没变但插件覆盖项变了」正是必须重读的那种情况。
            self.langer = Langer(settings=self.settings, logger=self.logger,
                                 winreg=self.winreg, overrides=pluginLoader.plugin_langs,
                                 revision=pluginLoader.langs_revision)
            # 翻译也是注入的（基层不 import 上层）
            self.settings.set_tr(self.langer.get)
            # 从这里起，改设置自动排一次防抖存盘 —— 各处不必再记着调 saveSettings
            self.settings.watch(self._on_settings_changed)
            javaManager.settings = self.settings
            javaDownload.set_tr_func(self.langer.get)
            mdt_set_tr_func(self.langer.get)
            self.logger._cleanup_old_logs()

            self.saveSettings()


            self.launcher = mdtLauncher(self, self.settings)
            self.githubAPI = GithubAPI()
            self.mdtManager = mdtManager(self.settings, parent=None, root=self)
            self.mdtManager.on_game_changed.connect(self._on_game_changed)
            if self.settings["github"]["token_enc"]:
                token = githubAPI.read_token(self.settings)
                if token:
                    self.githubAPI.setToken(token)
                QThTimer.task(
                    0,
                    lambda e: self.githubAPI.checkToken(),
                    result_callback=self._on_startup_rate_check,
                    dedicated=True   # 网络任务走独立线程，避免阻塞 QThTimer 共享线程（卡死所有 taskP）
                )


            self.signals.register("tokenVerified", Signal(bool, str, object))
            # 浮层 / 栈走信号：页面不直接点 root.window.floatingOverlay|floatingStack，
            # 而是发一个请求，挂到哪一层由 Window 自己决定（页面因此不必知道窗口结构）
            self.signals.register("overlayRequested", Signal(object))
            self.signals.register("overlayClosed", Signal(object, bool))
            self.signals.register("stackRequested", Signal(object))
            self.signals.register("stackClosed", Signal(object, bool))
            # Java 任务状态：下载列表的轮询 → 启动页的进度文字（只改字不切页）
            self.signals.register("java_status", Signal(str, object))
            # 插件重载是**命令**（有动作、不需要回值）：走事件，谁都能请求。
            # 不往托盘塞入口 —— 托盘是窗口自己的零件，它该管的是窗口。
            self.signals.register("reload_plugins", Signal())
            self.signals.on("reload_plugins", lambda *_: self.reload_plugins())
            # 插件集合变了（卸载 / 加载失败回滚）：宿主据此把它盖过的东西收回来。
            # 必须赶在 load_all() 之前注册 —— 加载期就有插件可能失败并发这条。
            self.signals.register("plugins_changed", Signal())
            self.signals.on("plugins_changed", self._on_plugins_changed)
            # 关闭询问浮层的答复是**命令**：藏到托盘 / 退出。浮层只发请求，
            # 真正动手的是窗口自己 —— 浮层不该知道窗口能被藏起来。
            self.signals.register("closeRequested", Signal(str))
            self.signals.on("closeRequested", self._on_close_requested)

            # 加载插件。位置有讲究：必须早于建窗口 —— 插件在 setup() 里往扩展点
            # 登记，而界面要到构建时才去读那些条目；同时又必须晚于 events.bind()
            # 与 Langer，插件才用得上 logger / lang。
            # load_all 逐个隔离：坏插件只记进它自己的 error，绝不往外抛
            # （外面整个包在一个大 try 里，抛出去就是「启动失败」弹窗）。
            self.plugins = pluginLoader.load_all()
            # 插件语言包要等插件加载完才进得来（Langer 建得比插件早）。这一步
            # 通常已经是多余的：load_all 末尾会发 plugins_changed，_on_plugins_changed
            # 那条路已经按当前语言重读过一次了。留着当保险（那条路万一没走成，
            # 语言表也不至于停在「没有插件覆盖」的版本）；重复调用 Langer 自己会
            # 挡掉 —— 语言与插件语言包两样都没变就不会再读一遍、再广播一遍。
            self.langer.load(self.langer.current_lang)

            self.tray = self.Tray(self, self)
            self.window = self.Window(self, self)

            # 后台预加载所有游戏数据到缓存，加速后续切换
            QThTimer.task(100, lambda event: self.mdtManager.preload_all())
            # 图标周期检查与 QPixmaps 引用计数缓存已由 mdtManager 自管理（icon_timer）

            # 退出统一清理：先停下载/后台线程（避免退出挂起与崩溃弹窗）
            app.aboutToQuit.connect(self._cleanup_on_quit)

            # Java 下载流程的 UI 回调/辅助函数由 src/utils/on_start/java.py 挂载（保持 self._java_* 调用点不变）
            _attach_java_ui(self)

            startup.register(self)

        def _on_game_changed(self, data):
            """mdtManager 事件回调（主线程）。

            newGame/deleteGame/nameChanged/groupChanged → gameList 变化，落盘；
            iconChanged → 图标文件变化，失效 QPixmaps 缓存（下次引用重新加载）。
            事件明细属于排查用信息，走 DEBUG：仅在 `--log=debug` 启动时输出，
            避免日常日志被游戏目录变化刷屏。
            """
            self.logger.debug(f"on_game_changed: {data}")
            etype = data.get("type")
            if etype in ("newGame", "deleteGame", "nameChanged", "groupChanged"):
                self.saveSettings()
            elif etype == "iconChanged":
                mdtManager.invalidate_icon_pixmap(data.get("game"))

        def _cleanup_on_quit(self):
            """应用退出前的统一清理（aboutToQuit 时执行）。

            顺序：隐藏托盘 → 结束游戏进程 → 停止下载线程 → 停止 QThTimer 后台线程
            → 清理图片缓存。QThTimer.shutdown() 在模块内也连接了 aboutToQuit，重复调用是幂等的。
            """
            try:
                self.tray.hide()
            except Exception:
                pass
            # 结束启动器拉起的游戏进程：退出启动器就不再留下后台跑着的服务端
            # blocking=True：退出流程已回不到事件循环，必须同步等进程真的死掉
            try:
                self.launcher.kill_game(blocking=True)
            except Exception:
                pass
            # 取消 Java 下载/解压流程（并清掉 javaDownload.json：取消即放弃，不再续传）
            try:
                self._java_cancel_all()
            except Exception:
                pass
            try:
                _qd_shutdown_all()
            except Exception:
                pass
            try:
                QThTimer.shutdown()
            except Exception:
                pass
            # 删除 markdown 图片缓存（mdimg），下次渲染时重新下载
            try:
                import shutil
                mdimg = getPath("BML/.tmp/mdimg")
                if os.path.isdir(mdimg):
                    shutil.rmtree(mdimg, ignore_errors=True)
            except Exception:
                pass

        # token 的加密与落盘在 api/githubAPI.py 里（store_token / read_token），
        # 不在这里 —— 用到它的是 GitHub 设置页和启动流程，跟宿主没关系。

        def _on_startup_rate_check(self, result):
            ok, error_type, data = result
            if ok:
                rate = self.githubAPI.rate
                s = self.settings["github"]
                s["rate"]["core"] = {"remaining": rate["core"]["remaining"], "reset": rate["core"]["reset"]}
                s["rate"]["search"] = {"remaining": rate["search"]["remaining"], "reset": rate["search"]["reset"]}
                s["useful"] = True
            elif error_type == "auth":
                self.githubAPI.setToken(None)
                s = self.settings["github"]
                s["token_enc"] = None
                s["token_key"] = None
                s["useful"] = None
                s["user"] = {"name": None, "headurl": None}
            self.saveSettings()
            self.signals.emit("tokenVerified", ok, error_type, data)

        def setTheme(self,theme):
            self.settings["theme"] = 1 if theme else 0
            self.apply_theme()

        # ==================== settings 读写 ====================
        # settings.json 的读写统一走这里：
        #   写 → 临时文件 + os.replace 原子替换（不会留下写了一半的文件）
        #   读 → 失败时原件备份到 BML/badSettings/，再回退默认值
        # ── 设置：实现在 src/utils/settings.py（L0 基层），这里只留入口 ──
        # 宿主对设置只剩两件事：什么时候读、什么时候写。校验/合并/原子替换/
        # 损坏备份/清理临时文件都在那个类里。

        @property
        def defsettings(self):
            """默认值表（= schema）。出处是 src/utils/settings.py 的 DEFAULT_SCHEMA。"""
            return self.settings.schema

        class _SettingsSaveTrigger(QObject):
            """把「设置有改动」从任意线程送到 GUI 线程。

            写入方可能在工作线程（rate 同步、下载收尾），而 QTimer 不能在那儿
            start（QObject::startTimer: Timers cannot be started from another
            thread）。信号跨线程是排队投递的，所以只借它转一道手。
            """

            fired = Signal()

        def _on_settings_changed(self, path, old, new):
            """设置一改就告诉主线程一声（可能在任意线程被调用）。

            原先「谁改谁记得调 saveSettings」散在十几处，漏一个就是悄悄丢配置；
            现在挂在这条通知上。
            """
            self._settings_dirty.fired.emit()

        def _schedule_settings_save(self):
            """（主线程）排一次防抖存盘：500ms 合并高频写，比如拖滑块。"""
            timer = getattr(self, "_settings_save_timer", None)
            if timer is None:
                # Main 不是 QObject，给不了父对象，所以自己攥着这个引用
                timer = self._settings_save_timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(self.saveSettings)
            timer.start(500)

        def loadSettings(self):
            """读 settings.json：合并进 schema；读不了就备份原文件再回默认值。"""
            self.settings.load()

        def saveSettings(self):
            """写 settings.json（原子替换，写不进去只记日志）。"""
            self.settings.save()

        def reload_plugins(self, retry=True):
            """重载插件层：全部卸载 → 重走一遍 → 界面按注册表对账。

            什么时候用：手动装了 / 删了 / 改了插件之后，不必重启启动器；
            或者某个插件上次加载失败被标注停用了，用户改好后想再试一次
            （retry=True 会连停用名单里的一起重试；失败就再标回去）。

            界面（页面 / 托盘 / 样式 / 语言）不在这里逐个收拾 —— 它们各自挂在
            plugins_changed 上对账。这里只补一次语言与样式，保证「插件集合的
            最终状态」被完整应用一次（卸载过程中是逐条触发的）。
            """
            try:
                for info in list(pluginLoader.loaded()):
                    pluginLoader.unload(info)
                infos = pluginLoader.load_all(retry_disabled=retry)
                ok = [i for i in infos if i.ok]
                bad = [i for i in infos if not i.ok]
                self.logger.info(
                    "插件已重载：%d 个加载成功%s"
                    % (len(ok), "，%d 个失败（已标注停用）" % len(bad) if bad else ""),
                    name="Plugin")
                # 界面不必在这里逐个收拾：load_all 末尾会发 plugins_changed，
                # 语言 / 样式 / 托盘 / 页面各自挂在它上面按注册表对账。
                return infos
            except Exception:
                self.logger.error("重载插件失败：\n" + traceback.format_exc(limit=6),
                                  name="Plugin")
                return []

        def _on_close_requested(self, mode):
            """关闭询问浮层的答复：藏到托盘 / 退出启动器。

            设置存不存由浮层自己决定（它那儿有「保存到设置」那个勾），
            这里只管动手 —— 一处执行，两条路（直接点 × 与浮层选择）行为一致。
            """
            if mode == "tray":
                self.window.hide()
            else:
                self.window.close()

        def ask_close(self):
            """弹一层「隐藏到托盘 / 退出启动器」。

            控件由设置层给（它在那儿，因为要问的就是它的 closeByTray），
            挂到哪一层归窗口管：这里只发请求，窗口自己知道浮层装在哪。
            """
            self.signals.emit("overlayRequested", ask_close(self.window))

        def _on_plugins_changed(self):
            """插件集合变了：把它盖过的三样收回来。

            插件能盖的三样，各自的重算入口宿主本来就有：
              * 语言包 —— plugin_langs 是 load 时合并进去的，重载一次就没了它；
              * 样式片段 —— apply_theme 每次重新收 core.qss；
              * 托盘菜单项 —— 托盘照 core.tray.menu 重建。

            页面（core.pages）不在这里：页容器自己订了这条事件，收到就按注册表
            对账（sync_pages）—— 它才知道怎么拆自己的按钮与三栏控件。

            启动期（窗口还没建）也会收到这条：那时 theme/lang 的最终状态还由启动
            流程自己定，所以这里做守卫。
            """
            try:
                self.langer.load(self.langer.current_lang)
            except Exception as e:
                try:
                    self.logger.warning(f"插件变更后重载语言失败：{e}")
                except Exception:
                    pass
            if getattr(self, "window", None) is not None:
                try:
                    self.apply_theme()
                except Exception:
                    pass
            tray = getattr(self, "tray", None)
            if tray is not None:
                try:
                    tray.reload_plugin_items()
                except Exception:
                    pass

        def apply_theme(self):
            is_light = bool(self.settings["theme"])
            theme_file = "light.qss" if is_light else "dark.qss"

            # 开始：停止窗口绘制，避免切换过程中的闪烁与中间态
            self.window.setUpdatesEnabled(False)
            try:
                qss = ""
                with open(getPath(f"src/resources/styles/{theme_file}"), "r", encoding="utf-8") as f:
                    qss = f.read()

                # 扩展加的样式片段（core.qss）：接在主题文件**后面**，同名选择器
                # 以靠后的为准 —— 插件能盖内置样式，而不必去改主题文件。
                # theme 为 None 表示两套主题都加，否则按当前是不是浅色筛。
                extra = [e.qss for e in registry.entries("core.qss")
                         if e.get("theme") is None
                         or bool(e.get("theme")) == is_light]
                if extra:
                    qss = qss.rstrip() + "\n\n" + "\n\n".join(x.strip() for x in extra) + "\n"

                app = QApplication.instance()
                if app:
                    app.setStyleSheet(qss)
                    self.logger.debug(f"Loading QtStyleSheet from {theme_file}:\n{qss} ")

                font = QFont()
                font.setFamily("Microsoft Yahei")
                font.setPointSize(8)
                app.setFont(font)

                # 广播主题变化：各控件的 lighting 已自行接在总线上
                bus.set_theme(is_light)
                self.logger.info(t(self.langer.get("core.log.info.themeChange"), "light" if is_light else "dark"))
            finally:
                # 完成：重新启用绘制（异常也保证恢复，避免窗口卡在不绘制状态）
                self.window.setUpdatesEnabled(True)

        class Window(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root



                self.server = QLocalServer(self)
                QLocalServer.removeServer("BookMdtLauncherMI")
                if self.server.listen("BookMdtLauncherMI"):
                    self.server.newConnection.connect(self.showS)



                self.root.logger.debug("init QW.window")
                self.root.window = self
                self.setMinimumSize(QSize(600, 450))

                self.installEventFilter(self)

                self._last_window_state = Qt.WindowNoState
                # 无边框窗口拖动状态：由 drag_begin/drag_move/drag_end 维护（Logo 与叠加浮层遮罩共用）
                self._drag_pressed = False
                self._drag_moving = False
                self._drag_winpos = None
                self._drag_mousepos = None

                self.init_ui()
                self.init_wid()

                self.root.apply_theme()

                self.root.logger.info(self.root.langer.get("core.log.info.windowLoad"))

            def init_ui(self):
                self.setWindowTitle("Book MDT Launcher")
                self.setWindowFlags(Qt.FramelessWindowHint)
                self.setGeometry(50, 50, 700, 500)

            def changeEvent(self, event):
                if event.type() == QEvent.WindowStateChange:
                    if not self.isMinimized():
                        self._last_window_state = self.windowState()
                        # 同步最大化/还原按钮图标。
                        # 不依赖 nativeEvent（PySide6 下 eventType 是 QByteArray，
                        # Windows 消息分支不可靠），Qt 自身的窗口状态变化一定触发这里。
                        try:
                            tbt = self.main.top.tbt_max
                            maximized = self.isMaximized()
                            self.root.logger.debug(f"window state changed, maximized={maximized}")
                            tbt.setLogo(1 if maximized else 0)
                        except Exception:
                            pass
                super().changeEvent(event)

            def restore_from_tray(self):
                self.show()
                if self.isMinimized():
                    # 最小化
                    if self._last_window_state == Qt.WindowMaximized:
                        self.showMaximized()
                    else:
                        self.showNormal()
                else:
                    # 提层
                    self.raise_()
                self.activateWindow()

            def openGithubSetting(self):
                """打开 GitHub 设置页：现建一个并入叠。

                遮罩与居中由叠加浮层统一提供。原先窗口自己攥着一个常驻实例，
                关掉再开看到的还是旧状态；现在每次现建，读到的就是当前配置。
                """
                open_overlay("core.githubSetting", self)

            def showS(self):
                conn = self.server.nextPendingConnection()
                if conn:
                    conn.readyRead.connect(self._on_read_data)
                    conn.disconnected.connect(conn.deleteLater)

            def _on_read_data(self):
                conn = self.sender()
                data = conn.readAll()
                if data == QByteArray(b"MAINWINSHOW"):
                    self.restore_from_tray()
                conn.disconnectFromServer()
                conn.deleteLater()

            def init_wid(self):
                self.floatingStack = FloatingStack(self)
                self.root.logger.debug("init QW.window.left")
                self.left = self.Left(self, self.root)
                self.root.logger.debug("init QW.window.lline")
                self.lline = self.LLine(self, self.root)

                self.root.logger.debug("init QW.windowL")
                self.layout = QHBoxLayout(self)
                self.layout.setAlignment(Qt.AlignLeft)
                self.layout.setSpacing(0)
                self.layout.setContentsMargins(0, 0, 0, 0)

                self.root.logger.debug("init QW.windowL.stren")
                self.stren = QWidget()
                self.stren.setFixedWidth(41)
                self.layout.addWidget(self.stren, 0)

                self.root.logger.debug("init QW.windowL.main")
                # 左栏导航按钮组在这里注入：页容器要往导航栏加按钮，但不该顺着
                # parent/root 往上摸 —— 显式传下去，「谁给谁」就写在这一行里。
                self.main = self.Main(self, self.root, nav=self.left.pagebtns)
                self.layout.addWidget(self.main, 1)

                self.left.raise_()
                self.lline.raise_()

                self.floatingStack.raise_()

                # 叠加浮层：GitHub 设置页、游戏管理、下载列表都由 core.overlays
                # 登记、用的时候现建（见 pages/githubSetting.py、dlList.py）——
                # 窗口不认识这些类，也不替它们保管实例。
                self.floatingOverlay = FloatingOverlay(self)

                # 浮层/栈请求在这里落地：请求方只管发信号，
                # 挂载点（叠加层还是栈层）由窗口自己决定
                _sig = self.root.signals
                _sig.connect("overlayRequested", self.floatingOverlay.add_page)
                _sig.connect("overlayClosed", self.floatingOverlay.pop_page)
                _sig.connect("stackRequested", self.floatingStack.add_page)
                _sig.connect("stackClosed", self.floatingStack.pop_page)

                # 遮罩层盖住整个窗口，鼠标事件到不了标题栏，它按事件请求拖动窗口
                _sig.register("dragRequested", Signal(str, object))
                _sig.connect("dragRequested", self._on_drag_requested)

            def _on_drag_requested(self, phase, event):
                """遮罩层请求拖动无边框窗口：转给窗口自己那套 drag_begin/move/end。"""
                handler = getattr(self, "drag_" + str(phase), None)
                if handler is not None:
                    handler(event)

            def eventFilter(self, obj, event):
                if obj is self and event.type() == QEvent.Resize:
                    new_width = self.left.width()  # 假设宽度固定，或者从配置读取
                    self.left.setGeometry(0, 0, new_width, self.height())
                    self.lline.init_ui()

                    self.root.logger.debug(f"Window resized via filter: {self.width()}x{self.height()}")

                return super().eventFilter(obj, event)

            def nativeEvent(self, eventType, message):
                """
                拦截 Windows 原生消息
                """
                # 判断是否是 Windows 消息
                # PySide6: eventType 是 QByteArray（b"windows_generic_MSG"）；PyQt5 是 str。
                # 直接比较 str 在 PySide6 下恒为 False，导致整个分支（含最大化检测）失效。
                if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
                    # PySide6: message 已是 int（内存地址）；PyQt5 是 sip.voidptr，int() 两者通用
                    msg = ctypes.wintypes.MSG.from_address(int(message))

                    #
                    if msg.message == 0x0084:
                        if not self.isMaximized() and not self.floatingOverlay.isVisible():
                            # 获取鼠标在屏幕上的坐标
                            pos = self.mapFromGlobal(QCursor.pos())
                            x, y = pos.x(), pos.y()
                            w, h = self.width(), self.height()

                            border_width = 5
                            result = 1

                            if x < border_width:
                                if y < border_width:
                                    result = 13
                                elif y > h - border_width:
                                    result = 16
                                else:
                                    result = 10
                            elif x > w - border_width:
                                if y < border_width:
                                    result = 14
                                elif y > h - border_width:
                                    result = 17
                                else:
                                    result = 11
                            elif y < border_width:
                                result = 12
                            elif y > h - border_width:
                                result = 15

                            return True, result

                    # 托盘主题切换
                    elif msg.message in (0x001A, 0x0320):
                        QTimer.singleShot(100, self.root.tray.setIcon_)

                    # 最大化检测
                    elif msg.message == 0x0005:
                        if msg.wParam == 2:
                            self.root.logger.debug("window maximized")
                            self.main.top.tbt_max.setLogo(1)
                        elif msg.wParam == 0:
                            self.root.logger.debug("window unmaximized")
                            self.main.top.tbt_max.setLogo(0)

                # 3. 其他消息交给默认处理
                return super().nativeEvent(eventType, message)

            def resizeEvent(self, event):
                super().resizeEvent(event)
                self.floatingStack.setGeometry(0,40,self.width(),self.height()-40)
                self.floatingOverlay.setGeometry(0,0,self.width(),self.height())

            def drag_begin(self, event):
                # 拖动开始：记录窗口与鼠标起点
                self._drag_pressed = True
                self._drag_moving = False
                self._drag_winpos = self.pos()
                self._drag_mousepos = event.globalPosition().toPoint()

            def drag_move(self, event):
                # 拖动中：按鼠标位移移动窗口（越界限制在多屏可用桌面内）
                if not self._drag_pressed or self._drag_mousepos is None:
                    return
                if self.isMaximized():
                    self.showNormal()
                self._drag_moving = True
                # 多屏：取所有屏幕可用区域的并集，避免用主屏尺寸把窗口夹在单屏内
                area = None
                for screen in QApplication.screens():
                    g = screen.availableGeometry()
                    area = g if area is None else area.united(g)
                if area is None:
                    area = QApplication.primaryScreen().availableGeometry()
                # 至少保留 40px 在桌面范围内，防止窗口被拖出视野
                min_x, max_x = area.left(), area.right() + 1 - 40
                min_y, max_y = area.top(), area.bottom() + 1 - 40
                movpos = self._drag_winpos + event.globalPosition().toPoint() - self._drag_mousepos
                movpos.setX(max(min_x, min(movpos.x(), max_x)))
                movpos.setY(max(min_y, min(movpos.y(), max_y)))
                self.move(movpos)

            def drag_end(self, event=None):
                # 拖动结束：返回本次是否真的移动过，调用方据此区分“单击”
                moved = self._drag_pressed and self._drag_moving
                if moved:
                    self.root.logger.debug(t("Window moved via filter: ($1,$2)", self.pos().x(), self.pos().y()))
                self._drag_pressed = False
                self._drag_moving = False
                self._drag_winpos = None
                self._drag_mousepos = None
                return moved
                

            class Left(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.isfold = True
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setGeometry(0, 0, 40, self.parent.height())
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.root.logger.debug("init QW.window.leftL")
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.root.logger.debug("init QW.window.leftL.tline")
                    self.tline = self.TLine(self, self.root)
                    self.root.logger.debug("init QW.window.leftL.logo")
                    self.logo = self.Logo(self, self.root)
                    self.layout.addWidget(self.logo, 0)
                    self.layout.addWidget(self.tline, 0)

                    self.root.logger.debug("init QW.window.leftL.pages")
                    self.pagebtns = self.PageBtns(self, self.root)
                    self.layout.addWidget(self.pagebtns, 1)

                def fold(self, text=None):
                    if text is None:
                        text = not self.isfold
                    width = 40 if text else 180
                    self.setGeometry(0, 0, width, self.height())
                    self.root.window.lline.init_ui()
                    self.root.logger.debug(f"Window left fold: {self.isfold}")
                    self.isfold = text

                class Logo(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root

                        self.init_ui()
                        self.init_wid()
                        bus.bind(self)

                    def init_ui(self):
                        self.setFixedSize(180, 40)
                        self.setAttribute(Qt.WA_StyledBackground, True)
                        # 整块可拖动：悬停/按下都是食指手，只有拖动中换成四向移动
                        self._cursor_shape = Qt.PointingHandCursor
                        self.setCursor(self._cursor_shape)

                    def init_wid(self):
                        self.root.logger.debug("init QW.window.leftL.logoL")
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(5)
                        self.layout.setAlignment(Qt.AlignLeft)

                        self.logo = QLabel(self)

                        self.logo.setFixedSize(40, 40)
                        self.logo.setScaledContents(True)
                        self.layout.addWidget(self.logo, 0)

                        self.label = QLabel(self)
                        self.label.setText('Book MDT Launcher')
                        self.label.setFixedWidth(140)
                        self.label.setProperty('wid', 'title')
                        self.layout.addWidget(self.label, 1)

                    def lighting(self, light: bool):
                        logo = getPath(app_icon(light))
                        pix = QPixmap(logo)
                        if pix.isNull():
                            self.root.logger.error(f"Logo image not found: {logo}")
                        self.logo.setPixmap(pix)

                    def _set_cursor(self, shape):
                        """切换光标形状；拖动时 mouseMove 高频触发，同形状不重复设。"""
                        if self._cursor_shape != shape:
                            self._cursor_shape = shape
                            self.setCursor(shape)

                    def _over_icon(self, event):
                        """鼠标是否落在 40x40 的 logo 图上：图标本身可点，光标保持悬停时的食指手。"""
                        return self.logo.geometry().contains(event.position().toPoint())

                    def mousePressEvent(self, event):
                        # 只认左键：右键（含中键）在这里不触发任何操作——既不拖动窗口，也不折叠侧栏
                        if event.button() == Qt.LeftButton:
                            self.root.window.drag_begin(event)
                        elif not self._over_icon(event):
                            # 右键按在标题文字上：按住没任何反应，光标换回普通箭头
                            self._set_cursor(Qt.ArrowCursor)
                        super().mousePressEvent(event)

                    def mouseMoveEvent(self, event):
                        if self.root.window._drag_pressed:
                            self.root.window.drag_move(event)
                            # 按住后 drag_move 立刻置位 _drag_moving（无位移阈值），光标随即换成四向移动
                            if self.root.window._drag_moving:
                                self._set_cursor(Qt.SizeAllCursor)
                        elif event.buttons() & Qt.RightButton:
                            # 右键按住移动：跨过图标边界时实时切换
                            self._set_cursor(Qt.PointingHandCursor if self._over_icon(event) else Qt.ArrowCursor)
                        super().mouseMoveEvent(event)

                    def mouseReleaseEvent(self, event):
                        if event.button() == Qt.LeftButton:
                            # 用 drag_end 的返回值区分单击/拖动：它返回「本次是否真的移动过」。
                            # 不能改读 _drag_moving——drag_end 里已经把它清成 False 了。
                            if self.root.window._drag_pressed and not self.root.window.drag_end(event):
                                self.parent.fold()
                        # 松开时鼠标仍在控件上：不论左右键都回到悬停的食指手
                        self._set_cursor(Qt.PointingHandCursor)
                        super().mouseReleaseEvent(event)

                class TLine(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.root = root
                        self.parent = parent

                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(1)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        self.line = QWidget(self)
                        self.line.setAttribute(Qt.WA_StyledBackground, True)
                        self.line.setProperty("wid", "line")

                    def resizeEvent(self, event):
                        """
                        当 TLine 的大小发生变化时（由布局管理器决定），
                        重新计算内部 line 的位置和宽度
                        """
                        super().resizeEvent(event)

                        # 获取当前 TLine 的实际宽度
                        current_width = self.width()

                        # 确保宽度足够减去两边的 5px
                        if current_width > 10:
                            new_width = current_width - 10
                            new_x = 5
                        else:
                            new_width = current_width
                            new_x = 0

                        # 更新内部 line 的几何形状
                        self.line.setGeometry(new_x, 0, new_width, 1)

                class PageBtns(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self._btn = None
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setFixedWidth(180)

                    def init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop)

                        self.btsGroup = QButtonGroup(self)
                        self.btns_ = []

                        self.chooser = QWidget(self)
                        self.chooser.setAttribute(Qt.WA_StyledBackground, True)
                        self.chooser.setStyleSheet("background: #6e4197;")
                        self.chooser.setFixedSize(3, 40)
                        self.chooser.move(-10, 0)

                        self.btsGroup.buttonClicked.connect(self.someone_clicked)

                    def someone_clicked(self, btn):
                        if self._btn is not btn:
                            self.chooser.setGeometry(btn.x(), btn.y(), 3, 40)
                            self.root.logger.debug(t("Page changed to: $1", self.root.langer.get(btn.text_)))
                            self._btn = btn

                    def add_btn(self, text=None, logo=None):
                        btn = self.Btns(logo, text, self, self.root)
                        self.btns_.append(btn)
                        self.layout.addWidget(btn)
                        self.btsGroup.addButton(btn)
                        return btn

                    def remove_btn(self, btn):
                        """摘掉一颗按钮（插件页面被卸掉时）。

                        三处都要摘：按钮组（否则它还占着互斥）、布局、以及
                        「当前选中」那个记录 —— 不然后面点别人时 chooser 会跳错位置。
                        """
                        if btn in self.btns_:
                            self.btns_.remove(btn)
                        self.btsGroup.removeButton(btn)
                        self.layout.removeWidget(btn)
                        btn.setParent(None)
                        btn.deleteLater()
                        if self._btn is btn:
                            self._btn = None

                    class Btns(QPushButton):
                        def __init__(self, logo=None, text=None, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.logo_ = logo
                            self.text_ = text
                            self.init_ui()
                            self.init_wid()
                            bus.bind(self)

                        def init_ui(self):
                            self.setFixedSize(180, 40)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid", "lbtn")
                            self.setCheckable(True)

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setContentsMargins(3, 0, 0, 0)
                            self.layout.setSpacing(5)

                            self.logo = QLabel(self)
                            self.logo.setFixedSize(40, 40)
                            self.logo.setAttribute(Qt.WA_StyledBackground, False)
                            self.logo.setProperty("wid", "lbtn")
                            self.logo.setScaledContents(False)
                            self.layout.addWidget(self.logo)

                            self.text = QLabel(self)
                            self.text.setAttribute(Qt.WA_StyledBackground, False)
                            self.text.setFixedSize(140, 40)
                            self.text.setProperty("wid", "lbtn")
                            self.langing()
                            self.layout.addWidget(self.text)

                        def lighting(self, light: bool):
                            if self.logo_ is not None:
                                color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                                logo = change_color(self.logo_, color)
                                pixmap = logo.pixmap(56,56)

                                if not pixmap.isNull():
                                    smooth_pixmap = pixmap.scaled(
                                        30, 30,
                                        Qt.KeepAspectRatio,
                                        Qt.FastTransformation
                                    )
                                    self.logo.setPixmap(smooth_pixmap)
                                else:
                                    self.root.logger.warning(f"Failed to load pixmap for {self.logo_}")

                        def langing(self):
                            if self.text_ is not None:
                                self.text.setText(self.root.langer.get(self.text_))
                                self.setToolTip(self.root.langer.get(self.text_))

                        def setText(self, _text):
                            self.text_ = _text
                            self.langing()

                        def setLogo(self, _logo):
                            self.logo_ = _logo
                            self.lighting()

            class LLine(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.init_ui()

                def init_ui(self):
                    self.setProperty("wid", "line")
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.setGeometry(self.parent.left.width(), 0, 1, self.parent.height())


            class Main(QWidget):
                def __init__(self, parent=None, root=None, nav=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.nav = nav          # 左栏导航按钮组，由 Window 注入
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    pass

                def init_wid(self):
                    self.root.logger.debug("init QW.windowL.mainL")
                    self.layout = QVBoxLayout(self)
                    self.layout.setAlignment(Qt.AlignTop)
                    self.layout.setSpacing(0)
                    self.layout.setContentsMargins(0, 0, 0, 0)

                    self.root.logger.debug("init QW.windowL.mainL.top")
                    self.top = self.Top(self, self.root)
                    self.layout.addWidget(self.top, 0)

                    self.root.logger.debug("init QW.windowL.mainL.tline")
                    self.tline = self.TLine(self, self.root)
                    self.layout.addWidget(self.tline)

                    self.root.logger.debug("init QW.windowL.mainL.main")
                    self.main = self.Main(self, self.root, nav=self.nav)
                    self.layout.addWidget(self.main, 1)

                class Top(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(40)

                    def init_wid(self):
                        self.root.logger.debug("init QW.windowL.mainL.topL")
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(7, 0, 5, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignRight)

                        self.github = self.GitHub(self, self.root)
                        self.layout.addWidget(self.github)

                        self.layout.addSpacing(8)

                        self.dlList = self.DlList(self, self.root)
                        self.layout.addWidget(self.dlList)

                        self.layout.addStretch(1)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_mini")
                        self.tbt_mini = self.TriBtn([getPath(TBT_MINIMIZE)], self, self.root)
                        self.tbt_mini.clicked.connect(lambda: self.root.window.showMinimized())
                        self.layout.addWidget(self.tbt_mini)
                        self.layout.addSpacing(5)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_max")
                        self.tbt_max = self.TriBtn(
                            [
                                getPath(TBT_MAXIMIZE),
                                getPath(TBT_MAXIMIZE2)
                            ],
                            self, self.root)
                        self.tbt_max.clicked.connect(self.maxmize)
                        self.layout.addWidget(self.tbt_max)
                        self.layout.addSpacing(5)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_close")
                        self.tbt_close = self.TriBtn([getPath(TBT_CLOSE)], self, self.root)
                        self.tbt_close.clicked.connect(lambda: self.close_())
                        self.tbt_close.setStyleSheet("QPushButton:hover{background: red;}")
                        self.layout.addWidget(self.tbt_close)


                    def maxmize(self):
                        if self.root.window.isMaximized():
                            self.root.window.showNormal()
                        else:
                            self.root.window.showMaximized()

                    def close_(self):
                        """右上角那个 ×：藏到托盘、退出，或者先问一句。

                        closeByTray 三态（见 settings.DEFAULT_SCHEMA）：
                        True 直接藏、False 直接退、None（默认）弹一层问 ——
                        问了才定下来的那种，是用户在浮层里勾了「保存到设置」。
                        """
                        mode = self.root.settings["closeByTray"]
                        if mode is None:
                            self.root.ask_close()
                        elif mode:
                            self.root.window.hide()
                        else:
                            self.root.window.close()

                    def mousePressEvent(self, event):
                        self.root.window.drag_begin(event)
                        super().mousePressEvent(event)

                    def mouseMoveEvent(self, event):
                        self.root.window.drag_move(event)
                        super().mouseMoveEvent(event)

                    def mouseReleaseEvent(self, event):
                        self.root.window.drag_end(event)
                        super().mouseReleaseEvent(event)

                    class GitHub(QPushButton):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self._hover_pending = False
                            self.init_ui()
                            bus.bind(self)
                            self.clicked.connect(self.root.window.openGithubSetting)
                            # refreshed 仅更新 tooltip，不触发后台请求
                            self.root.githubAPI.refreshed.connect(self._update_tooltip)

                        def init_ui(self):
                            self.setFixedSize(28, 28)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setStyleSheet("QPushButton {border-radius: 15px;}")

                        def lighting(self, light):
                            self.setIcon(QIcon(change_color(getPath(BRAND_GITHUB),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                            self.setIconSize(QSize(28, 28))

                        def _update_tooltip(self):
                            """仅更新 tooltip 文本，不触发网络请求。"""
                            token = self.root.settings["github"]["token_enc"]
                            live_rate = self.root.githubAPI.rate
                            rate = self.root.settings["github"]["rate"]

                            def _fmt_reset(entry):
                                r = entry.get("reset", [])
                                if len(r) == 6:
                                    return f"{r[3]:02d}:{r[4]:02d}:{r[5]:02d}"
                                return "-"

                            def _get(entry, key, fallback_entry=None):
                                v = entry.get(key)
                                if v is not None and v != []:
                                    return v
                                if fallback_entry is not None:
                                    v = fallback_entry.get(key)
                                    if v is not None and v != []:
                                        return v
                                return None

                            core_rem = _get(rate["core"], "remaining", live_rate["core"])
                            search_rem = _get(rate["search"], "remaining", live_rate["search"])
                            core_reset = _fmt_reset(
                                rate["core"] if rate["core"].get("reset") else live_rate["core"]
                            )
                            search_reset = _fmt_reset(
                                rate["search"] if rate["search"].get("reset") else live_rate["search"]
                            )

                            if token is None:
                                key = "core.github.token.none"
                            elif self.root.settings["github"]["useful"] is False:
                                key = "core.github.token.error"
                            else:
                                key = "core.github.token"
                            #   $1=通用剩余 $2=通用刷新 $3=搜索剩余 $4=搜索刷新（与文案顺序一致）
                            self.setToolTip(str(t(
                                self.root.langer.get(key),
                                core_rem, core_reset, search_rem, search_reset
                            )))

                        def _maybe_fetch_rate(self):
                            """hover 时数据缺失才触发一次 checkToken（防抖 2s）。"""
                            if self._hover_pending:
                                return
                            live = self.root.githubAPI.rate
                            core_rem = live["core"].get("remaining")
                            search_rem = live["search"].get("remaining")
                            if core_rem is not None and search_rem is not None:
                                return
                            self._hover_pending = True
                            QThTimer.task(0, lambda e: self.root.githubAPI.checkToken(), dedicated=True)
                            # 2 秒后允许下次 hover 触发
                            QTimer.singleShot(2000, lambda: setattr(self, '_hover_pending', False))

                        def enterEvent(self, event):
                            super().enterEvent(event)
                            self._update_tooltip()
                            if self.root.settings["github"]["token_enc"] is not None:
                                self._maybe_fetch_rate()

                    class DlList(QPushButton):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.init_ui()
                            bus.bind(self)
                            self.shown = True
                            self.hide()
                            self._active_state = None
                            # taskP 周期驱动：job 在 QThTimer 共享子线程检查任务表，
                            # 仅状态变化时 emit 回主线程刷新 UI——主线程零轮询、跨线程消息最少
                            self._dl_timer = QThTimer.taskP(
                                1000, self._check_state, [lambda v: self._apply_visible(v)]
                            )
                            self.destroyed.connect(self._stop_dl_timer)
                            self.clicked.connect(self._on_click)

                        def _on_click(self):
                            """打开下载列表浮层。

                            页面本身在 pages/dlList.py 里按 core.overlays 登记；
                            这里只发个请求，把**自己**当 parent 交出去 —— 本页靠
                            parent.shown / update_shown 反过来告诉这颗图标「列表开着，
                            先别藏」。那是两者之间仅有的约定。
                            """
                            open_overlay("core.dlList", self)

                        def _check_state(self, event):
                            """子线程：读取任务表，与本地状态比对，变化才 emit。"""
                            cur = bool(QDownloader.get_active_tasks())
                            if cur != self._active_state:
                                self._active_state = cur
                                event.lambdas[0].emit(cur)

                        def _apply_visible(self, visible):
                            """主线程：仅状态变化时被调用，更新 UI。"""
                            try:
                                self.setVisible(visible and self.shown)
                            except Exception:
                                pass

                        def update_shown(self):
                            """shown 变化（DlListPage 打开/关闭）后立即刷新，不等下一个周期。"""
                            try:
                                self.setVisible(self._active_state and self.shown)
                            except Exception:
                                pass

                        def _stop_dl_timer(self):
                            # 自身销毁时停掉周期任务，避免对已删除对象回调
                            try:
                                timer = getattr(self, "_dl_timer", None)
                                if timer is not None:
                                    timer.destroy()
                                    self._dl_timer = None
                            except Exception:
                                pass

                        def init_ui(self):
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setStyleSheet("QPushButton {border-radius: 15px;}")

                        def lighting(self, light):
                            self.setIcon(QIcon(change_color(getPath(ACT_DL_LIST),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                            self.setIconSize(QSize(30,30))

                    class TriBtn(QPushButton):
                        def __init__(self, logo: list, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.logo_ = logo
                            self.setLogo_ = 0
                            self.init_ui()
                            bus.bind(self)

                        def init_ui(self):
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid", "tbtn")

                        def setLogo(self, l):
                            self.setLogo_ = l
                            self.lighting(self.root.settings["theme"])

                        def lighting(self, light: bool):
                            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                            logo = change_color(self.logo_[self.setLogo_], color)
                            pixmap = QIcon(logo.pixmap(48,48))

                            self.setIcon(pixmap)

                class TLine(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setProperty("wid", "line")
                        self.setFixedHeight(1)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        pass

                class Main(QWidget):
                    def __init__(self, parent=None, root=None, nav=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.nav = nav          # 左栏导航按钮组，由 Window 注入
                        self.pages = []         # 建好的页面，与 btns 一一对应
                        self.btns = []          # 对应的左栏按钮（pages[i].btn is btns[i]）
                        self._page_keys = {}    # core.pages 的 key -> (page, btn)，对账用
                        self.init_wid()
                        # 默认页由 core.pages 里 default=True 的那条决定；
                        # 没有标记（或注册表为空）时退回第一个。
                        default = self.default_page or (self.pages[0] if self.pages else None)
                        if default is not None:
                            default.click()

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop)

                        self.left = self.Left_(self,self.root)
                        self.layout.addWidget(self.left,0)
                        self.main = self.Main_(self,self.root)
                        self.layout.addWidget(self.main,1)
                        self.right = self.Right_(self,self.root)
                        self.layout.addWidget(self.right,0)

                        # 宿主体交给注册器：页面据此取三栏容器，不必再顺着
                        # parent.parent 猜「我的祖父有三栏」。这也是插件页能独立
                        # 构造的前提 —— 它只认注册表里的具名条目，不认窗口结构。
                        registry.declare("core.shell", registrant="core",
                                         fields=("init", "order"),
                                         required=("init",),
                                         built=("obj",),
                                         doc="宿主体（三栏页容器）：left / main / right")
                        registry.provide("core.shell", "core.shell.workspace", self,
                                         order=1)

                        # 页面本身不在这里登记：各页面模块在自己末尾往 core.pages
                        # 加条目（契约声明在 pages/builtin.py），装配方只负责构建 ——
                        # 「有哪些页面」不归 main.py 管，加页面也不动这里。
                        # 属性名（start/download/game/setting）仍不是内部私有的：
                        # on_start/java.py 按 key 取到 Start 后调它的具名入口
                        # （java_show_progress / java_finish），registry.bind 回填的
                        # 产物也用这些名字，改名要连带一起改。
                        self.default_page = None
                        self.sync_pages()

                        # 插件集合一变就对账：卸掉一个带页面的插件，它的按钮与
                        # 三栏控件不能留在界面上（原先要重启才干净）。
                        events.on("plugins_changed", self.sync_pages)

                    def sync_pages(self):
                        """按 core.pages 对账：没建的补上、不在表里的摘掉。

                        为什么是对账而不是整体重建：整体重建会把所有页面的状态
                        （滚动位置、正在走的任务、控制台内容）一起清掉，而且每次
                        插件变动都重建一遍内置页很浪费。对账只动变化的那几个。
                        """
                        want = registry.entries("core.pages")
                        keys = [e.key for e in want]

                        # 先摘：建过、但现在不在注册表里的（插件被卸了）
                        for key in [k for k in self._page_keys if k not in keys]:
                            self._drop_page(key)

                        # 再补：按注册表顺序插到该在的位置
                        for index, e in enumerate(want):
                            if e.key not in self._page_keys:
                                self._build_page(e, index)

                        # 默认页跟着注册表走
                        self.default_page = next(
                            (self._page_keys[e.key][0] for e in want if e.get("default")),
                            None)

                    def _build_page(self, e, index):
                        """建一页并插到 index（左栏按钮、三栏控件、注册表产物一起）。"""
                        # icon 用 get：契约里它是可选的（required 只要 init/title），
                        # 直接 e.icon 会让「插件页面没配图标」炸掉整个装配循环 ——
                        # NavBtn 本来就接受 None。
                        btn = self.nav.add_btn(e.title, e.get("icon"))
                        page = e.init(Box(parent=self, entry=e, btn=btn))
                        # 这两张表归装配方维护，不由页面自己追加 ——
                        # 插件页面不走内置的 Page 基类，靠自己就会漏。
                        # btns 装的是左栏按钮（pages[i].btn is btns[i]）。
                        self.pages.insert(index, page)
                        self.btns.insert(index, btn)
                        self._page_keys[e.key] = (page, btn)
                        btn.clicked.connect(page.changePage)
                        setattr(self, e.name, page)
                        # 页面与配套按钮在注册表里有唯一出处，后续按 key 就能取到
                        registry.bind("core.pages", e.key, main=page, btn=btn)
                        return page

                    def _drop_page(self, key):
                        """拆一页：三栏控件、左栏按钮、挂在本容器上的属性一起摘。

                        注册表那边不用管 —— 条目已经先被 remove_namespace 摘掉了，
                        所以这里拿不到（也不需要）Entry。
                        """
                        page, btn = self._page_keys.pop(key)
                        was_current = self.main.currentWidget() is getattr(page, "main", None)

                        for stack, wid in ((self.left, getattr(page, "left", None)),
                                           (self.main, getattr(page, "main", None)),
                                           (self.right, getattr(page, "right", None))):
                            if wid is None:
                                continue
                            stack.removeWidget(wid)
                            wid.deleteLater()
                        self.nav.remove_btn(btn)
                        if page in self.pages:
                            self.pages.remove(page)
                        if btn in self.btns:
                            self.btns.remove(btn)

                        # setattr(self, e.name, page) 挂上去的那个属性也要摘
                        attr = key.rpartition(".")[2]
                        if getattr(self, attr, None) is page:
                            delattr(self, attr)

                        # 当前页被拆了：切到还在的第一页，别停在一个已经删掉的控件上
                        if was_current and self.pages:
                            self.pages[0].changePage()

                    class Left_(QStackedWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root


                    class Main_(QStackedWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root

                    class Right_(QStackedWidget):
                        def __init__(self,parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root

        class Tray(QSystemTrayIcon):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.theme = None
                self.init_ui()
                self.init_wid()
                bus.bind(self)
                self.activated.connect(self.on_tray_activated)
                self.root.logger.info(self.root.langer.get("core.log.info.trayLoad"))

            def on_tray_activated(self, reason):
                if reason == QSystemTrayIcon.ActivationReason.Trigger:
                    self.root.logger.debug("Tray clicked by L-mouse button")
                    self.root.window.restore_from_tray()

            def init_ui(self):
                self.setToolTip("Book Mdt Launcher")
                self.setIcon_()
                self.show()

            def init_wid(self):
                self.menu = QMenu()

                self.menu_title = QAction("Book Mdt Launcher", self)
                self.menu_title.triggered.connect(lambda: QTimer.singleShot(0, self.root.window.restore_from_tray))
                self.menu.addAction(self.menu_title)

                self.menu.addSeparator()  # 添加分隔线

                # 扩展项（core.tray.menu）：插件自己给 QAction，托盘只负责摆位置。
                # 它们连同兜底那条分隔线由 reload_plugin_items() 维护 ——
                # 插件卸载后要把它的项摘掉，不能建好就不管。
                self._plugin_actions = []
                self._plugin_sep = self.menu.addSeparator()

                self.menu_close = QAction("", self)
                self.menu_close.triggered.connect(QApplication.quit)
                self.menu.addAction(self.menu_close)

                self.reload_plugin_items()
                self.langing()
                self.setContextMenu(self.menu)

            def reload_plugin_items(self):
                """按 core.tray.menu 重建扩展项。

                插在「关闭」之前；没有扩展项时兜底那条分隔线自己藏起来，
                免得菜单里留一条孤零零的横线。
                """
                for act, _e in self._plugin_actions:
                    self.menu.removeAction(act)
                    act.deleteLater()
                self._plugin_actions = []
                for e in registry.entries("core.tray.menu"):
                    act = e.init(Box(parent=self, entry=e))
                    self.menu.insertAction(self.menu_close, act)
                    self._plugin_actions.append((act, e))
                self._plugin_sep.setVisible(bool(self._plugin_actions))
                self.langing()

            def langing(self):
                self.menu_close.setText(self.root.langer.get("core.tray.menu.close"))
                for act, e in getattr(self, "_plugin_actions", ()):
                    act.setText(self.root.langer.get(e.title))

            def setIcon_(self):
                """根据系统主题设置托盘图标"""
                theme = "light" if self.root.winreg.taskbar_theme() == "dark" else "dark"
                if self.theme != theme:
                    self.theme = theme
                    icon_path = getPath(ICON_APP_LIGHT if theme == "light" else ICON_APP_DARK)

                    # 检查文件是否存在，防止路径错误导致无图标
                    if not os.path.exists(icon_path):
                        self.root.logger.warning(t(self.root.langer.get("core.log.warning.trayIconPath"), icon_path))

                    icon = QIcon(icon_path)
                    self.setIcon(icon)
                    self.root.logger.info(t(self.root.langer.get("core.log.info.trayTheme"), "light" if theme == "light" else "dark"))

        class Winreg():
            def __init__(self, parent=None, root=None):
                self.parent = parent
                self.root = root

            def display_language(self):
                try:
                    dll = ctypes.windll.kernel32
                    langId = dll.GetUserDefaultUILanguage()
                    langStr = locale.windows_locale.get(langId)
                    if langStr:
                        return langStr.replace("_", "-")
                except Exception as e:
                    self.root.logger.error(f"Failed to get language, using en-US: {e}")
                return "en-US"

            def taskbar_theme(self):
                """
                获取 Windows 系统外壳主题颜色 (light/dark)
                """
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                    value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
                    return "light" if value == 1 else "dark"
                except Exception as e:
                    self.root.logger.warning(f"Failed to get system theme: {e}")
                    return "light"

    if __name__ == "__main__":
        app = QApplication(sys.argv)
        socket = QLocalSocket()
        socket.connectToServer("BookMdtLauncherMI")

        if socket.waitForConnected(200):
            socket.write(b"MAINWINSHOW")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            sys.exit(0)
        else:
            socket.deleteLater()

            main = Main(app)
            # --no-open：启动后不弹出窗口（后台/托盘运行，点托盘图标再显示）
            if "--no-open" not in sys.argv[1:]:
                main.window.show()
            code = app.exec()
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(code)

except Exception as e:
    err_msg = _safe_fmt_exc(e)

    print(err_msg)

    dialog = QDialog()
    dialog.setWindowTitle("Book MDT Launcher - Error")
    dialog.setMinimumSize(550, 400)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)
    layout.setContentsMargins(15, 15, 15, 15)

    info_label = QLabel(
        "启动器貌似出现了一点问题，请带上下面这段错误信息前往 "
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues 提交反馈\n\n"
        "The launcher seems to have encountered a problem. Please take the"
        "following error message and submit feedback at "
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues \n"
    )
    info_label.setWordWrap(True)
    info_label.setStyleSheet("font-size: 13px;")
    layout.addWidget(info_label)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setPlainText(err_msg)
    text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
    layout.addWidget(text_edit, 1)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()

    skip_btn = QPushButton("跳转 Skip")
    skip_btn.setFixedWidth(120)
    skip_btn.clicked.connect(lambda: webbrowser.open(
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues"
    ))
    btn_layout.addWidget(skip_btn)

    cancel_btn = QPushButton("取消 Cancel")
    cancel_btn.setFixedWidth(120)
    cancel_btn.clicked.connect(dialog.reject)
    btn_layout.addWidget(cancel_btn)

    layout.addLayout(btn_layout)

    dialog.rejected.connect(QApplication.quit)
    dialog.exec()
    # 出错分支同样强制退出，避免残留线程导致挂起/崩溃弹窗
    os._exit(1)
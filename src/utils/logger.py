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

日志（L0 基层）。

从 main.py 搬出来的（原先它是 Main 里的一个嵌套类）。它只认注入进来的两样：
settings（读 maxLogNum）与 tr（翻译）；拿不到就退化成默认值与英文原文 ——
基层不往上依赖，否则「设置还没建好就没法打日志」会一直缠着启动流程。

`--log=<级别>` 只认 `=` 形式，取值必须是 LEVELS 里的键，其余一律回退 INFO。
"""

import logging
import os
import sys
from datetime import datetime

from .path_utils import getPath
from .utils import t


class Logger:
    """日志（基层）。

    它只依赖注入进来的两样：settings（读 maxLogNum）与 tr（翻译）。
    拿不到就退化成默认值/英文原文 —— 基层不往上依赖，
    否则「设置还没建好就没法打日志」这种事会一直缠着启动流程。
    """

    # 命令行 `--log=<级别>`（只认 `=`，级别取 LEVELS 的键，默认 info）
    LOG_ARG = "--log="
    LEVELS = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    def __init__(self, parent=None, settings=None, tr=None):
        self.parent = parent
        self._settings = settings
        self._tr = tr
        # 缓存已创建的 logger 实例，避免重复创建
        self._loggers = {}
        # 日志级别来自命令行（--log=debug），默认 INFO
        self.level = self._parse_level()
        # 初始化基础配置
        self._setup_base_logging()

    @classmethod
    def _parse_level(cls):
        """解析 `--log=<级别>`：只接受 `=` 形式，取值必须是 LEVELS 里的键。

        `--log:debug`、`--log debug` 等写法一概不接收，回退 INFO。
        """
        for arg in sys.argv[1:]:
            if arg.startswith(cls.LOG_ARG):
                value = arg[len(cls.LOG_ARG):].strip().lower()
                if value in cls.LEVELS:
                    return cls.LEVELS[value]
        return logging.INFO

    def _setup_base_logging(self):
        """
        配置根 Logger ("Main") 的 Handler 和格式。
        其他子 Logger 将共享这些 Handler。
        """
        loglevel = self.level
        self.base_logger_name = "Main"

        # 获取或创建主 logger
        main_logger = logging.getLogger(self.base_logger_name)
        main_logger.setLevel(loglevel)

        # 防止重复添加 handler
        if main_logger.handlers:
            self._loggers[self.base_logger_name] = main_logger
            return

        # 控制台 handler
        console = logging.StreamHandler()
        console.setLevel(loglevel)

        # 文件 handler 配置
        self.log_dir = getPath("BML/logs")
        os.makedirs(self.log_dir, exist_ok=True)

        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S") + f".{now.microsecond // 1000:03d}"
        timestamp_file = os.path.join(self.log_dir, f"{timestamp}.log")
        latest_file = os.path.join(self.log_dir, "latest.log")

        file_handler_timestamp = logging.FileHandler(timestamp_file, encoding="utf-8")
        file_handler_latest = logging.FileHandler(latest_file, mode='w', encoding="utf-8")

        file_handler_timestamp.setLevel(loglevel)
        file_handler_latest.setLevel(loglevel)

        # 设置日志格式：包含 %(name)s 以区分不同模块
        formatter = logging.Formatter('[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s')
        console.setFormatter(formatter)
        file_handler_timestamp.setFormatter(formatter)
        file_handler_latest.setFormatter(formatter)

        # 将 handler 添加到主 logger
        main_logger.addHandler(console)
        main_logger.addHandler(file_handler_timestamp)
        main_logger.addHandler(file_handler_latest)

        self._loggers[self.base_logger_name] = main_logger

    def set_settings(self, settings):
        """设置建得比日志晚（日志要读 maxLogNum），建完回填给它。"""
        self._settings = settings
        return self

    def set_tr(self, tr):
        """翻译也是注入的：宿主挂了 Langer 之后回填。"""
        self._tr = tr
        return self

    def _t(self, key, fallback):
        if self._tr is None:
            return fallback
        try:
            got = self._tr(key)
            return got if got and got != key else fallback
        except Exception:
            return fallback

    def _get_logger(self, name=None):
        """
        获取指定名称的 logger。
        如果 name 为 None 或 "Main"，返回主 logger。
        否则返回 "Main.{name}" 的子 logger。
        """
        if not name or name == "Main":
            target_name = self.base_logger_name
        else:
            # 使用层级命名，例如 "Main.Cmd"，这样它们会共享 Main 的 Handler
            target_name = f"{self.base_logger_name}.{name}"

        if target_name not in self._loggers:
            logger = logging.getLogger(target_name)
            # 子 logger 默认继承父 logger 的级别和 handler，无需额外配置
            # 但如果需要单独控制级别，可以在此设置：
            # logger.setLevel(logging.DEBUG)
            self._loggers[target_name] = logger

        return self._loggers[target_name]

    def _cleanup_old_logs(self):
        max_num = self._settings["maxLogNum"] if self._settings is not None else 50
        if not os.path.exists(self.log_dir):
            return
        files = [f for f in os.listdir(self.log_dir) if f.endswith('.log') and f != 'latest.log']
        files.sort()
        while len(files) > max_num:
            oldest = files.pop(0)
            try:
                os.remove(os.path.join(self.log_dir, oldest))
                # 清理日志时使用主 logger 记录
                self._loggers[self.base_logger_name].info(
                    t(self._t("core.log.info.cleanOldLogs",
                              "cleaned old log: $1"), oldest))
            except Exception as e:
                pass

    # 修改日志方法，增加 name 参数，默认为 None (即 Main)
    def debug(self, msg, name=None):
        self._get_logger(name).debug(msg)

    def info(self, msg, name=None):
        self._get_logger(name).info(msg)

    def warning(self, msg, name=None):
        self._get_logger(name).warning(msg)

    def error(self, msg, name=None, exc_info=False):
        self._get_logger(name).error(msg, exc_info=exc_info)

    def critical(self, msg, name=None):
        self._get_logger(name).critical(msg)

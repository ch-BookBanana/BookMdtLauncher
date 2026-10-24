# 插件开发指南

> BML v2 插件开发文档：清单、基类、生命周期、注册 DSL、扩展点与各项能力。

插件只有一个入口 `BMLCore`。`import src.*` 与 `import main` 会在加载阶段被拦截。
宿主当前的 `API_VERSION = "2.0.0"`（semver）；v2 不向下兼容 v1 的清单名与装饰器，
旧写法在这一版里一律改成 `registrar("命名空间").动词(...)`。

## 最小可运行插件

```text
BML/plugins/hello/
├── data.hjson        # 清单（data.hjson > data.json > data.toml，只放一个）
└── main.py           # 入口文件，缺省 main.py
```

```hjson
// BML/plugins/hello/data.hjson —— hjson：支持 // 注释、无引号键
{
  id: example_hello
  name: Hello
  version: 1.0.0
  api: 2.x
  entry_class: Hello
  author: you
  description: 最小示例插件
}
```

```python
# BML/plugins/hello/main.py
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from BMLCore import BMLPlugin, events, registrar


class HelloPanel(QWidget):
    """自绘界面块：标题一行说明。"""

    def __init__(self, parent=None):
        super().__init__()
        lay = QVBoxLayout(self)
        head = QLabel(events.lang.get("hello.page.head"))   # 按语言键取当前文案
        head.setObjectName("helloHead")                     # 供 qss 选择器使用
        head.setProperty("wid", "text")                     # 沿用内置字体与配色
        lay.addWidget(head)


class Hello(BMLPlugin):
    id = "example_hello"
    name = "Hello"
    version = "1.0.0"
    settings_defaults = {"greet": True}                     # 设置默认值

    # 自己的信号：声明在全局总线上（名字自动加 "example_hello." 前缀）
    hello = registrar("signals").new("hello")

    @registrar("core/pages").new(title="hello.page", order=50)   # 左栏新增一页
    def page(self, ctx):
        return HelloPanel(ctx.parent)                            # 返回控件，宿主挂载

    def on_ready(self):
        # 所有插件加载完成、界面尚未构建
        self.log("就绪，greet = %s" % self.get_config("greet"))
        self.register("signals").set("hello", "ready")           # 发信号
```

启动后日志中出现 `[example_hello]开始加载` 与 `[example_hello]加载完成`（加载器打的），
以及插件自己在 `on_ready` 里打的 `[example_hello] 就绪，greet = True`。

## 常用动作

| 目标 | 写法 |
|------|------|
| 左栏页面 | `@registrar("core/pages").new(title=…, order=50)`，方法返回 `QWidget` |
| 叠加层 / 整页浮层栈 | `registrar("core/overlays")` / `registrar("core/stacks")` |
| 设置项 / 设置分组 | `registrar("core/setting/items")` / `registrar("core/setting/sections")` |
| 游戏管理功能页 | `registrar("core/gameManager/pages")` |
| 托盘项 | `registrar("core/tray/menu").new(title=…)`，构建方法返回 `QAction` |
| css 片段 | 类属性 `css = registrar("core/qss").new("hello.css", qss="…", theme=None)` |
| 信号声明 / 发送 / 订阅 | `register("signals").new / set / watch` |
| 设置读写 | `self.settings["k"]` / `self.get_config("k", 默认)` / `self.set_config("k", v)` / `self.watch_config("k", cb)` |
| 私有目录 / 插件内文件 | `self.workspace` / `self.path("assets/icon.png")` |
| 周期回调 / 后台任务 / 下载 / 线程 | `self.every(...)` / `self.task(...)` / `self.download(...)` / `self.thread(...)` |
| 日志 | `self.log("…")` |

## 章节索引

| 章节 | 内容 |
|------|------|
| [1. 目录结构](<1. 目录结构.md>) | 安装位置、目录布局、`.zip`、多文件 |
| [2. 清单文件](<2. 清单文件.md>) | `data.hjson` 字段、`api` 版本、依赖约束、报错 |
| [3. 插件基类](<3. 插件基类.md>) | `Plugin` / `BMLPlugin`、host 句柄、能力句柄、`Ctx` |
| [4. 生命周期](<4. 生命周期.md>) | 加载、就绪、卸载与回滚顺序 |
| [5. 扩展点](<5. 扩展点.md>) | 注册 DSL、命名空间、九个动词、各扩展点字段 |
| [6. 设置](<6. 设置.md>) | 分桶存储、`self.settings` 视图、变更回调 |
| [7. 语言与样式](<7. 语言与样式.md>) | 语言包、`lang.get`、`core/qss` |
| [8. 事件与托盘](<8. 事件与托盘.md>) | 全局信号总线、托盘项 |
| [9. 资源与依赖](<9. 资源与依赖.md>) | `self.path`、`dependencies`、`self.use` |
| [10. 加载失败与停用](<10. 加载失败与停用.md>) | 日志格式、停用名单、恢复方式 |
| [11. 已知限制](<11. 已知限制.md>) | 当前限制与替代做法 |
| [12. 验证清单](<12. 验证清单.md>) | 冒烟脚本与发布前检查项 |
| [可用包](<可用包.md>) | 可导入的模块范围 |

---

## 相关文档

- [CONTRIBUTING](../../CONTRIBUTING.md) — 项目结构、构建与调试
- [README](../../README.md) — 面向用户的说明

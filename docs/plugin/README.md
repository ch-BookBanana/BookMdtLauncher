# 插件开发指南

> BML 插件开发文档：清单、基类、生命周期、注册装饰器、扩展点与各项能力。

插件只有一个入口 `BMLCore`。`import src.*` 与 `import main` 会在加载阶段被拦截。

## 最小可运行插件

```text
BML/plugins/hello/
├── manifest.toml
└── main.py
```

```toml
id = "example_hello"
version = "1.0.0"
api = "1.x"
entry_class = "Hello"
```

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from BMLCore import BMLPlugin, Widgets, events, registrar


class GreetPanel(QWidget):
    """自绘界面块：标题 + 一行说明。"""

    def __init__(self, parent=None):
        super().__init__()
        lay = QVBoxLayout(self)
        head = QLabel(events.lang.get("hello.page.head"))   # 按语言键取当前语言文案
        head.setObjectName("helloHead")                     # 供 qss 选择器使用
        head.setProperty("wid", "text")                     # 沿用内置字体与配色
        lay.addWidget(head)
        lay.addWidget(QLabel("example_hello"))          # 固定文本无需翻译


class Hello(BMLPlugin):
    id = "example_hello"
    name = "Hello"
    version = "1.0.0"
    # 设置默认值：读不到的键回落到此
    settings_defaults = {"greet": True}

    def __init__(self, host):
        super().__init__(host)                  # 首句：保存 host
        self.log("开始加载")                     # 日志带 [example_hello] 前缀
        self.runs = self.get_config("runs", 0)   # 读取设置项，未存过时为 0

    @registrar.setting(title="hello.greet")      # 设置页「插件」分组新增一项
    def build_greet(self, ctx):
        # ctx.title 即登记时给出的语言键，由控件自行翻译
        return Widgets.Bool(ctx.parent, ctx.title)

    @registrar.page(title="hello.page", order=50)   # 左栏新增一页
    def build_page(self, ctx):
        return GreetPanel(ctx.parent)               # 返回控件，由宿主挂载

    @registrar.tray(title="hello.about")            # 托盘菜单新增一项
    def about(self):
        self.log("托盘项被触发")

    styles = registrar.qss("QLabel#helloHead { font-weight: bold; }")   # 两套主题均生效

    def on_ready(self):
        # 所有插件加载完成、界面尚未构建：适合跨插件初始化
        self.log("就绪，第 %d 次加载" % self.runs)
```

启动后日志中出现 `[example_hello]开始加载` 与 `[example_hello]加载完成`。

## 常用动作

| 目标 | 写法 |
|------|------|
| 左栏页面 | `@registrar.page(title=…, icon=…, order=50)`，方法返回控件 |
| 叠加层 / 整页浮层栈 | `@registrar.overlay(...)` / `@registrar.stack(...)` |
| 设置项 / 设置分组 | `@registrar.setting(title=…)` / `@registrar.section(title=…)` |
| 游戏管理功能页 | `@registrar.game_page(title=…, icon=…)` |
| 托盘项 | `@registrar.tray(title=…)` |
| css 片段 | 类属性 `styles = registrar.qss("…", theme=None)` |
| 事件订阅 / 就绪回调 | `@registrar.on("事件名")` / `@registrar.on_ready()` |
| 设置读写 | `self.get_config("k", 默认)` / `self.set_config("k", v)` / `self.watch_config("k", cb)` |
| 私有数据 / 目录 | `self.data` + `self.save_data()` / `self.workspace` |
| 插件内文件 | `self.path("assets/icon.png")` |
| 日志 | `self.log("…")` |

## 章节索引

| 章节 | 内容 |
|------|------|
| [1. 目录结构](<1. 目录结构.md>) | 安装位置、目录布局、`.zip`、多文件 |
| [2. 清单文件](<2. 清单文件.md>) | `manifest.toml` 字段、`api` 版本、报错 |
| [3. 插件基类](<3. 插件基类.md>) | `Plugin` / `BMLPlugin`、host 句柄、`Ctx` |
| [4. 生命周期](<4. 生命周期.md>) | 加载与卸载顺序 |
| [5. 扩展点](<5. 扩展点.md>) | 注册装饰器与各扩展点字段 |
| [6. 设置](<6. 设置.md>) | 设置、默认值、变更回调、私有数据 |
| [7. 语言与样式](<7. 语言与样式.md>) | 语言包、`lang.get`、`qss` |
| [8. 事件与托盘](<8. 事件与托盘.md>) | `on` / `emit`、托盘项 |
| [9. 资源与依赖](<9. 资源与依赖.md>) | `self.path`、`[dependencies]` |
| [10. 加载失败与停用](<10. 加载失败与停用.md>) | 日志格式、停用名单、恢复方式 |
| [11. 已知限制](<11. 已知限制.md>) | 当前限制与替代做法 |
| [12. 验证清单](<12. 验证清单.md>) | 发布前检查项 |
| [可用包](<可用包.md>) | 可导入的模块范围 |

---

## 相关文档

- [CONTRIBUTING](../../CONTRIBUTING.md) — 项目结构、构建与调试
- [README](../../README.md) — 面向用户的说明

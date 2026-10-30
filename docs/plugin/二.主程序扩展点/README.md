> **怎么读**：每篇开头先看 `>` 引用块——那是「容易踩的坑 / 和你直觉不一样的地方」，正文是正常说明。看不懂时优先信 `>` 里的内容。

# 二.主程序扩展点

> 这一部分讲**宿主提供了哪些位置可以挂东西**（接口、字段、类型、位置）。
> 插件怎么写、类型/注册语法，见 [插件基础语法](../一.插件基础/README.md)。

| 篇 | 扩展点 |
|---|---|
| [1. 页面](1.%20页面.md) | `core/pages`、`core/start/bottom` |
| [2. 浮层](2.%20浮层.md) | `core/overlays`（Modal）/ `core/stacks`（Stack） |
| [3. 设置页](3.%20设置页.md) | `core/setting/pages`、`core/setting/items` |
| [4. 下载页](4.%20下载页.md) | `core/download/tabs` / `sources` / `item/actions` |
| [5. 游戏管理](5.%20游戏管理.md) | `core/gameManager/pages`、`core/gameSettings/sections` |
| [6. 内置信号](6.%20内置信号.md) | `core/signals` 下宿主登记的信号 |
| [7. 托盘与样式](7.%20托盘与样式.md) | `core/tray/menu`、`core/qss` |

每个扩展点是一份**契约**（字段表/必填/是否可覆盖），登记时按契约校验。

---

<div align="middle">
<a href="../README.md">← 插件开发文档</a>  |  <a href="../一.插件基础/README.md">一.插件基础 →</a>
</div>

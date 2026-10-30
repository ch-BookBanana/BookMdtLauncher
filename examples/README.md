# v3 插件示例

三个示例，各讲一件事，按顺序读就行：

| 目录 | 讲什么 |
|---|---|
| `hello/` | 最小插件：声明一个点、写一个值、发一个信号 |
| `types/` | 自定义 BType：成员（init）怎么声明、怎么用 |
| `point/` | BPoint 的整张脸：条目、覆盖、通知、产物槽 |

把任意一个目录复制到 `BML/plugins/` 下，启动启动器就会加载它（`data.hjson` 里
`entry: main.<类名>`，类定义在 `main.py` 里）。

> 想验证它们能跑：`python scripts\check_examples.py`

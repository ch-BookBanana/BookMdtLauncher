"""三个下载源：import 即登记（game.py 末尾会 import 本包）。"""

# 顺序即显示顺序（去掉 order 之后一律按登记先后）：Origin → MindustryX → MindustryARC
from . import origin, mindustryx, mindustryarc       # noqa: F401

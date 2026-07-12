"""导出智能报告集成阶段使用的真实 OpenAPI 契约。

本脚本位于工具层，上游由开发者或契约测试调用，下游直接读取 ``main.app``。
它输出完整应用 OpenAPI，而不是手工拼装报告接口，保证团队合并后能够同时发现
公共路由冲突。输出文件固定为 ``docs/integration/openapi-iteration3.json``。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 直接执行 scripts/*.py 时，Python 默认只把 scripts 目录放在导入路径首位。
# 这里显式加入项目根目录，否则无法导入根目录的 main.py。
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import app  # noqa: E402  项目根目录加入导入路径后才能安全导入


OUTPUT_PATH = PROJECT_ROOT / "docs" / "integration" / "openapi-iteration3.json"


def export_openapi(output_path: Path = OUTPUT_PATH) -> Path:
    """从当前 FastAPI 应用导出 OpenAPI，并返回实际写入路径。

    Args:
        output_path: 契约文件输出位置，默认写入集成交付目录。

    Returns:
        已写入的绝对路径，供命令行和自动化检查继续使用。

    Side Effects:
        创建父目录并覆盖旧快照；不访问数据库，也不调用外部服务。
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path.resolve()


if __name__ == "__main__":
    print(export_openapi())

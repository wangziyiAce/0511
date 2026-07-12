"""智能报告助手数据库迁移契约测试。

本文件位于测试层，用于在不连接生产数据库的情况下核对版本化 SQL 是否覆盖
代码侧 Registry、报告状态和任务来源契约。真实 MySQL 的 upgrade/downgrade
执行仍在集成验收阶段完成；这里先阻止代码枚举与迁移声明再次漂移。
"""

from pathlib import Path

from models.report import REPORT_STATUS_VALUES, TRIGGER_SOURCE_VALUES
from services.reporting.registry import REPORT_REGISTRY


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPGRADE_PATH = PROJECT_ROOT / "migrations" / "20260711_01_sync_report_generation_contract.up.sql"
DOWNGRADE_PATH = PROJECT_ROOT / "migrations" / "20260711_01_sync_report_generation_contract.down.sql"


def _extract_contract_values(sql: str, contract_name: str) -> set[str]:
    """从迁移的机器可读注释中提取契约值，便于测试发现代码与 DDL 漂移。"""
    prefix = f"-- contract:{contract_name}="
    for line in sql.splitlines():
        if line.startswith(prefix):
            return {value.strip() for value in line.removeprefix(prefix).split(",") if value.strip()}
    return set()


def test_upgrade_migration_covers_report_registry():
    """Registry 中每一种报告都必须能写入迁移后的 report_type 字段。"""
    sql = UPGRADE_PATH.read_text(encoding="utf-8")

    assert set(REPORT_REGISTRY).issubset(_extract_contract_values(sql, "report_type"))


def test_upgrade_migration_covers_status_and_trigger_source():
    """迁移声明必须与 ORM 的任务状态和触发来源完全一致。"""
    sql = UPGRADE_PATH.read_text(encoding="utf-8")

    assert set(REPORT_STATUS_VALUES) == _extract_contract_values(sql, "status")
    assert set(TRIGGER_SOURCE_VALUES) == _extract_contract_values(sql, "trigger_source")


def test_migration_has_upgrade_and_downgrade_files():
    """版本化迁移必须同时提供升级和回滚入口，不能只在完成报告中记录 ALTER。"""
    assert UPGRADE_PATH.is_file()
    assert DOWNGRADE_PATH.is_file()


"""申请风险真实验收 seed 的静态契约测试。

测试确保 seed 使用固定的合成 application_id、可以重复执行，并提供范围明确的
清理脚本。风险分本身仍由生产规则计算，本文件不复制业务评分逻辑。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_ROOT / "migrations" / "seeds" / "20260711_application_risk_acceptance.seed.sql"
CLEANUP_PATH = PROJECT_ROOT / "migrations" / "seeds" / "20260711_application_risk_acceptance.cleanup.sql"
SYNTHETIC_IDS = {"1024", "1058", "1091"}


def test_seed_contains_three_synthetic_applications():
    """seed 必须覆盖高风险、中风险和低风险三个合成申请。"""
    sql = SEED_PATH.read_text(encoding="utf-8")

    for application_id in SYNTHETIC_IDS:
        assert f"A{application_id}" in sql
        assert application_id in sql


def test_seed_is_repeatable_and_cleanup_is_scoped():
    """重复执行前只清理三个测试 ID，验收后也能精确删除这些数据。"""
    seed_sql = SEED_PATH.read_text(encoding="utf-8")
    cleanup_sql = CLEANUP_PATH.read_text(encoding="utf-8")

    assert "DELETE FROM application_material_item" in seed_sql
    assert "INSERT INTO application_material_item" in seed_sql
    assert "DELETE FROM application_material_item" in cleanup_sql
    for application_id in SYNTHETIC_IDS:
        assert application_id in cleanup_sql


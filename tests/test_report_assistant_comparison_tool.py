"""只读指标对比工具的集成契约测试。"""

from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.report import ReportGeneration
from services.reporting.assistant.schemas import ComparisonPeriod
from services.reporting.assistant.tools import tool_compare_report_metrics
import pytest
from unittest.mock import Mock, patch
from services.reporting.aggregators import AggregatedReport
from services.reporting.schemas import DataQuality
from utils.database import Base


def test_completed_reports_are_compared_with_four_bound_evidence_items_each():
    """验证工具选择精确周期报告，并为原值与派生值建立不可交换的证据。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ReportGeneration.__table__])
    db = sessionmaker(bind=engine)()
    user = SimpleNamespace(id=7, role_code="admin")
    periods = ComparisonPeriod(
        current_start=date(2026, 7, 1), current_end=date(2026, 7, 7),
        previous_start=date(2026, 6, 24), previous_end=date(2026, 6, 30),
        current_label="本周", previous_label="上周",
    )
    for report_id, start, end, value in (
        (1, periods.current_start, periods.current_end, 5),
        (2, periods.previous_start, periods.previous_end, 3),
    ):
        db.add(ReportGeneration(
            id=report_id, report_type="application_risk", report_title="测试",
            period_start=start, period_end=end, status="completed", schema_version=2,
            generated_by=7, report_content={"metrics": {"high_risk_count": value}},
            data_quality={"level": "ok", "warnings": [], "data_source": "database"},
            create_time=datetime(2026, 7, report_id), update_time=datetime(2026, 7, report_id),
        ))
    db.commit()

    result = tool_compare_report_metrics(
        report_type="application_risk", comparison_period=periods,
        metric_names=["high_risk_count"], current_user=user, db=db,
    )

    comparison = result.data["comparison"][0]
    assert (comparison["current_value"], comparison["previous_value"], comparison["delta"]) == (5, 3, 2)
    evidence = result.data["evidence"]
    assert len(evidence) == 4
    assert len({item["evidence_id"] for item in evidence}) == 4
    assert [(item["comparison_role"], item["source_report_id"]) for item in evidence[:2]] == [
        ("current", 1), ("previous", 2)
    ]
    assert all(item["evidence_id"].startswith("E") and item["evidence_id"][1:].isdigit() for item in evidence)


def test_incompatible_period_granularity_is_rejected_before_comparison():
    """两期天数口径不同不能仅因 Schema 相同就直接比较。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ReportGeneration.__table__])
    db = sessionmaker(bind=engine)()
    period = ComparisonPeriod(
        current_start=date(2026, 7, 1), current_end=date(2026, 7, 7),
        previous_start=date(2026, 6, 20), previous_end=date(2026, 6, 30),
        current_label="本周", previous_label="上一周期",
    )
    for report_id, start, end in ((1, period.current_start, period.current_end), (2, period.previous_start, period.previous_end)):
        db.add(ReportGeneration(id=report_id, report_type="application_risk", report_title="测试",
            period_start=start, period_end=end, status="completed", schema_version=2, generated_by=7,
            report_content={"metrics": {"high_risk_count": 1}}, data_quality={"level": "ok"}))
    db.commit()
    with pytest.raises(ValueError, match="不兼容"):
        tool_compare_report_metrics(report_type="application_risk", comparison_period=period,
            metric_names=["high_risk_count"], current_user=SimpleNamespace(id=7, role_code="admin"), db=db)


def test_duplicate_dimension_rows_are_rejected():
    """同一期同一精确维度出现两行时不得由字典静默覆盖。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ReportGeneration.__table__])
    db = sessionmaker(bind=engine)()
    period = ComparisonPeriod(current_start=date(2026, 7, 1), current_end=date(2026, 7, 7),
        previous_start=date(2026, 6, 24), previous_end=date(2026, 6, 30), current_label="本周", previous_label="上周")
    duplicate = {"channel_metrics": [{"channel": "search", "roi": 1}, {"channel": "search", "roi": 2}]}
    for report_id, start, end in ((1, period.current_start, period.current_end), (2, period.previous_start, period.previous_end)):
        db.add(ReportGeneration(id=report_id, report_type="channel_roi", report_title="测试", period_start=start,
            period_end=end, status="completed", schema_version=2, generated_by=7,
            report_content=duplicate, data_quality={"level": "ok"}))
    db.commit()
    with pytest.raises(ValueError, match="重复维度"):
        tool_compare_report_metrics(report_type="channel_roi", comparison_period=period,
            metric_names=["roi"], current_user=SimpleNamespace(id=7, role_code="admin"), db=db)


def _period():
    return ComparisonPeriod(current_start=date(2026, 7, 1), current_end=date(2026, 7, 7),
        previous_start=date(2026, 6, 24), previous_end=date(2026, 6, 30),
        current_label="本周", previous_label="上周")


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ReportGeneration.__table__])
    return sessionmaker(bind=engine)()


def _report(report_id, start, end, content, *, owner=7, quality=None, updated=None):
    return ReportGeneration(id=report_id, report_type="channel_roi", report_title="测试",
        period_start=start, period_end=end, status="completed", schema_version=2, generated_by=owner,
        report_content=content, data_quality=quality or {"level": "ok"},
        create_time=updated or datetime(2026, 7, 1), update_time=updated or datetime(2026, 7, 1))


def test_role_denied_before_any_database_query():
    """敏感指标角色拒绝必须发生在数据库查询之前。"""
    db = Mock()
    with pytest.raises(PermissionError):
        tool_compare_report_metrics(report_type="channel_roi", comparison_period=_period(),
            metric_names=["roi"], current_user=SimpleNamespace(id=8, role_code="student"), db=db)
    db.query.assert_not_called()


def test_latest_exact_completed_report_uses_update_create_id_tiebreak_and_row_denial():
    """精确周期多报告按更新时间、创建时间、ID 确定选择，且选中行仍需鉴权。"""
    db = _db(); p = _period(); same = datetime(2026, 7, 2)
    for item in (_report(10, p.current_start, p.current_end, {"channel_metrics":[{"channel":"x","roi":1}]}, owner=99, updated=same),
                 _report(11, p.current_start, p.current_end, {"channel_metrics":[{"channel":"x","roi":2}]}, owner=7, updated=same),
                 _report(12, p.previous_start, p.previous_end, {"channel_metrics":[{"channel":"x","roi":1}]}, owner=7)):
        db.add(item)
    db.commit()
    # 行级规则与角色白名单是两道独立防线；这里固定行级结果以验证工具不会跳过该检查。
    with patch("services.reporting.assistant.tools._can_access_report", return_value=False):
        with pytest.raises(PermissionError, match="对比报告"):
            tool_compare_report_metrics(report_type="channel_roi", comparison_period=p, metric_names=["roi"],
                current_user=SimpleNamespace(id=99, role_code="manager"), db=db)
    result = tool_compare_report_metrics(report_type="channel_roi", comparison_period=p, metric_names=["roi"],
        current_user=SimpleNamespace(id=7, role_code="admin"), db=db)
    assert result.data["comparison"][0]["current_value"] == 2


def test_aggregator_fallback_is_read_only_and_creates_no_report_task():
    """无持久化报告时只调用聚合边界，两次聚合后表中仍无任务记录。"""
    db = _db(); p = _period()
    aggregate = Mock(side_effect=[
        AggregatedReport(content={"channel_metrics":[{"channel":"x","roi":2}]}, snapshot={}, data_quality=DataQuality()),
        AggregatedReport(content={"channel_metrics":[{"channel":"x","roi":1}]}, snapshot={}, data_quality=DataQuality()),
    ])
    with patch("services.reporting.aggregators.aggregate_report", aggregate):
        result = tool_compare_report_metrics(report_type="channel_roi", comparison_period=p, metric_names=["roi"],
            current_user=SimpleNamespace(id=7, role_code="admin"), db=db)
    assert result.data["comparison"][0]["delta"] == 1
    assert aggregate.call_count == 2
    assert db.query(ReportGeneration).count() == 0


def test_dimensions_align_exactly_quality_is_independent_and_blocked_evidence_is_auditable():
    """维度并集保留缺失 None；两期质量不覆盖，阻断时派生证据仍存在但值为空。"""
    db = _db(); p = _period()
    db.add(_report(1, p.current_start, p.current_end, {"channel_metrics":[{"channel":"a","roi":2},{"channel":"b","roi":3}]},
        quality={"level":"empty","warnings":["current"]}))
    db.add(_report(2, p.previous_start, p.previous_end, {"channel_metrics":[{"channel":"a","roi":1},{"channel":"c","roi":4}]},
        quality={"level":"ok","warnings":["previous"]}))
    db.commit()
    result = tool_compare_report_metrics(report_type="channel_roi", comparison_period=p, metric_names=["roi"],
        current_user=SimpleNamespace(id=7, role_code="admin"), db=db)
    rows = {row["dimension"]["channel"]: row for row in result.data["comparison"]}
    assert rows["b"]["previous_value"] is None and rows["c"]["current_value"] is None
    assert result.data["current_data_quality"]["warnings"] == ["current"]
    assert result.data["previous_data_quality"]["warnings"] == ["previous"]
    roles = {(e["dimension"]["channel"], e["comparison_role"]): e for e in result.data["evidence"]}
    assert {role for channel, role in roles if channel == "a"} == {"current","previous","delta","change_rate"}
    assert roles[("a","delta")]["value"] is None and roles[("a","change_rate")]["value"] is None
    assert roles[("a","current")]["period_label"] == "本周"
    assert roles[("a","previous")]["period_label"] == "上周"


def test_evidence_ids_stay_stable_across_resolver_order_and_additional_dimension():
    """已有维度证据 ID 不受列表重排或新增其他维度影响。"""
    def run(current_items):
        db = _db(); p = _period()
        db.add(_report(1, p.current_start, p.current_end, {"channel_metrics":current_items}))
        db.add(_report(2, p.previous_start, p.previous_end, {"channel_metrics":[{"channel":"a","roi":1},{"channel":"b","roi":1}]}))
        db.commit()
        result = tool_compare_report_metrics(report_type="channel_roi", comparison_period=p, metric_names=["roi"],
            current_user=SimpleNamespace(id=7, role_code="admin"), db=db)
        return {(e["dimension"].get("channel"), e["comparison_role"]): e["evidence_id"] for e in result.data["evidence"]}
    baseline = run([{"channel":"a","roi":2},{"channel":"b","roi":2}])
    changed = run([{"channel":"z","roi":9},{"channel":"b","roi":2},{"channel":"a","roi":2}])
    assert all(baseline[key] == changed[key] for key in baseline)

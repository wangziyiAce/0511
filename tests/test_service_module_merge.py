from pathlib import Path


def test_customer_agent_services_are_merged_into_chat_service():
    from services import chat_service

    expected_exports = [
        "create_or_get_session",
        "get_session_by_id",
        "get_session_messages",
        "save_message",
        "query_courses",
        "get_course_by_id",
        "query_events",
        "get_event_by_id",
        "register_for_event",
        "cancel_registration",
    ]

    for name in expected_exports:
        assert hasattr(chat_service, name), f"services.chat_service missing {name}"


def test_legacy_course_and_event_service_files_are_removed():
    services_dir = Path(__file__).resolve().parents[1] / "services"

    assert not (services_dir / "course_service.py").exists()
    assert not (services_dir / "event_service.py").exists()

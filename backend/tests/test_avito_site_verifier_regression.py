from __future__ import annotations

from runpy import run_path


QA2 = run_path("tools/avito_site_verifier_qa2.py")
known_site_for = QA2["known_site_for"]
run_regression_controls = QA2["run_regression_controls"]


def test_known_official_domains_are_resolved_before_search() -> None:
    assert known_site_for({"seller": "Грузовичкоф"}) == "https://gruzovichkof.ru/"
    assert known_site_for({"seller": "Типография Группа М"}) == "https://gmprint.ru/"
    assert known_site_for({"seller": "ГИПЕРИОН ПРОЕКТ"}) == "https://giperionpro.ru/"


def test_control_entities_cannot_be_no_site_after_search() -> None:
    rows = [
        {"seller": "Грузовичкоф", "site_status": "NO_SITE_AFTER_SEARCH"},
        {"seller": "Типография Группа М", "site_status": "NO_SITE_AFTER_SEARCH"},
        {"seller": "ГИПЕРИОН ПРОЕКТ", "site_status": "NO_SITE_AFTER_SEARCH"},
    ]
    result = run_regression_controls(rows)
    assert result["passed"] is True

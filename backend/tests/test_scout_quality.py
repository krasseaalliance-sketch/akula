from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scout-vps-stage-20260814" / "scout.py"
spec = importlib.util.spec_from_file_location("scout_stage", MODULE_PATH)
assert spec and spec.loader
scout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scout)


def test_telegram_digest_is_not_a_lead() -> None:
    digest = (
        "За последние сутки наш фриланс-бот нашел 25 проектов на сумму более 0 руб. "
        "в категории Разработка"
    )
    assert scout.telegram_request_is_qualified(digest) is False


def test_concrete_telegram_request_is_kept() -> None:
    request = "Нужен исполнитель: сделать лендинг для мебельной компании, бюджет обсуждается"
    assert scout.telegram_request_is_qualified(request) is True


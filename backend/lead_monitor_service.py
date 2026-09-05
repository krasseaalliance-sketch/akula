"""Lead Hunter Monitor: find real IT demand, not promotional content."""

from __future__ import annotations

import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.lead_intelligence.engine import LeadIntelligenceService
from app.models import (
    Lead,
    ServiceRuntime,
    TelegramAccountProfile,
    TelegramCommunityCandidate,
    TelegramDialog,
    TelegramDiscoveryRun,
    TelegramMessageRecord,
)
from app.lead_monitor_queries import IT_SEARCH_QUERIES_RU, is_real_it_request
from app.service_scheduler import IndependentServiceScheduler, TickResult, actor_for, default_service_specs
from app.telegram_engine.engine import TelegramEngineService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lead-monitor")


_BALI_COMMUNITY_MARKERS = (
    "bali",
    "\u0431\u0430\u043b\u0438",
    "\u0438\u043d\u0434\u043e\u043d\u0435\u0437\u0438\u044f",
    "\u0438\u043d\u0434\u043e\u043d\u0435\u0437\u0438\u0439\u0441\u043a",
)

_BALI_WOMEN_CHAT_MARKERS = (
    "\u0436\u0435\u043d\u0441\u043a",
    "ladies",
    "women",
    "\u0434\u0435\u0432\u043e\u0447",
    "girls",
)


def _is_bali_community_message(item) -> bool:
    """Keep the IT monitor geography-neutral; Bali campaign data is out of scope."""
    haystack = " ".join(
        value.casefold()
        for value in (getattr(item, "dialog_title", None), getattr(item, "dialog_username", None))
        if value
    )
    return any(marker in haystack for marker in _BALI_COMMUNITY_MARKERS)


IT_COMMUNITY_DISCOVERY_QUERIES_RU = (
    "IT", "IT чат", "IT для бизнеса", "программисты", "разработка",
    "веб разработка", "сайт", "бот", "CRM", "автоматизация", "AI",
    "стартап", "фриланс", "удалённая работа", "предприниматели", "бизнес",
    "маркетинг", "дизайн", "телеграм", "Telegram", "интернет магазин",
    "онлайн бизнес", "сервис", "приложение", "интеграция", "аналитика",
    "чат боты", "разработчики", "заказчики", "подрядчики", "агентство",
    "digital", "SaaS", "ecommerce", "малый бизнес", "услуги для бизнеса",
    "автоматизация бизнеса", "создание сайтов", "мобильная разработка",
    "нейросети", "искусственный интеллект", "интернет маркетинг",
)

IT_COMMUNITY_DISCOVERY_LOCATIONS_RU = (
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
    "Красноярск", "Иркутск", "Владивосток", "Сочи", "Калининград",
    "Тбилиси", "Батуми", "Ереван", "Алматы", "Астана", "Дубай",
    "Бали", "Таиланд", "Индонезия", "Стамбул", "Берлин", "Белград",
    "Кипр", "Пхукет", "Куала-Лумпур", "Варшава", "Прага",
)

IT_COMMUNITY_DISCOVERY_LOCATION_TOPICS_RU = (
    "чат", "бизнес", "работа", "IT", "предприниматели",
)


# Keep the discovery source in UTF-8. These assignments intentionally override
# legacy mojibake constants left by the first implementation.
IT_COMMUNITY_DISCOVERY_QUERIES_RU = (
    "IT", "IT чат", "IT для бизнеса", "программисты", "разработка",
    "веб разработка", "сайт", "бот", "CRM", "автоматизация", "AI",
    "стартап", "фриланс", "удалённая работа", "предприниматели", "бизнес",
    "маркетинг", "дизайн", "телеграм", "Telegram", "интернет-магазин",
    "онлайн бизнес", "сервис", "приложение", "интеграция", "аналитика",
    "чат боты", "разработчики", "заказчики", "подрядчики", "агентство",
    "digital", "SaaS", "ecommerce", "малый бизнес", "услуги для бизнеса",
    "автоматизация бизнеса", "создание сайтов", "мобильная разработка",
    "нейросети", "искусственный интеллект", "интернет маркетинг",
)
IT_COMMUNITY_DISCOVERY_LOCATIONS_RU = (
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
    "Красноярск", "Иркутск", "Владивосток", "Сочи", "Калининград",
    "Тбилиси", "Батуми", "Ереван", "Алматы", "Астана", "Дубай",
    "Бали", "Таиланд", "Индонезия", "Стамбул", "Берлин", "Белград",
    "Кипр", "Пхукет", "Куала-Лумпур", "Варшава", "Прага",
)
IT_COMMUNITY_DISCOVERY_LOCATION_TOPICS_RU = (
    "чат", "бизнес", "работа", "IT", "предприниматели",
)


# Replace the legacy mojibake discovery values at runtime.  Keeping this block
# ASCII-escaped avoids another encoding-dependent source edit.
IT_COMMUNITY_DISCOVERY_QUERIES_RU = (
    "IT", "IT \u0447\u0430\u0442", "IT \u0434\u043b\u044f \u0431\u0438\u0437\u043d\u0435\u0441\u0430",
    "\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0438\u0441\u0442\u044b", "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0430",
    "\u0432\u0435\u0431 \u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0430", "\u0441\u0430\u0439\u0442", "\u0431\u043e\u0442", "CRM", "\u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0437\u0430\u0446\u0438\u044f", "AI",
    "\u0441\u0442\u0430\u0440\u0442\u0430\u043f", "\u0444\u0440\u0438\u043b\u0430\u043d\u0441", "\u0443\u0434\u0430\u043b\u0451\u043d\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430", "\u043f\u0440\u0435\u0434\u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0442\u0435\u043b\u0438", "\u0431\u0438\u0437\u043d\u0435\u0441",
    "\u043c\u0430\u0440\u043a\u0435\u0442\u0438\u043d\u0433", "\u0434\u0438\u0437\u0430\u0439\u043d", "\u0442\u0435\u043b\u0435\u0433\u0440\u0430\u043c", "Telegram", "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442 \u043c\u0430\u0433\u0430\u0437\u0438\u043d",
    "\u043e\u043d\u043b\u0430\u0439\u043d \u0431\u0438\u0437\u043d\u0435\u0441", "\u0441\u0435\u0440\u0432\u0438\u0441", "\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435", "\u0438\u043d\u0442\u0435\u0433\u0440\u0430\u0446\u0438\u044f", "\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430",
    "\u0447\u0430\u0442 \u0431\u043e\u0442\u044b", "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a\u0438", "\u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0438", "\u043f\u043e\u0434\u0440\u044f\u0434\u0447\u0438\u043a\u0438", "\u0430\u0433\u0435\u043d\u0442\u0441\u0442\u0432\u043e",
    "digital", "SaaS", "ecommerce", "\u043c\u0430\u043b\u044b\u0439 \u0431\u0438\u0437\u043d\u0435\u0441", "\u0443\u0441\u043b\u0443\u0433\u0438 \u0434\u043b\u044f \u0431\u0438\u0437\u043d\u0435\u0441\u0430",
)
IT_COMMUNITY_DISCOVERY_LOCATIONS_RU = tuple(
    "\u041c\u043e\u0441\u043a\u0432\u0430 \u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433 \u041d\u043e\u0432\u043e\u0441\u0438\u0431\u0438\u0440\u0441\u043a \u0415\u043a\u0430\u0442\u0435\u0440\u0438\u043d\u0431\u0443\u0440\u0433 \u041a\u0430\u0437\u0430\u043d\u044c \u041a\u0440\u0430\u0441\u043d\u043e\u044f\u0440\u0441\u043a \u0418\u0440\u043a\u0443\u0442\u0441\u043a \u0412\u043b\u0430\u0434\u0438\u0432\u043e\u0441\u0442\u043e\u043a \u0421\u043e\u0447\u0438 \u0422\u0431\u0438\u043b\u0438\u0441\u0438 \u0411\u0430\u0442\u0443\u043c\u0438 \u0410\u043b\u043c\u0430\u0442\u044b \u0410\u0441\u0442\u0430\u043d\u0430 \u0414\u0443\u0431\u0430\u0439 \u0411\u0430\u043b\u0438 \u0422\u0430\u0438\u043b\u0430\u043d\u0434 \u0418\u043d\u0434\u043e\u043d\u0435\u0437\u0438\u044f \u0421\u0442\u0430\u043c\u0431\u0443\u043b \u0411\u0435\u0440\u043b\u0438\u043d \u0411\u0435\u043b\u0433\u0440\u0430\u0434".split()
)
IT_COMMUNITY_DISCOVERY_LOCATION_TOPICS_RU = ("\u0447\u0430\u0442", "\u0431\u0438\u0437\u043d\u0435\u0441", "\u0440\u0430\u0431\u043e\u0442\u0430", "IT", "\u043f\u0440\u0435\u0434\u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0442\u0435\u043b\u0438")

BALI_COMMUNITY_DISCOVERY_QUERIES_RU = (
    "\u0411\u0430\u043b\u0438",
    "\u0411\u0430\u043b\u0438 \u0447\u0430\u0442",
    "\u0440\u0443\u0441\u0441\u043a\u0438\u0435 \u043d\u0430 \u0411\u0430\u043b\u0438",
    "\u0411\u0430\u043b\u0438 \u043f\u043e\u043f\u0443\u0442\u0447\u0438\u043a\u0438",
    "\u0418\u043d\u0434\u043e\u043d\u0435\u0437\u0438\u044f \u0411\u0430\u043b\u0438",
    "Ubud",
    "Canggu",
    "Sanur Bali",
)


def discover_bali_communities(db, *, profile, actor, telegram, local_dialog_ids, target: int) -> set[str]:
    """Discover public Bali groups separately from the IT community dataset."""
    existing = set(db.scalars(select(TelegramCommunityCandidate.external_id).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        TelegramCommunityCandidate.category == "BALI_DISCOVERY_CANDIDATE",
    )).all()) - set(local_dialog_ids)
    if len(existing) >= target:
        return existing

    queries = list(BALI_COMMUNITY_DISCOVERY_QUERIES_RU)
    try:
        results_by_query = telegram.search_global_communities_batch(
            profile=profile,
            queries=queries,
            limit=100,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bali community discovery batch failed: %s", type(exc).__name__)
        results_by_query = {}

    found = {}
    hit_counts = {}
    for query in queries:
        for item in results_by_query.get(query, []):
            if item.dialog_type not in {"GROUP", "SUPERGROUP"}:
                continue
            if not item.username or item.external_id in local_dialog_ids:
                continue
            if item.external_id in existing:
                continue
            haystack = " ".join((item.title or "", item.username or "")).casefold()
            if not any(marker in haystack for marker in _BALI_COMMUNITY_MARKERS):
                continue
            hit_counts[item.external_id] = hit_counts.get(item.external_id, 0) + 1
            found.setdefault(item.external_id, (item, query))
            if len(existing) + len(found) >= target:
                break
        if len(existing) + len(found) >= target:
            break

    # Telegram's contacts search exposes public groups that are not present
    # in the global message index. Keep this read-only fallback in the same
    # Bali pass so discovery is not limited to communities with indexed posts.
    for query in ("\u0411\u0430\u043b\u0438", "\u0411\u0430\u043b\u0438 \u0447\u0430\u0442", "Ubud", "Canggu"):
        if len(existing) + len(found) >= target:
            break
        try:
            contact_rows = telegram.search_communities(profile=profile, query=query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bali contacts discovery failed for %s: %s", query, type(exc).__name__)
            continue
        for item in contact_rows:
            if item.dialog_type not in {"GROUP", "SUPERGROUP"}:
                continue
            if not item.username or item.external_id in local_dialog_ids or item.external_id in existing:
                continue
            haystack = " ".join((item.title or "", item.username or "")).casefold()
            if not any(marker in haystack for marker in _BALI_COMMUNITY_MARKERS):
                continue
            hit_counts[item.external_id] = hit_counts.get(item.external_id, 0) + 1
            found.setdefault(item.external_id, (item, query))
            if len(existing) + len(found) >= target:
                break

    if not found:
        return existing

    run = TelegramDiscoveryRun(
        workspace_id=profile.workspace_id,
        integration_account_id=profile.integration_account_id,
        search_query="global_russian_bali_community_discovery",
        status="SUCCEEDED",
        result_count=len(found),
        completed_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    for external_id, (item, query) in found.items():
        candidate = db.scalar(select(TelegramCommunityCandidate).where(
            TelegramCommunityCandidate.workspace_id == profile.workspace_id,
            TelegramCommunityCandidate.external_id == external_id,
        ))
        if candidate is None:
            candidate = TelegramCommunityCandidate(
                workspace_id=profile.workspace_id,
                external_id=external_id,
                title=item.title,
                username=item.username,
                url=f"https://t.me/{item.username}",
                source="TELEGRAM_GLOBAL",
                search_query=query,
                relevance_score=min(1.0, 0.65 + 0.05 * hit_counts.get(external_id, 1)),
                activity_score=min(1.0, hit_counts.get(external_id, 1) / 5),
                member_count=item.member_count or 0,
                language="ru_candidate",
                geography="Bali",
                category="BALI_DISCOVERY_CANDIDATE",
                reason="Returned by global Bali community discovery; language and relevance require verification",
                review_status="NEW",
                discovery_run_id=run.id,
            )
            db.add(candidate)
        else:
            candidate.category = "BALI_DISCOVERY_CANDIDATE"
            candidate.geography = candidate.geography or "Bali"
        existing.add(external_id)
    db.commit()
    logger.info("Bali community discovery completed: %s/%s external candidates", len(existing), target)
    return existing


def join_bali_daily_top(db, *, profile, actor, telegram, local_dialog_ids, join_limit: int):
    """Join Bali communities slowly, excluding women-only communities."""
    candidates = list(db.scalars(select(TelegramCommunityCandidate).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        TelegramCommunityCandidate.category == "BALI_DISCOVERY_CANDIDATE",
        TelegramCommunityCandidate.source == "TELEGRAM_GLOBAL",
        TelegramCommunityCandidate.external_id.not_in(local_dialog_ids),
        TelegramCommunityCandidate.username.is_not(None),
    ).order_by(
        TelegramCommunityCandidate.member_count.desc(),
        TelegramCommunityCandidate.discovered_at.asc(),
    )).all())
    joined = 0
    attempted = 0
    excluded_women = 0
    for candidate in candidates:
        if attempted >= join_limit:
            break
        haystack = " ".join((candidate.title or "", candidate.username or "")).casefold()
        if any(marker in haystack for marker in _BALI_WOMEN_CHAT_MARKERS):
            if candidate.join_status not in {"JOINED", "LEFT"}:
                candidate.join_status = "SKIPPED_UNVERIFIED"
                candidate.join_error = "BALI_WOMEN_CHAT_EXCLUDED_BY_OPERATOR"
            excluded_women += 1
            continue
        if candidate.join_status in {"JOINED", "FAILED", "FLOOD_WAIT", "LEFT", "SKIPPED_UNVERIFIED"}:
            continue
        if (candidate.member_count or 0) < 1000:
            candidate.join_status = "SKIPPED_UNVERIFIED"
            candidate.join_error = "REQUIRES_VERIFIED_MEMBER_COUNT"
            continue
        attempted += 1
        try:
            telegram.join_public_community(
                db,
                profile=profile,
                username=candidate.username,
                actor=actor,
            )
            candidate.join_status = "JOINED"
            candidate.joined_at = datetime.utcnow()
            candidate.join_error = None
            joined += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            error_name = type(exc).__name__
            candidate.join_status = "FLOOD_WAIT" if "FloodWait" in error_name else "FAILED"
            candidate.join_error = error_name
            db.commit()
            if candidate.join_status == "FLOOD_WAIT":
                logger.warning("Bali joining paused after Telegram FloodWait")
                break
    db.commit()
    return {"joined": joined, "attempted": attempted, "excluded_women": excluded_women}


def discover_it_communities(db, *, profile, actor, telegram, local_dialog_ids, target: int) -> set[str]:
    """Discover external public community candidates before scanning messages."""
    existing = set(db.scalars(select(TelegramCommunityCandidate.external_id).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        or_(
            TelegramCommunityCandidate.category.is_(None),
            TelegramCommunityCandidate.category != "BALI_DISCOVERY_CANDIDATE",
        ),
    )).all()) - set(local_dialog_ids)
    if len(existing) >= target:
        return existing

    found = {}
    hit_counts = {}
    queries = (
        *IT_COMMUNITY_DISCOVERY_QUERIES_RU,
        *(f"{location} {topic}"
          for location in IT_COMMUNITY_DISCOVERY_LOCATIONS_RU
          for topic in IT_COMMUNITY_DISCOVERY_LOCATION_TOPICS_RU),
    )
    # Telegram rate limits make an unbounded Cartesian query set unsafe for a
    # single scheduler tick. The next ticks continue discovery while message
    # scanning proceeds against the already confirmed global set.
    queries = queries[:1] if existing else queries[:40]
    try:
        results_by_query = telegram.search_global_communities_batch(
            profile=profile,
            queries=list(queries),
            limit=100,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("community discovery batch failed: %s", type(exc).__name__)
        results_by_query = {}
    for query in queries:
        dialogs = results_by_query.get(query, [])
        for item in dialogs:
            if item.dialog_type not in {"GROUP", "SUPERGROUP"}:
                continue
            if not item.username or item.external_id in local_dialog_ids or item.external_id in existing:
                continue
            hit_counts[item.external_id] = hit_counts.get(item.external_id, 0) + 1
            found.setdefault(item.external_id, (item, query))
            if len(existing) + len(found) >= target:
                break
        if len(existing) + len(found) >= target:
            break

    # Contacts search is a second, read-only discovery source. It finds public
    # chats that have no indexed message matching the broader IT queries.
    for query in ("IT", "\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0438\u0441\u0442\u044b", "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0430", "CRM"):
        if len(existing) + len(found) >= target:
            break
        try:
            contact_rows = telegram.search_communities(profile=profile, query=query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("IT contacts discovery failed for %s: %s", query, type(exc).__name__)
            continue
        for item in contact_rows:
            if item.dialog_type not in {"GROUP", "SUPERGROUP"}:
                continue
            if not item.username or item.external_id in local_dialog_ids or item.external_id in existing:
                continue
            hit_counts[item.external_id] = hit_counts.get(item.external_id, 0) + 1
            found.setdefault(item.external_id, (item, query))
            if len(existing) + len(found) >= target:
                break

    if not found:
        return existing

    run = TelegramDiscoveryRun(
        workspace_id=profile.workspace_id,
        integration_account_id=profile.integration_account_id,
        search_query="global_russian_it_community_discovery",
        status="SUCCEEDED",
        result_count=len(found),
        completed_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    for external_id, (item, query) in found.items():
        candidate = db.scalar(select(TelegramCommunityCandidate).where(
            TelegramCommunityCandidate.workspace_id == profile.workspace_id,
            TelegramCommunityCandidate.external_id == external_id,
        ))
        if candidate is None:
            candidate = TelegramCommunityCandidate(
                workspace_id=profile.workspace_id,
                external_id=external_id,
                title=item.title,
                username=item.username,
                url=f"https://t.me/{item.username}",
                source="TELEGRAM_GLOBAL",
                search_query=query,
                relevance_score=0.5,
                activity_score=min(1.0, hit_counts.get(external_id, 1) / 5),
                member_count=item.member_count or 0,
                language="ru_candidate",
                category="IT_DISCOVERY_CANDIDATE",
                reason="Returned by global Telegram community discovery; language and relevance require verification",
                review_status="NEW",
                discovery_run_id=run.id,
            )
            db.add(candidate)
        existing.add(external_id)
    db.commit()
    logger.info("community discovery completed: %s/%s external candidates", len(existing), target)
    return existing


def rank_and_join_daily_top(db, *, profile, actor, telegram, local_dialog_ids, daily_target: int, join_limit: int):
    """Rank today's external candidates and join only the highest-ranked ones."""
    local_now = datetime.now(ZoneInfo("Asia/Krasnoyarsk"))
    local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    candidates = list(db.scalars(select(TelegramCommunityCandidate).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        TelegramCommunityCandidate.source == "TELEGRAM_GLOBAL",
        TelegramCommunityCandidate.external_id.not_in(local_dialog_ids),
        or_(
            TelegramCommunityCandidate.category.is_(None),
            TelegramCommunityCandidate.category != "BALI_DISCOVERY_CANDIDATE",
        ),
    )).all())
    if not candidates:
        return {"daily_candidates": 0, "top_candidates": 0, "joined": 0}

    relevance_terms = (
        "it", "dev", "разработ", "програм", "бот", "crm", "ai", "чат",
        "бизнес", "автомат", "digital", "стартап", "технолог", "код",
        "дизайн", "веб", "сайт", "мобильн", "данн", "кибер",
    )
    strong_relevance_terms = (
        "разработ", "програм", "developer", "frontend", "backend", "fullstack",
        "devops", "бот", "crm", "автомат", "стартап", "технолог", "код",
        "сайт", "мобильн", "инженер", "it", "digital",
    )
    for candidate in candidates:
        haystack = " ".join((candidate.title or "", candidate.username or "")).casefold()
        if any(term in haystack for term in strong_relevance_terms):
            candidate.relevance_score = max(float(candidate.relevance_score or 0), 0.85)
    db.commit()
    metadata_targets = [
        candidate.username for candidate in candidates
        if candidate.username
        and (candidate.member_count or 0) == 0
        and any(term in " ".join((candidate.title or "", candidate.username or "")).casefold() for term in relevance_terms)
    ][:max(20, min(join_limit, 50))]
    if metadata_targets:
        try:
            metadata = telegram.enrich_community_metadata(profile=profile, usernames=metadata_targets)
            for candidate in candidates:
                values = metadata.get((candidate.username or "").casefold())
                if values:
                    candidate.member_count, candidate.activity_score = values
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("community metadata enrichment failed: %s", type(exc).__name__)

    max_members = max((candidate.member_count or 0) for candidate in candidates) or 1
    for candidate in candidates:
        size_score = math.log1p(candidate.member_count or 0) / math.log1p(max_members)
        candidate.rank_score = round(
            0.55 * size_score
            + 0.30 * float(candidate.activity_score or 0)
            + 0.15 * float(candidate.relevance_score or 0),
            6,
        )
    candidates.sort(key=lambda item: (item.rank_score, item.member_count or 0), reverse=True)
    for position, candidate in enumerate(candidates, start=1):
        candidate.rank_position = position
        # The persisted enum accepts ACCEPTED/NEW/REJECTED; rank_position is
        # the authoritative TOP marker and avoids inventing a new enum value.
        candidate.review_status = "ACCEPTED" if position <= daily_target else "NEW"
    db.commit()

    joined = 0
    attempted = 0
    for candidate in candidates:
        if attempted >= join_limit:
            break
        if candidate.join_status in {"JOINED", "FAILED", "FLOOD_WAIT", "LEFT", "SKIPPED_UNVERIFIED"}:
            continue
        if (candidate.member_count or 0) < 1000 or float(candidate.relevance_score or 0) < 0.75:
            candidate.join_status = "SKIPPED_UNVERIFIED"
            candidate.join_error = "REQUIRES_VERIFIED_RELEVANCE_AND_MEMBER_COUNT"
            db.commit()
            continue
        attempted += 1
        try:
            telegram.join_public_community(
                db,
                profile=profile,
                username=candidate.username,
                actor=actor,
            )
            candidate.join_status = "JOINED"
            candidate.joined_at = datetime.utcnow()
            candidate.join_error = None
            joined += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            error_name = type(exc).__name__
            candidate.join_status = "FLOOD_WAIT" if "FloodWait" in error_name else "FAILED"
            candidate.join_error = error_name
            db.commit()
            if candidate.join_status == "FLOOD_WAIT":
                logger.warning("joining paused after Telegram FloodWait")
                break
    folder_peers = 0
    joined_candidates = list(db.scalars(select(TelegramCommunityCandidate).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        TelegramCommunityCandidate.join_status == "JOINED",
        TelegramCommunityCandidate.username.is_not(None),
    )).all())
    joined_dialog_types = dict(db.execute(select(
        TelegramDialog.external_dialog_id,
        TelegramDialog.dialog_type,
    ).where(TelegramDialog.integration_account_id == profile.integration_account_id)).all())
    joined_usernames = [
        candidate.username for candidate in joined_candidates
        if joined_dialog_types.get(candidate.external_id) in {"GROUP", "SUPERGROUP"}
    ]
    if joined_usernames:
        try:
            folder_peers = telegram.update_dialog_folder(
                profile=profile,
                title="IT-\u043b\u0438\u0434\u044b",
                usernames=joined_usernames,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("IT-leads folder update failed: %s", type(exc).__name__)
    logger.info("daily community top: candidates=%s top=%s joined=%s folder_peers=%s", len(candidates), min(daily_target, len(candidates)), joined, folder_peers)
    return {
        "daily_candidates": len(candidates),
        "top_candidates": min(daily_target, len(candidates)),
        "joined": joined,
        "folder_peers": folder_peers,
    }


IT_SEARCH_QUERIES = (
    "нужен сайт",
    "ищу разработчика",
    "нужен Telegram-бот",
    "нужна CRM",
    "нужна автоматизация",
    "нужно AI",
    "нужно мобильное приложение",
    "посоветуйте программиста",
    "кто может сделать сайт",
    "нужен подрядчик",
    "ищем исполнителя",
    "ищу программиста",
    "ищу специалиста",
    "нужен фрилансер",
    "нужна разработка",
    "разработать сайт",
    "создать приложение",
    "нужна интеграция",
    "кто возьмется за",
    "кто знает программиста",
    "подскажите программиста",
)
IT_SUBJECT = r"(?:сайт\w*|лендинг\w*|разработчик\w*|программист\w*|telegram[- ]?бот\w*|телеграм[- ]?бот\w*|бот\w*|crm|автоматиза\w*|мобильн\w*|приложен\w*|ai|api|интеграц\w*|подрядчик\w*)"
EXPLICIT_REQUEST_PATTERNS = (
    rf"\bнужн(?:ен|а|о|ы)\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\bищу\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\bтребуется\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\b(?:ищу|ищем|нужен|нужна|нужно)\b.{{0,100}}\bисполнител\w*\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\b(?:кто может|кто-нибудь может|посоветуйте|порекомендуйте)\b.{{0,100}}\b(?:сделать|создать|разработать|написать|настроить|подключить|интегрировать)\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\b(?:кто может|посоветуйте|порекомендуйте)\b.{{0,100}}\b(?:разработчика|программиста|подрядчика|исполнителя)\b",
    rf"\b(?:ищу|ищем|нужен|нужна|нужно)\b.{{0,100}}\b(?:специалист\w*|фрилансер\w*)\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\bкто возьмется за\b.{{0,100}}\b{IT_SUBJECT}\b",
    rf"\b(?:кто знает|подскажите)\b.{{0,100}}\b(?:программиста|разработчика|специалиста|фрилансера)\b",
    rf"\b(?:разработать|создать|сделать|настроить|подключить)\b.{{0,100}}\b{IT_SUBJECT}\b",
)
PROMOTIONAL_MARKERS = (
    "регистрация",
    "воркшоп",
    "митап",
    "курс",
    "занятие",
    "программа",
    "стоимость",
    "оплата",
    "группа до",
    "мест мало",
    "каждую среду",
    "подпишитесь",
    "новости",
    "гайд",
    "обзор",
    "релиз",
    "для кого",
    "кто ведет",
)
NON_IT_MARKERS = (
    "создать аккаунт",
    "зарегистрироваться",
    "личный кабинет",
    "продлить визу",
    "продлить визу",
    "виза",
    "билеты",
    "фотошоп билетов",
    "ищу девушку",
)


def _is_real_it_request(text: str | None) -> bool:
    """Require an explicit request for an IT service or executor."""
    normalized = " ".join((text or "").casefold().split())
    if (
        not normalized
        or any(marker in normalized for marker in PROMOTIONAL_MARKERS)
        or any(marker in normalized for marker in NON_IT_MARKERS)
    ):
        return False
    return any(re.search(pattern, normalized) for pattern in EXPLICIT_REQUEST_PATTERNS)


def run_tick(db, workspace) -> TickResult:
    actor = actor_for(workspace, db)
    username = os.getenv("TELEGRAM_ACCOUNT_USERNAME", "Alexey_Mifanyuk")
    profile = db.scalar(
        select(TelegramAccountProfile).where(
            TelegramAccountProfile.workspace_id == workspace.id,
            TelegramAccountProfile.username == username,
            TelegramAccountProfile.authorization_status == "AUTHORIZED",
        )
    )
    if profile is None:
        raise RuntimeError("TELEGRAM_AUTH_REQUIRED")

    tick_started = datetime.utcnow()
    telegram = TelegramEngineService()
    global_rows = []
    for query in IT_SEARCH_QUERIES:
        try:
            global_rows.extend(telegram.search_global_messages(profile=profile, query=query, limit=100))
        except Exception as exc:  # noqa: BLE001
            logger.warning("global Telegram search failed for %r: %s", query, type(exc).__name__)

    unique_rows = {
        (item.dialog_external_id, item.external_id): item
        for item in global_rows
        if not _is_bali_community_message(item)
    }
    filtered_rows = [item for item in unique_rows.values() if _is_real_it_request(item.text)]
    eligible_dialog_ids = telegram.ingest_global_messages(
        db, profile=profile, actor=actor, rows=filtered_rows
    )
    message_ids = {item.external_id for item in filtered_rows}
    leads = telegram.discover_leads(
        db,
        profile=profile,
        actor=actor,
        dialog_external_ids=eligible_dialog_ids,
        message_external_ids=message_ids,
        max_messages=500,
    )
    new_lead_ids = [
        lead.id for lead in leads
        if lead.created_at and lead.created_at >= tick_started
    ]
    LeadIntelligenceService().run(
        db,
        workspace_id=workspace.id,
        actor_id=actor.id,
        lead_ids=new_lead_ids,
    )

    threshold = float(os.getenv("LEAD_MONITOR_CRITICAL_THRESHOLD", "70"))
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).replace(tzinfo=None)
    new_leads = int(
        db.scalar(
            select(func.count(Lead.id)).where(
                Lead.workspace_id == workspace.id,
                Lead.created_at >= today,
            )
        )
        or 0
    )
    critical = sum(1 for lead in leads if float(lead.score or 0) >= threshold)
    new_leads_for_notification = [
        lead
        for lead in leads
        if lead.created_at
        and lead.created_at >= tick_started
        and float(lead.score or 0) >= threshold
    ]
    if new_leads_for_notification:
        lines = [
            "🚨 Lead Hunter Monitor · IT",
            f"Новых потенциальных клиентов: {len(new_leads_for_notification)}",
        ]
        for lead in new_leads_for_notification[:10]:
            lines.append(
                f"• {lead.author_username or lead.author_name or 'Telegram user'} · "
                f"{int(lead.score or 0)}/100 · {lead.detected_need or 'спрос на IT'}"
            )
            lines.append(
                f"  {lead.source_message_url or lead.source_url or 'Ссылка на сообщение недоступна'}"
            )
        telegram.send_operator_notification(
            profile=profile,
            content="\n".join(lines),
            target=os.getenv("TELEGRAM_IT_LEADS_CHAT_ID"),
        )

    return TickResult(
        leads=new_leads,
        critical_leads=critical,
        stats={
            "dialogs_scanned": len(eligible_dialog_ids),
            "global_messages_scanned": len(filtered_rows),
            "russian_community_dialogs_scanned": len(eligible_dialog_ids),
            "lead_records": len(leads),
            "critical_threshold": threshold,
            "publishing_enabled": False,
            "replies_enabled": False,
        },
    )


def run_tick_v2(db, workspace) -> TickResult:
    """Run a 30-minute report tick and a global scan every configured interval."""
    actor = actor_for(workspace, db)
    username = os.getenv("TELEGRAM_ACCOUNT_USERNAME", "Alexey_Mifanyuk")
    profile = db.scalar(select(TelegramAccountProfile).where(
        TelegramAccountProfile.workspace_id == workspace.id,
        TelegramAccountProfile.username == username,
        TelegramAccountProfile.authorization_status == "AUTHORIZED",
    ))
    if profile is None:
        raise RuntimeError("TELEGRAM_AUTH_REQUIRED")

    runtime = db.scalar(select(ServiceRuntime).where(
        ServiceRuntime.workspace_id == workspace.id,
        ServiceRuntime.service_key == "lead_monitor",
    ))
    scan_interval = max(1800, int(os.getenv("LEAD_MONITOR_SCAN_INTERVAL_SECONDS", "1800")))
    now = datetime.now(timezone.utc)
    last_scan_raw = (runtime.settings_json or {}).get("last_scan_at") if runtime else None
    scan_due = True
    if last_scan_raw:
        try:
            last_scan = datetime.fromisoformat(last_scan_raw)
            if last_scan.tzinfo is None:
                last_scan = last_scan.replace(tzinfo=timezone.utc)
            scan_due = (now - last_scan).total_seconds() >= scan_interval
        except ValueError:
            scan_due = True

    telegram = TelegramEngineService()
    leads = []
    eligible_dialog_ids = []
    filtered_rows = []
    local_dialog_ids = set(db.scalars(select(TelegramDialog.external_dialog_id).where(
        TelegramDialog.integration_account_id == profile.integration_account_id,
    )).all())
    community_target = max(1000, int(os.getenv("LEAD_MONITOR_COMMUNITY_TARGET", "1000")))
    join_limit = max(1, int(os.getenv("LEAD_MONITOR_DAILY_JOIN_LIMIT", "1")))
    all_candidate_ids = set(db.scalars(select(TelegramCommunityCandidate.external_id).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        or_(
            TelegramCommunityCandidate.category.is_(None),
            TelegramCommunityCandidate.category != "BALI_DISCOVERY_CANDIDATE",
        ),
    )).all()) - local_dialog_ids
    local_now = datetime.now(ZoneInfo("Asia/Krasnoyarsk"))
    day_start_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    today_candidate_count = int(db.scalar(select(func.count(TelegramCommunityCandidate.id)).where(
        TelegramCommunityCandidate.workspace_id == profile.workspace_id,
        TelegramCommunityCandidate.discovered_at >= day_start_utc,
        TelegramCommunityCandidate.external_id.not_in(local_dialog_ids),
        or_(
            TelegramCommunityCandidate.category.is_(None),
            TelegramCommunityCandidate.category != "BALI_DISCOVERY_CANDIDATE",
        ),
    )) or 0)
    remaining_today = max(0, community_target - today_candidate_count)
    discovered_community_ids = discover_it_communities(
        db,
        profile=profile,
        actor=actor,
        telegram=telegram,
        local_dialog_ids=local_dialog_ids,
        target=len(all_candidate_ids) + remaining_today,
    )
    bali_target = max(1, int(os.getenv("LEAD_MONITOR_BALI_COMMUNITY_TARGET", "1000")))
    discovered_bali_ids = discover_bali_communities(
        db,
        profile=profile,
        actor=actor,
        telegram=telegram,
        local_dialog_ids=local_dialog_ids,
        target=bali_target,
    )
    top_stats = rank_and_join_daily_top(
        db,
        profile=profile,
        actor=actor,
        telegram=telegram,
        local_dialog_ids=local_dialog_ids,
        daily_target=community_target,
        join_limit=join_limit,
    )
    bali_join_limit = max(1, int(os.getenv("LEAD_MONITOR_BALI_DAILY_JOIN_LIMIT", "1")))
    bali_join_stats = join_bali_daily_top(
        db,
        profile=profile,
        actor=actor,
        telegram=telegram,
        local_dialog_ids=local_dialog_ids,
        join_limit=bali_join_limit,
    )
    # Do not block lead discovery while the 1,000-community acquisition goal
    # is still in progress.  The target is a daily expansion objective, not a
    # prerequisite for scanning already discovered global communities.
    discovery_ready = bool(discovered_community_ids)
    scan_started = now
    max_age_hours = max(1, int(os.getenv("LEAD_MONITOR_MESSAGE_MAX_AGE_HOURS", "48")))
    if scan_due and discovery_ready:
        global_rows = []
        for query in IT_SEARCH_QUERIES_RU:
            try:
                global_rows.extend(telegram.search_global_messages(profile=profile, query=query, limit=100))
            except Exception as exc:  # noqa: BLE001
                logger.warning("global Telegram search failed for %r: %s", query, type(exc).__name__)
        # Telegram's global message search often ranks the operator's joined
        # dialogs first. Read recent history from the discovered public peers
        # directly as a read-only fallback; this never joins or writes to them.
        public_candidates = list(db.scalars(select(TelegramCommunityCandidate).where(
            TelegramCommunityCandidate.workspace_id == profile.workspace_id,
            TelegramCommunityCandidate.source == "TELEGRAM_GLOBAL",
            TelegramCommunityCandidate.external_id.not_in(local_dialog_ids),
            TelegramCommunityCandidate.username.is_not(None),
            or_(
                TelegramCommunityCandidate.category.is_(None),
                TelegramCommunityCandidate.category != "BALI_DISCOVERY_CANDIDATE",
            ),
        ).order_by(
            TelegramCommunityCandidate.rank_score.desc(),
            TelegramCommunityCandidate.member_count.desc(),
        ).limit(100)).all())
        public_usernames = [
            candidate.username for candidate in public_candidates
            if "bali" not in " ".join((candidate.title or "", candidate.username or "", candidate.geography or "")).casefold()
        ][:20]
        if public_usernames:
            try:
                global_rows.extend(telegram.read_public_community_messages(
                    profile=profile,
                    usernames=public_usernames,
                    limit=20,
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("public community message read failed: %s", type(exc).__name__)
        # A global search can return old indexed posts. Lead Monitor is a
        # demand detector, so stale messages must never become new leads.
        fresh_cutoff = now - timedelta(hours=max_age_hours)
        global_rows = [
            item for item in global_rows
            if item.sent_at and item.sent_at.replace(tzinfo=timezone.utc) >= fresh_cutoff
        ]
        # Never process the operator's own local dialogs through Lead Hunter.
        # Global search may return them too; they are explicitly out of scope.
        unique_rows = {
            (item.dialog_external_id, item.external_id): item
            for item in global_rows
            if item.dialog_external_id not in local_dialog_ids
            and not _is_bali_community_message(item)
        }
        filtered_rows = [item for item in unique_rows.values() if is_real_it_request(item.text)]
        eligible_dialog_ids = telegram.ingest_global_messages(
            db, profile=profile, actor=actor, rows=filtered_rows
        )
        message_ids = {item.external_id for item in filtered_rows}
        leads = telegram.discover_leads(
            db,
            profile=profile,
            actor=actor,
            dialog_external_ids=eligible_dialog_ids,
            message_external_ids=message_ids,
            max_messages=500,
        )
        new_lead_ids = [
            lead.id for lead in leads
            if lead.created_at and lead.created_at >= scan_started.replace(tzinfo=None)
        ]
        if new_lead_ids:
            LeadIntelligenceService().run(
                db,
                workspace_id=workspace.id,
                actor_id=actor.id,
                lead_ids=new_lead_ids,
            )
        if runtime is not None:
            runtime.settings_json = {
                **(runtime.settings_json or {}),
                "last_scan_at": now.isoformat(),
                "scan_interval_seconds": scan_interval,
                "scope": "global_russian_telegram",
            }

    threshold = float(os.getenv("LEAD_MONITOR_CRITICAL_THRESHOLD", "70"))
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    base = [
        Lead.workspace_id == workspace.id,
        Lead.source_platform == "TELEGRAM",
        Lead.created_at >= today,
        Lead.source_dialog_external_id.is_not(None),
        Lead.source_dialog_external_id.not_in(local_dialog_ids),
    ]
    fresh_lead_cutoff = (now - timedelta(hours=max_age_hours)).replace(tzinfo=None)
    lead_message_join = and_(
        TelegramMessageRecord.workspace_id == Lead.workspace_id,
        TelegramMessageRecord.external_dialog_id == Lead.source_dialog_external_id,
        TelegramMessageRecord.external_message_id == Lead.source_message_id,
    )
    new_leads = int(db.scalar(
        select(func.count(Lead.id)).join(TelegramMessageRecord, lead_message_join).where(
            *base,
            TelegramMessageRecord.sent_at >= fresh_lead_cutoff,
        )
    ) or 0)
    critical = int(db.scalar(
        select(func.count(Lead.id)).join(TelegramMessageRecord, lead_message_join).where(
            *base,
            Lead.score >= threshold,
            TelegramMessageRecord.sent_at >= fresh_lead_cutoff,
        )
    ) or 0)
    new_critical = [
        lead for lead in leads
        if lead.created_at and lead.created_at >= scan_started.replace(tzinfo=None) and float(lead.score or 0) >= threshold
    ]

    lines = [
        "Lead Hunter Monitor · IT",
        f"Сканирование: {'выполнено' if scan_due else 'не требуется до следующего прохода'}",
        f"Новых лидов сегодня: {new_leads}",
        f"Высокий приоритет: {critical}",
        f"Найдено в последнем скане: {len(leads)}",
    ]
    for lead in new_critical[:10]:
        lines.extend([
            f"• {lead.author_username or lead.author_name or 'Telegram user'} · {int(lead.score or 0)}/100",
            f"  {lead.source_message_url or lead.source_url or 'Ссылка недоступна'}",
        ])
    telegram.send_operator_notification(
        profile=profile,
        content="\n".join(lines),
        target=os.getenv("TELEGRAM_IT_LEADS_CHAT_ID"),
    )
    return TickResult(
        leads=new_leads,
        critical_leads=critical,
        stats={
            "scan_performed": scan_due and discovery_ready,
            "scan_interval_seconds": scan_interval,
            "report_interval_seconds": 1800,
            "scope": "global_russian_telegram",
            "community_discovery_target": community_target,
            "community_candidates_external": len(discovered_community_ids),
            "bali_community_candidates_external": len(discovered_bali_ids),
            "bali_community_discovery_target": bali_target,
            "community_candidates_today": top_stats["daily_candidates"],
            "community_top_today": top_stats["top_candidates"],
            "community_joined_today": top_stats["joined"],
            "community_discovery_ready": discovery_ready,
            "community_join_limit": join_limit,
            "bali_community_joined_today": bali_join_stats["joined"],
            "bali_community_join_limit": bali_join_limit,
            "bali_women_excluded": bali_join_stats["excluded_women"],
            "dialogs_scanned": len(eligible_dialog_ids),
            "global_messages_scanned": len(filtered_rows),
            "lead_records": len(leads),
            "critical_threshold": threshold,
            "publishing_enabled": False,
            "replies_enabled": False,
        },
    )


if __name__ == "__main__":
    IndependentServiceScheduler(default_service_specs()["lead_monitor"], run_tick_v2).run_forever()

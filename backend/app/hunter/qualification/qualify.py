from __future__ import annotations

from ..models import IntentResult, NormalizedSignal, QualificationResult


def qualify_signal(signal: NormalizedSignal, intent: IntentResult) -> QualificationResult:
    text = signal.text_for_analysis.casefold()
    reasons: list[str] = []
    if signal.raw_signal.lead_type_hint == "OPPORTUNITY":
        return QualificationResult("OPPORTUNITY", "OPPORTUNITY", ("PROFILE_OPPORTUNITY_SIGNAL",), 0.82, intent.evidence)
    if any(x in text for x in (
        "резюме", "ищу работу", "вакансия", "требуется сотрудник", "ищем в штат", "рекрутер", "оператор",
        "человека на вахту", "человека для работы", "найти человека", "добавлять товары", "карточки товаров",
        "написание отзыва", "публиковать отзывы", "публикация отзывов", "отзывы на wildberries", "wildberries",
        "автокад", "чертежи в автокаде",
    )):
        reasons.append("VACANCY_OR_JOB_SEEKER")
    if any(x in text for x in (
        "копирайтер", "создавать тексты", "писать тексты", "брендбук", "массовое редактирование картинок",
        "картинки в corel", "карточка товара в figma",
    )):
        reasons.append("OUT_OF_PROFILE_CONTENT_OR_DESIGN_ONLY")
    if any(x in text for x in ("я делаю сайты", "сделаю сайт", "оказываю услуги", "портфолио исполнителя", "мои услуги")) and not any(x in text for x in ("нужен", "требуется", "ищем", "необходимо", "ищу специалиста")):
        reasons.append("SUPPLIER_SELF_PROMOTION")
    if any(x in text for x in ("совет", "кто знает", "посоветуйте", "сколько стоит")) and not intent.intent:
        reasons.append("INFORMATIONAL")
    if intent.abstain:
        reasons.extend(intent.abstain_reasons)
    if not intent.intent:
        reasons.append("NO_SUPPORTED_PRODUCT_INTENT")
    if reasons:
        decision = "NEEDS_REVIEW" if not any(x in reasons for x in ("SUPPLIER_SELF_PROMOTION", "NO_SUPPORTED_PRODUCT_INTENT", "OUT_OF_PROFILE_CONTENT_OR_DESIGN_ONLY")) else "REJECTED"
        return QualificationResult(decision, "NOT_LEAD", tuple(dict.fromkeys(reasons)), intent.confidence, intent.evidence)
    return QualificationResult("QUALIFIED", "HOT_DEMAND", ("DIRECT_PROJECT_REQUEST",), min(0.99, intent.confidence + 0.04), intent.evidence)

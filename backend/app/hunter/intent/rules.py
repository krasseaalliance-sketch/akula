from __future__ import annotations

import re

from ..models import IntentResult, NormalizedSignal


class RulesIntentProvider:
    """Deterministic semantic baseline for fresh public demand signals."""

    def analyze(self, signal: NormalizedSignal) -> IntentResult:
        text = signal.text_for_analysis
        lower = text.casefold()
        evidence: list[str] = []
        rejected_supplier = any(
            phrase in lower
            for phrase in ("я делаю сайты", "сделаю сайт", "разработка сайтов под ключ", "оказываю услуги", "мои услуги")
        )
        direct = any(
            phrase in lower
            for phrase in (
                "нужен сайт", "нужен новый сайт", "нужен интернет-магазин", "нужен калькулятор", "нам нужны", "нужны ",
                "разработать сайт", "создать сайт", "требуется сайт", "ищем подрядчика", "нужен разработчик", "исправить",
                "доработать сайт", "доработать opencart", "редизайн сайта", "редизайн страницы", "нужна верстка", "посадить верстку", "перенести дизайн", "исправить главную", "нужен бот", "нужно приложение",
                "разработать приложение", "сделать лендинг", "нужен исполнитель", "нужен специалист",
                "ищу разработчика", "ищу специалиста", "требуется разработчик", "нужно сделать", "нужно создать",
                "нужно разработать", "нужно делать", "нужно собрать", "собрать сайт", "собрать лендинг",
                "необходимо создать", "сделать страницу", "создание сайта", "необходимо разработать", "требуется разработать",
                "на постоянку нужен",
            )
        )
        if direct:
            evidence.append("direct_request_phrase")
        if any(phrase in lower for phrase in ("тз", "техническое задание", "макет", "figma", "функционал", "интеграци", "прототип")):
            evidence.append("project_detail")
        if any(phrase in lower for phrase in ("бюджет", "руб", "₽", "договорная", "стоимость", "гонорар")):
            evidence.append("budget_or_price_signal")
        if any(phrase in lower for phrase in ("срок", "дедлайн", "за 5 дней", "за 7 дней", "сегодня", "на этой неделе")):
            evidence.append("timeframe_signal")

        intent = self._intent(lower)
        if intent and not rejected_supplier and any(
            phrase in lower for phrase in ("нужен", "нужно", "необходимо", "требуется", "ищем", "ищу", "создать", "разработ", "сделать", "собрать")
        ):
            direct = True
            if "direct_request_phrase" not in evidence:
                evidence.append("direct_request_phrase")
        requested_product = self._product(intent)
        budget_min, budget_max = self._budget(text)
        deadline = self._deadline(lower)
        urgency = "HIGH" if any(x in lower for x in ("срочно", "сегодня", "на этой неделе", "за 1 день")) else "MEDIUM" if deadline or "за " in lower else "LOW"
        industry = self._industry(lower)
        features = tuple(self._features(lower))
        confidence = min(0.98, 0.42 + len(evidence) * 0.10 + (0.18 if intent else 0))
        abstain_reasons: list[str] = []
        if not direct:
            abstain_reasons.append("NO_DIRECT_PROJECT_INTENT")
        return IntentResult(
            commercial_intent="HIGH" if direct and intent else "MEDIUM" if direct else "NONE",
            intent=intent, requested_product=requested_product, industry=industry,
            company_or_person=signal.raw_signal.author_identifier,
            city=signal.raw_signal.metadata.get("city"), region=signal.raw_signal.metadata.get("region"),
            budget_min=budget_min, budget_max=budget_max, currency="RUB" if budget_min or budget_max or "руб" in lower or "₽" in text else None,
            deadline=deadline, urgency=urgency,
            existing_site="YES" if any(x in lower for x in ("действующий сайт", "текущий сайт", "доработать сайт", "на wordpress", "на битрикс")) else None,
            required_features=features,
            project_stage="SPECIFIED" if any(x in lower for x in ("тз", "техническое задание")) or len(features) >= 2 else "EARLY",
            decision_maker_signal="DIRECT_POSTER" if direct else None, confidence=round(confidence, 4),
            evidence=tuple(evidence), abstain=bool(abstain_reasons), abstain_reasons=tuple(abstain_reasons),
        )

    @staticmethod
    def _intent(text: str) -> str | None:
        if any(x in text for x in ("интернет-магазин", "магазин на", "магазина", "корзин", "оплат", "opencart")):
            return "BUILD_ECOMMERCE"
        if any(x in text for x in ("редизайн", "переделать сайт", "доработать сайт", "доработки сайта", "обновить сайт")):
            return "REDESIGN_WEBSITE"
        if any(x in text for x in ("лендинг", "landing", "сайт-визит", "одностранич")):
            return "BUILD_LANDING"
        if re.search(r"(?:telegram|телеграм)[- ]?бот\w*|\bбот\w*\b", text):
            return "BUILD_BOT"
        if any(x in text for x in ("приложени", "android", "ios")):
            return "BUILD_MOBILE_APP"
        if any(x in text for x in ("калькулятор", "конфигуратор")):
            return "BUILD_CALCULATOR" if "калькулятор" in text else "BUILD_CONFIGURATOR"
        if any(x in text for x in ("автоматизац", "интеграци", "синхронизац")):
            return "AUTOMATE_BUSINESS_PROCESS"
        if any(x in text for x in ("3d", "3d-модел", "визуализац")):
            return "CREATE_3D_RENDER" if "3d" in text else "CREATE_VISUALIZATION"
        if any(x in text for x in ("сайт", "верстк", "веб-дизайн", "web", "opencart", "битрикс", "wordpress", "tilda", "главной странице")):
            return "BUILD_WEBSITE"
        return None

    @staticmethod
    def _product(intent: str | None) -> str | None:
        return {
            "BUILD_ECOMMERCE": "internet_store", "REDESIGN_WEBSITE": "existing_website", "BUILD_LANDING": "landing_page",
            "BUILD_BOT": "business_bot", "BUILD_MOBILE_APP": "mobile_app", "BUILD_CALCULATOR": "calculator",
            "BUILD_CONFIGURATOR": "configurator", "AUTOMATE_BUSINESS_PROCESS": "digital_process",
            "CREATE_3D_RENDER": "3d_render", "CREATE_VISUALIZATION": "visualization", "BUILD_WEBSITE": "website",
        }.get(intent or "")

    @staticmethod
    def _industry(text: str) -> str | None:
        for key, value in (("промышлен", "INDUSTRIAL"), ("косметолог", "BEAUTY"), ("клиник", "HEALTHCARE"), ("магазин", "RETAIL"), ("транспорт", "LOGISTICS"), ("мебел", "FURNITURE"), ("образован", "EDUCATION"), ("журнал", "MEDIA")):
            if key in text:
                return value
        return None

    @staticmethod
    def _features(text: str) -> list[str]:
        mapping = (("фигм", "FIGMA"), ("битрикс", "BITRIX"), ("wordpress", "WORDPRESS"), ("тильд", "TILDA"), ("оплат", "PAYMENTS"), ("crm", "CRM"), ("api", "API"), ("адаптив", "RESPONSIVE"), ("мобильн", "MOBILE"), ("android", "ANDROID"), ("ios", "IOS"), ("личн", "ACCOUNT"), ("каталог", "CATALOG"), ("корзин", "CART"), ("интеграц", "INTEGRATION"), ("калькулятор", "CALCULATOR"), ("форм", "FORM"), ("заявк", "REQUEST_FORM"), ("текст", "COPY"), ("логотип", "BRAND"))
        return [label for needle, label in mapping if needle in text]

    @staticmethod
    def _budget(text: str) -> tuple[int | None, int | None]:
        numbers = [int(value.replace(" ", "")) for value in re.findall(r"(?<!\w)(\d{1,3}(?:[\s ]\d{3})+|\d{4,7})(?:\s?₽|\s?руб|\s?р\.)?", text, flags=re.IGNORECASE)]
        numbers = [number for number in numbers if number >= 1000]
        return (min(numbers), max(numbers)) if numbers else (None, None)

    @staticmethod
    def _deadline(text: str) -> str | None:
        match = re.search(r"(?:за|в течение)\s+(\d+)\s+(дн|дней|день|недел)", text.casefold())
        return match.group(0) if match else None

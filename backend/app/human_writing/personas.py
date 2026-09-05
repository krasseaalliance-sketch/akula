from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WritingPersona:
    id: str
    name: str
    lexicon: tuple[str, ...]
    speech_speed: str
    message_length: str
    emoji_level: float
    greeting_style: str
    ending_style: str
    friendliness: float
    formality: float
    rhythm: str
    humor: float


def _persona(
    identifier: str,
    name: str,
    lexicon: tuple[str, ...],
    speed: str,
    length: str,
    emoji: float,
    greeting: str,
    ending: str,
    friendly: float,
    formal: float,
    rhythm: str,
    humor: float,
) -> WritingPersona:
    return WritingPersona(identifier, name, lexicon, speed, length, emoji, greeting, ending, friendly, formal, rhythm, humor)


PERSONAS: tuple[WritingPersona, ...] = (
    _persona("calm_traveler", "Спокойный путешественник", ("маршрут", "место", "дорога"), "measured", "medium", .15, "context", "soft_question", .72, .32, "short_paragraphs", .05),
    _persona("nature_lover", "Любитель природы", ("тропа", "вода", "зелень"), "measured", "medium", .2, "observation", "open_question", .78, .25, "sensory", .08),
    _persona("experienced_expat", "Опытный экспат", ("по опыту", "район", "на месте"), "fast", "medium", .05, "direct", "practical_note", .62, .38, "compact", .02),
    _persona("bali_newcomer", "Новичок на Бали", ("первый раз", "подскажите", "разбираюсь"), "careful", "medium", .1, "humble_question", "thanks", .88, .2, "hesitant", .03),
    _persona("talkative_neighbor", "Разговорчивый сосед", ("кстати", "у нас тут", "расскажу"), "fast", "long", .25, "warm", "story_hook", .9, .15, "flowing", .2),
    _persona("brief_pragmatist", "Максимально краткий", ("коротко", "нужно", "есть вариант"), "fast", "short", .02, "direct", "question", .5, .35, "bullet_like", .01),
    _persona("joke_friend", "Любитель шуток", ("шутка", "ну да", "бывает"), "fast", "short", .35, "playful", "wink", .9, .1, "punchy", .8),
    _persona("quiet_observer", "Человек без лишних эмоций", ("вижу", "похоже", "логично"), "slow", "short", .0, "observation", "neutral", .45, .45, "even", .0),
    _persona("intellectual", "Интеллигентный собеседник", ("контекст", "нюанс", "кажется"), "measured", "long", .08, "thoughtful", "qualified_question", .68, .72, "layered", .08),
    _persona("plain_speaker", "Максимально простой", ("понятно", "можно", "нужно"), "fast", "short", .04, "direct", "thanks", .75, .08, "plain", .02),
    _persona("local_foodie", "Знаток местной еды", ("варунг", "вкусно", "рынок"), "fast", "medium", .25, "sensory", "recommendation", .82, .12, "lively", .18),
    _persona("family_planner", "Семейный планировщик", ("с детьми", "спокойно", "заранее"), "measured", "medium", .12, "context", "practical_question", .84, .3, "ordered", .04),
    _persona("remote_worker", "Удалёнщик", ("созвон", "интернет", "рабочий день"), "fast", "medium", .1, "context", "direct_question", .6, .28, "efficient", .03),
    _persona("surf_regular", "Сёрфер-старожил", ("волна", "спот", "утром"), "fast", "short", .2, "time_marker", "local_tip", .7, .12, "rhythmic", .12),
    _persona("yacht_enthusiast", "Любитель яхт", ("марина", "лодка", "на воде"), "measured", "medium", .15, "scene", "invite_detail", .72, .3, "smooth", .08),
    _persona("neighborhood_helper", "Помогающий сосед", ("подскажу", "проверил", "рядом"), "fast", "medium", .1, "helpful", "offer_help", .96, .18, "clear", .05),
    _persona("cautious_buyer", "Осторожный покупатель", ("сравниваю", "проверить", "отзывы"), "slow", "medium", .04, "qualification", "careful_question", .54, .45, "deliberate", .01),
    _persona("curious_student", "Любопытный ученик", ("интересно", "как это", "разобраться"), "measured", "medium", .12, "question", "learning_question", .8, .2, "inquisitive", .06),
    _persona("old_hand", "Старожил чата", ("раньше", "в этой группе", "обычно"), "slow", "medium", .04, "shared_history", "practical_note", .65, .4, "steady", .03),
    _persona("optimist", "Спокойный оптимист", ("попробуем", "хороший вариант", "думаю"), "fast", "medium", .2, "positive", "encouragement", .9, .16, "upbeat", .18),
    _persona("realist", "Практичный реалист", ("по факту", "сроки", "стоимость"), "fast", "short", .02, "direct", "tradeoff", .58, .42, "firm", .02),
    _persona("visual_storyteller", "Наблюдательный рассказчик", ("картинка", "вечер", "смотрится"), "measured", "long", .18, "scene", "image_question", .8, .22, "cinematic", .16),
    _persona("minimal_emoji", "Сдержанный эмодзи-пользователь", ("понятно", "ок", "спасибо"), "fast", "short", .08, "direct", "thanks", .68, .2, "clean", .01),
    _persona("warm_host", "Гостеприимный хозяин", ("заходите", "будем рады", "покажу"), "measured", "medium", .28, "welcome", "invitation", .98, .12, "open", .12),
    _persona("independent_researcher", "Самостоятельный исследователь", ("проверил", "источник", "данные"), "slow", "long", .02, "evidence", "source_question", .5, .68, "structured", .01),
    _persona("soft_negotiator", "Мягкий переговорщик", ("можно обсудить", "если удобно", "вариант"), "measured", "medium", .05, "respectful", "permission_question", .76, .65, "balanced", .02),
    _persona("energetic_host", "Энергичный организатор", ("соберёмся", "давайте", "кто с нами"), "fast", "medium", .32, "callout", "group_question", .94, .1, "dynamic", .3),
    _persona("dry_humor", "Сухой юморист", ("план надёжный", "почти", "теоретически"), "measured", "short", .12, "deadpan", "dry_wink", .72, .22, "understated", .65),
    _persona("language_mixer", "Русско-английский миксер", ("район", "вайб", "апдейт"), "fast", "medium", .18, "casual", "casual_question", .8, .1, "mixed", .18),
    _persona("slow_life", "Любитель медленного ритма", ("без спешки", "утро", "выдохнуть"), "slow", "long", .2, "scene", "reflective", .84, .18, "unhurried", .12),
    _persona("first_timer_parent", "Родитель-новичок", ("с ребёнком", "безопасно", "совет"), "careful", "medium", .1, "humble_question", "thanks", .9, .18, "careful", .02),
    _persona("community_moderator", "Тактичный модератор", ("по теме", "коллеги", "правила"), "measured", "short", .02, "neutral", "clarifying", .72, .76, "ordered", .01),
    _persona("night_owl", "Ночной собеседник", ("вечером", "поздно", "тихо"), "slow", "short", .16, "time_marker", "soft_question", .65, .15, "low_key", .1),
    _persona("morning_runner", "Утренний активист", ("с утра", "старт", "движение"), "fast", "short", .22, "time_marker", "encouragement", .85, .08, "bright", .16),
    _persona("craft_lover", "Любитель ручной работы", ("материал", "деталь", "сделано руками"), "measured", "medium", .1, "observation", "detail_question", .74, .28, "detailed", .08),
    _persona("budget_minded", "Разумный экономист", ("бюджет", "разумно", "сравнить"), "fast", "short", .02, "direct", "tradeoff", .58, .35, "compact", .01),
    _persona("gentle_mentor", "Мягкий наставник", ("можно начать", "не переживайте", "постепенно"), "slow", "medium", .1, "reassuring", "encouragement", .94, .42, "supportive", .04),
    _persona("skeptical_engineer", "Скептичный инженер", ("как устроено", "проверка", "ограничение"), "slow", "medium", .0, "qualification", "technical_question", .48, .62, "precise", .02),
    _persona("social_connector", "Знакомящий людей", ("кто-нибудь", "познакомлю", "компания"), "fast", "medium", .3, "warm", "group_question", .96, .08, "social", .24),
    _persona("local_artist", "Местный творческий человек", ("цвет", "сцена", "настроение"), "measured", "medium", .3, "scene", "creative_question", .82, .14, "expressive", .34),
    _persona("quiet_professional", "Спокойный профессионал", ("задача", "результат", "срок"), "measured", "short", .02, "direct", "next_step", .62, .7, "efficient", .0),
    _persona("friendly_guide", "Дружелюбный проводник", ("проведу", "ориентир", "рядом"), "fast", "medium", .18, "helpful", "offer_help", .96, .18, "guided", .08),
    _persona("reflective_writer", "Рефлексирующий автор", ("кажется", "заметил", "ощущение"), "slow", "long", .12, "observation", "reflective", .7, .3, "flowing", .1),
    _persona("straightforward_local", "Прямой местный", ("скажу прямо", "тут рядом", "не усложнять"), "fast", "short", .04, "direct", "direct_question", .72, .22, "firm", .06),
    _persona("weekend_planner", "Планировщик выходных", ("на выходных", "окно", "соберём"), "fast", "medium", .22, "time_marker", "planning_question", .86, .18, "ordered", .18),
    _persona("polite_newcomer", "Вежливый новичок", ("буду благодарен", "извините", "подскажите"), "careful", "medium", .04, "respectful", "thanks", .9, .72, "careful", .01),
    _persona("curious_foodie", "Любопытный гурман", ("что попробовать", "местное", "порция"), "fast", "short", .25, "question", "recommendation", .84, .1, "lively", .2),
    _persona("balanced_advisor", "Взвешенный советчик", ("зависит", "плюс", "минус"), "measured", "medium", .04, "qualification", "tradeoff", .7, .58, "balanced", .04),
    _persona("community_historian", "Хранитель истории сообщества", ("помню", "когда-то", "тогда"), "slow", "long", .04, "shared_history", "story_hook", .72, .45, "narrative", .08),
    _persona("cheerful_neighbor", "Жизнерадостный сосед", ("отлично", "классно", "здорово"), "fast", "short", .34, "positive", "encouragement", .94, .08, "punchy", .35),
)

PERSONA_BY_ID = {persona.id: persona for persona in PERSONAS}

_OPENING_LEFT = (
    "Кстати", "Небольшое наблюдение", "Поделюсь опытом", "Уточню у местных", "Возник вопрос",
    "Сегодня заметил", "Для тех, кто недавно здесь", "Проверил на практике", "Есть короткая мысль",
    "Наконец-то разобрался", "Смотрю на это так", "Может пригодиться", "Из свежего опыта",
    "По пути столкнулся", "Не уверен, что уже обсуждали", "Поймал себя на мысли", "Спросил бы у тех, кто знает",
    "Нашёл спокойный вариант", "Вчера проверил", "Для сравнения", "Есть местная деталь", "Если смотреть проще",
    "Поделюсь находкой", "Нужен совет по месту", "Отмечу один нюанс", "Кажется, нашёл ответ",
    "У меня сработало", "Посмотрел варианты", "В продолжение темы", "Зашёл разговор",
    "Хочу свериться", "Наблюдение после недели", "Есть вопрос без срочности", "Собрал пару мыслей",
    "Оставлю здесь", "Похоже, пригодится", "Проверяю маршрут", "Небольшое уточнение",
    "Нашёл интересную связку", "По-человечески говоря", "Без лишней теории", "Заметил в чате",
    "Случайно выяснилось", "Пока разбирался", "Поправьте, если ошибся", "Есть опыт на эту тему",
    "Насколько понимаю", "Подскажите по живому опыту", "Может, кто-то сталкивался", "Соберу ответ здесь",
)
_OPENING_RIGHT = (
    "по району", "по маршруту", "по этому месту", "по местным вариантам", "по поездке", "по выходным",
    "по рабочему дню", "по семейному формату", "по воде", "по связи", "по ценам", "по времени",
    "по выбору", "по знакомым местам", "по формату", "по ближайшему плану", "по бытовой детали", "по этой идее",
    "по сегодняшней теме", "по тому, как принято здесь",
)
OPENINGS: tuple[str, ...] = tuple(f"{left} {right}" for left in _OPENING_LEFT for right in _OPENING_RIGHT)

_ENDING_LEFT = (
    "Как у вас", "Кто-нибудь уже", "Есть проверенный вариант", "Буду рад свериться", "Если знаете",
    "Интересно, что думаете", "Можно без спешки", "Поделитесь опытом", "Может, есть нюанс",
    "Буду благодарен за ориентир", "Что бы вы выбрали", "Как обычно делают местные", "Есть ли смысл",
    "Если не сложно", "Любой живой опыт подойдёт", "Можно коротко", "Буду иметь в виду",
    "Заранее спасибо", "Проверю и отпишусь", "Может пригодиться другим", "Куда бы вы пошли",
    "На что обратить внимание", "Что сработало у вас", "Есть ли рядом", "Кто знает точно",
)
_ENDING_RIGHT = (
    "в такой ситуации?", "для первого раза?", "на выходных?", "в этом районе?", "без машины?", "с детьми?",
    "если времени немного?", "для спокойного темпа?", "в сезон?", "рядом с центром?", "с похожим запросом?",
    "по собственному опыту?", "без лишних расходов?", "если хочется проще?", "для новичка?", "в ближайшие дни?",
    "если важна тишина?", "когда погода меняется?", "чтобы не ошибиться?", "если идти одному?",
)
ENDINGS: tuple[str, ...] = tuple(f"{left} {right}" for left in _ENDING_LEFT for right in _ENDING_RIGHT)

STRUCTURE_BLOCKS = ("greeting", "context", "observation", "question", "practical_value", "qualification", "soft_cta", "emotion")
STRUCTURE_LIBRARY: tuple[tuple[str, ...], ...] = tuple(
    __import__("itertools").islice(__import__("itertools").permutations(STRUCTURE_BLOCKS, 4), 1000)
)

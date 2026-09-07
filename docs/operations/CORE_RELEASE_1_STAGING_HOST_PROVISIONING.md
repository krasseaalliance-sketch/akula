# Release 1 «Ядро»: provisioning внешнего staging-хоста

**Статус: `WAITING FOR PAYMENT APPROVAL`**

Дата инвентаризации: 2026-09-07 (Asia/Krasnoyarsk).

## Целевой immutable release

- Tag: `core-r1-staging-rc1-2026-09-07`
- Commit: `e497f5152b204df74a065789aeb46542089bcb99`
- Alembic head: `0025_core_day4_production_evidence`
- Artifact SHA-256: `29C992720B7FD605977B323E93BDF5F10FC82192726E188A888FA059BDA5DE56`
- Приватный репозиторий: `https://github.com/krasseaalliance-sketch/akula`

Этот документ описывает подготовку инфраструктуры. Внешний staging не развёрнут, внешний E2E A/B/C не выполнялся.

## Инвентаризация доступных ресурсов

Инвентаризация выполнялась без создания, изменения или удаления ресурсов.

| Вариант | Отдельный от production | Docker | PostgreSQL | Redis | Storage | HTTPS/DNS | Подходит |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Локальный Docker Desktop на рабочей станции | Нет: локальный/shared-контур, не внешний | Да | Да, локальный | Да, локальный | Да, локальный MinIO/volumes | Нет публичного endpoint | Нет |
| GitHub private repository + Actions | Да, для исходников и CI | Нет runtime-хоста | Нет | Нет | Только CI artifact | Только сервис GitHub, не staging URL | Нет |
| Отдельный VPS/VM/cloud account | Не найден | Не подтверждён | Не подтверждён | Не подтверждён | Не подтверждён | Не подтверждён | Нет |
| Отдельный домен/subdomain и DNS-доступ | Не найден | — | — | — | — | Не подтверждён | Нет |

Проверены локально доступные средства: Docker Desktop, SSH-клиент, Git и конфигурация проекта. Авторизованных CLI/учётных данных для Hetzner, AWS, Azure, GCP, DigitalOcean, Fly.io, Railway, Vercel или другого внешнего hosting-провайдера не обнаружено. SSH-конфигурации с staging-хостом и staging-specific environment variables также нет.

Локальные контейнеры, включая PostgreSQL, Redis и MinIO, намеренно не рассматриваются как staging: они не дают публичный HTTPS URL и не являются внешним изолированным контуром.

## Рекомендуемый вариант без автоматического заказа

Один рекомендуемый вариант: **Hetzner Cloud CPX22**, регион **Germany (FSN/NBG)** или **Finland (HEL)**, Ubuntu LTS.

- 2 shared vCPU;
- 4 GB RAM;
- 80 GB NVMe;
- Docker Engine + Docker Compose;
- firewall: только `22`, `80`, `443`;
- SSH-ключ, password root-login отключён;
- ориентир текущей цены: **€19.49/месяц без VAT и без публичного IPv4**; IPv4, backup и дополнительные storage оплачиваются отдельно по тарифу провайдера.

Официальная таблица Hetzner указывает для CPX22 2 vCPU, 4 GB RAM и текущий monthly cap €19.49 без VAT для Germany/Finland: [Hetzner Cloud price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/). Спецификация 80 GB для CPX22 указана на странице [Hetzner Cloud Germany](https://www.hetzner.com/cloud-made-in-germany/).

Этой конфигурации достаточно для малонагруженного тестового Compose-контура Release 1: frontend, backend, PostgreSQL, Redis, reverse proxy и staging-only file storage на одном хосте. Это не sizing для production-трафика; после запуска обязательна проверка памяти/CPU и увеличение хоста при нехватке ресурсов.

Заказ, регистрация, оплата и создание VPS не выполнялись. Для начала работ нужно явное одобрение оплаты владельцем аккаунта. Отдельно потребуется свободный домен/поддомен и DNS-доступ владельца домена; production DNS изменять нельзя.

## Что будет создано после одобрения

1. Новый VPS в отдельном cloud project, не связанном с production.
2. Отдельный hostname вида `staging.<отдельный-домен>`; production-домен `human-interface.ru` не используется.
3. Отдельные staging-only PostgreSQL, Redis и file storage. В Compose используются отдельные именованные volumes; при необходимости file storage выносится в отдельный staging object-storage bucket.
4. Отдельный набор `STAGING_*` secrets, создаваемый только на staging-хосте. Значения не попадут в Git, CI output или этот документ.
5. Отдельные staging-логи и отдельная backup/rollback-точка.
6. Caddy с Let’s Encrypt для staging hostname, HTTP → HTTPS redirect и маркировкой `STAGING`/release tag в health/UI.

## Порядок provisioning и deployment

1. Создать VPS из Ubuntu LTS и включить firewall для `22`, `80`, `443`.
2. Добавить SSH public key, отключить парольный root-login, создать отдельного deploy-пользователя.
3. Создать DNS A/AAAA запись только для staging hostname и проверить, что production DNS не менялся.
4. Установить Docker Engine и Compose plugin.
5. Клонировать приватный репозиторий и checkout **только** `core-r1-staging-rc1-2026-09-07`.
6. Сверить `HEAD` с `e497f5152b204df74a065789aeb46542089bcb99` и SHA-256 release artifact.
7. До миграции создать backup target для staging PostgreSQL.
8. Заполнить `.env.staging` только на сервере отдельными `STAGING_*` values.
9. Выполнить `alembic upgrade head` только против staging DB, затем поднять Compose и проверить health.
10. Снаружи проверить HTTPS, `/scout/core`, `/core → 404`, запрет protected API без токена, изоляцию workspace и авторизацию при чтении файлов.

## Rollback

- До миграции сохранить staging DB backup и текущий image/tag manifest.
- Для rollback приложения остановить Compose, checkout предыдущего утверждённого staging tag/image, проверить checksum и поднять сервисы снова.
- Если миграция несовместима, остановить приложение, восстановить staging DB из backup в отдельную staging DB и повторить health/smoke checks.
- Production DB, storage, DNS, secrets и сервисы в rollback не участвуют.

## Production isolation

Подтверждено по текущей инвентаризации: production не затрагивался. Не выполнялись запросы, deployment, миграции, изменения DNS, изменения файлов, создание сервисов или операции storage на `human-interface.ru` и его инфраструктуре. Локальные ресурсы не использовались как внешний staging.

## Блокер и необходимое действие

Отсутствует: оплаченный или уже доступный отдельный внешний VPS/cloud project с публичным IP.

Нужен владелец/система: владелец cloud-аккаунта и платёжный доступ.

Минимально необходимое действие: явно одобрить заказ Hetzner Cloud CPX22 в FSN/NBG или HEL (2 vCPU, 4 GB, 80 GB) по ориентиру €19.49/месяц без VAT, после чего предоставить отдельный домен/subdomain и DNS-доступ для staging.

До этого момента статус остаётся `WAITING FOR PAYMENT APPROVAL`. После выдачи хоста следующим шагом будет только provisioning и внешняя техническая проверка; E2E A/B/C в этой задаче не выполняется.

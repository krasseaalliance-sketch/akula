# Core Release 1 — GitHub and external staging blocker

**Status:** `BLOCKED`

Отсутствует: авторизованный доступ к отдельному приватному GitHub-репозиторию
для `krasseaalliance-sketch/akula` и разрешение создать или подключить его к
этому workspace. Локальный `git remote` отсутствует, GitHub CLI не установлен,
а read-only запрос к `https://github.com/krasseaalliance-sketch/akula.git`
вернул `Repository not found`.

Нужен владелец/система: владелец GitHub-организации `krasseaalliance-sketch`
или назначенный GitHub-администратор с правом создать private repository,
добавить `origin`, принять push exact branch/tag и настроить repository
Actions/Secrets.

Минимально необходимое действие: предоставить безопасный GitHub access через
утверждённый механизм и подтвердить private repository URL. После этого можно
создать remote, проверить `.gitignore`, опубликовать только
`codex/core-r1-rc1-2026-09-07` и `core-r1-staging-rc1-2026-09-07`, а затем настроить
staging-only delivery. Секреты в workspace, коммит, логи и отчёт не передавать.

Production не затрагивался.

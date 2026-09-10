# Подключение ASmeT в MAX к Constructive

Интеграция принимает сообщения бота ASmeT из MAX и передаёт их в существующий
контур обработки Constructive. Реальный access token хранится только в секретном
хранилище окружения и не записывается в базу, аудит, логи или репозиторий.

## Переменные окружения

Заполнить на сервере:

```text
MAX_API_BASE_URL=https://platform-api2.max.ru
MAX_ASMET_ACCESS_TOKEN=<fresh-secret>
MAX_ASMET_ORGANIZATION_ID=<constructive-organization-id>
MAX_ASMET_CHAT_ID=<max-chat-id>
MAX_WEBHOOK_URL=https://<public-host>/api/constructive/asmet/max/webhook
MAX_WEBHOOK_SECRET=<random-webhook-secret>
```

`MAX_WEBHOOK_URL` должен быть публичным HTTPS URL на 443 порту. Не использовать
localhost или HTTP. `MAX_ASMET_CHAT_ID` ограничивает обработку сообщений только
назначенным рабочим чатом.

## Подключение

После входа Создателя вызвать авторизованный endpoint:

```text
POST /api/constructive/asmet/max/connect
Authorization: Bearer <creator-access-token>
```

Endpoint проверяет `/me`, убеждается, что учетная запись MAX является ботом, и
регистрирует подписку webhook на `message_created`, `message_edited` и
`bot_started`.

Входящий webhook проверяет заголовок `X-Max-Bot-Api-Secret`, фильтрует чат,
передаёт сообщение в `process_max_message` и пишет событие аудита. Повторная
доставка одного сообщения не создаёт повторную запись и повторное подтверждение.

## Безопасность и отключение

- Токен, webhook-secret и creator access token не помещать в `.env.example`, Git,
  issue, скриншоты или журнал
- Ранее опубликованный в чате токен считать скомпрометированным и отозвать в
  панели MAX; для сервера выпустить новый
- Для отключения удалить webhook-подписку в панели/через MAX API и убрать
  `MAX_ASMET_ACCESS_TOKEN` из серверного secret store
- Ошибка или неподписанный webhook не должны считаться успешно обработанным

Официальные методы MAX: [`/me`](https://dev.max.ru/docs-api/methods/GET/me),
[`/subscriptions`](https://dev.max.ru/docs-api/methods/POST/subscriptions) и
[`/messages`](https://dev.max.ru/docs-api/methods/POST/messages).

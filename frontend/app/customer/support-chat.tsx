"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api-client";

type SupportMessage = { id: string; sender_type: "CUSTOMER" | "OPERATOR"; content: string; created_at: string; telegram_status: string };
type ThreadResponse = { thread_id: string; campaign_id: string | null; topic_title: string | null; workspace: string; telegram: { configured: boolean; chat_id: string | null }; messages: SupportMessage[] };

export function SupportChat({ campaignId }: { campaignId?: string }) {
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [value, setValue] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [sending, setSending] = useState(false);
  const path = campaignId ? `/support/thread?campaign_id=${encodeURIComponent(campaignId)}` : "/support/thread";
  async function load() { const response = await apiFetch(path); if (!response.ok) { setState("error"); return; } setThread(await response.json() as ThreadResponse); setState("ready"); }
  useEffect(() => { void load(); }, [campaignId]);
  async function send(event: FormEvent) { event.preventDefault(); const content = value.trim(); if (!content || sending) return; setSending(true); const response = await apiFetch("/support/messages", { method: "POST", body: JSON.stringify({ content, campaign_id: campaignId ?? null }) }); if (response.ok) { setValue(""); await load(); } setSending(false); }
  return <section className="customer-panel support-chat" aria-labelledby="support-title"><div className="customer-panel-head"><div><p className="customer-kicker">ПОДДЕРЖКА</p><h2 id="support-title">Написать команде Scout</h2></div><span className="support-routing"><i /> {thread?.telegram.configured ? "Тема в Telegram" : "Внутренний чат"}</span></div><p className="support-description">Ваш диалог закреплён за этим кабинетом. В Telegram он попадёт в отдельную тему с вашим именем и ID кабинета.</p>{state === "loading" && <div className="support-empty">Загружаем диалог…</div>}{state === "error" && <div className="support-empty">Не удалось открыть поддержку. Обновите страницу.</div>}{state === "ready" && <><div className="support-messages" aria-live="polite">{thread?.messages.length ? thread.messages.map((message) => <div className={`support-message ${message.sender_type === "CUSTOMER" ? "customer" : "operator"}`} key={message.id}><div>{message.content}</div><time>{new Date(message.created_at).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}</time></div>) : <div className="support-empty">Здесь появится история вашего обращения.</div>}</div><form className="support-composer" onSubmit={send}><label htmlFor="support-message">Сообщение</label><div><textarea id="support-message" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Опишите вопрос или проблему" maxLength={4000} /><button className="customer-button customer-button-dark" disabled={sending || !value.trim()}>{sending ? "Отправляем…" : "Отправить"}</button></div><small>Не отправляйте пароли, коды подтверждения и ключи доступа.</small></form></>}</section>;
}

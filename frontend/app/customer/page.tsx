"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { strictApiFetch } from "../api-client";
import { appPath } from "../paths";
import { SupportChat } from "./support-chat";
import { ConstructiveView } from "../constructive-view";

type Campaign = { id: string; company: string; name: string; task: string; geography: string; understanding: { what_we_sell?: string[]; who_we_seek?: string[]; where?: string[] }; status: string; access_until: string | null };
type Opportunity = { id: string; title: string; summary: string; need: string; location?: string; budget?: string; appeared_at: string; freshness: number; why_matches: string; status: string };
type Overview = { organization: string; campaigns: Campaign[]; new_opportunities: number; in_work: number; skipped: number };
type Product = "scout" | "constructive";

const blank = { name: "", website: "", social_url: "", description: "", country: "Россия", region: "", demand: "", commercial_task: "", minimum_value: "" };
const demoCampaign: Campaign = { id: "demo-scout", company: "ООО «Север»", name: "Коммерческий монтаж", task: "Находим коммерческие объекты на монтаж и обслуживание инженерных систем.", geography: "Красноярск, Сибирь", understanding: { what_we_sell: ["монтаж инженерных систем"], who_we_seek: ["коммерческие объекты"], where: ["Красноярск"] }, status: "ACTIVE", access_until: null };
const demoOverview: Overview = { organization: "ООО «Север»", campaigns: [demoCampaign], new_opportunities: 3, in_work: 1, skipped: 8 };
const demoOpportunities: Opportunity[] = [
  { id: "demo-1", title: "Монтаж системы вентиляции", summary: "Коммерческий объект · исполнитель ещё не выбран", need: "Проектирование и монтаж", location: "Красноярск", budget: "2,4–3,1 млн ₽", appeared_at: "сегодня", freshness: 4, why_matches: "совпадает география и тип работ", status: "NEW" },
  { id: "demo-2", title: "Обслуживание инженерных систем", summary: "Производственное помещение · нужен подрядчик на сезон", need: "Регулярное обслуживание", location: "Сосновоборск", budget: "от 480 000 ₽", appeared_at: "вчера", freshness: 22, why_matches: "подходит минимальный бюджет", status: "NEW" },
  { id: "demo-3", title: "Автоматика для нового объекта", summary: "Строящийся объект · сроки согласуются", need: "Поставка и монтаж", location: "Красноярск", budget: "от 920 000 ₽", appeared_at: "вчера", freshness: 28, why_matches: "совпадает категория", status: "TAKEN" },
];
const emptyCampaign: Campaign = { id: "", company: "", name: "", task: "", geography: "", understanding: {}, status: "", access_until: null };
const emptyOverview: Overview = { organization: "", campaigns: [], new_opportunities: 0, in_work: 0, skipped: 0 };

export default function CustomerPage() {
  const initialProduct: Product = process.env.NEXT_PUBLIC_APP_PRODUCT === "constructive" ? "constructive" : "scout";
  const [product, setProduct] = useState<Product>(initialProduct);
  const [overview, setOverview] = useState<Overview>(emptyOverview);
  const [selected, setSelected] = useState<Campaign>(emptyCampaign);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [filter, setFilter] = useState("NEW");
  const [form, setForm] = useState(blank);
  const [message, setMessage] = useState("Демо-режим: покажем рабочее пространство до подключения API.");
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(true);

  async function load() {
    try {
      const response = await Promise.race([
        strictApiFetch("/customer/overview"),
        new Promise<Response>((_, reject) => window.setTimeout(() => reject(new Error("overview timeout")), 1800)),
      ]);
      if (response.status === 401) {
        window.location.assign(appPath("/login"));
        return;
      }
      if (!response.ok) throw new Error("overview unavailable");
      const data = await response.json() as Overview;
      const campaign = data.campaigns[0] ?? emptyCampaign;
      setOverview(data); setSelected(campaign); setDemo(false); setMessage("");
      if (campaign?.id) {
        const feed = await strictApiFetch(`/customer/campaigns/${campaign.id}/opportunities`);
        if (feed.ok) { const payload = await feed.json() as { opportunities?: Opportunity[] }; setOpportunities(payload.opportunities ?? []); }
      }
    } catch { setDemo(false); setOverview(emptyOverview); setSelected(emptyCampaign); setOpportunities([]); setMessage("Scout сейчас не может получить рабочие данные с сервера."); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    if (initialProduct === "constructive") {
      setLoading(false);
      return;
    }
    void load();
  }, [initialProduct]);

  async function onboard(event: FormEvent) {
    event.preventDefault(); setMessage("Настраиваем профиль поиска…");
    try {
      const response = await strictApiFetch("/customer/onboarding", { method: "POST", body: JSON.stringify({ ...form, minimum_value: form.minimum_value ? Number(form.minimum_value) : null }) });
      setMessage(response.ok ? "Компания добавлена. Проверьте профиль поиска." : "Не получилось сохранить компанию.");
      if (response.ok) { setForm(blank); await load(); }
    } catch { setMessage("Не удалось связаться с кабинетом. Проверьте подключение."); }
  }
  async function feedback(id: string, action: "TAKE" | "SKIP") {
    setOpportunities((rows) => rows.map((row) => row.id === id ? { ...row, status: action === "TAKE" ? "TAKEN" : "SKIPPED" } : row));
    setMessage(action === "TAKE" ? "Возможность добавлена в работу." : "Возможность скрыта из новых.");
    if (!demo) await strictApiFetch(`/customer/opportunities/${id}/feedback`, { method: "POST", body: JSON.stringify({ action }) });
  }

  const visibleOpportunities = useMemo(() => opportunities.filter((item) => filter === "ALL" || (filter === "NEW" && item.status === "NEW") || (filter === "TAKEN" && item.status === "TAKEN") || (filter === "SKIPPED" && item.status === "SKIPPED") || (filter === "CONTACT" && item.status === "CONTACT")), [filter, opportunities]);
  const isConstructive = product === "constructive";
  if (!loading && !isConstructive && (!overview.organization || !selected.id)) return <main className="customer-app cabinet-shell"><div className="cabinet-wrap"><div className="cabinet-page-heading"><div><p className="cabinet-kicker">SCOUT / WORKSPACE</p><h1>Рабочие данные<br />не загружены</h1><p>{message || "В вашем аккаунте пока нет подключённого Scout-профиля."}</p></div></div><a className="cabinet-primary-action" href={appPath("/login")}>Повторить вход</a></div></main>;
  if (loading) return <main className="customer-app cabinet-shell"><div className="customer-loading">Открываем рабочее пространство…</div></main>;

  return <main className={`customer-app cabinet-shell ${isConstructive ? "constructive-app" : ""}`}>
    <aside className="cabinet-sidebar" aria-label="Навигация кабинета">
      <a href={isConstructive ? "/constructive/" : "/"} className="cabinet-brand"><span className="cabinet-brand-mark">{isConstructive ? "AS" : "LH"}</span><span><strong>{isConstructive ? "ASmeT" : "LEADHUNTER"}</strong><small>{isConstructive ? "CONSTRUCTIVE" : "WORKSPACE"}</small></span></a>
      <div className="cabinet-product-label">{isConstructive ? "РАБОЧЕЕ ПРОСТРАНСТВО" : "ПРОДУКТЫ"}</div>
      {isConstructive ? <div className="cabinet-product-switcher"><button className="active" type="button"><span className="cabinet-product-icon constructive">C</span><span><strong>Constructive</strong><small>Контроль объектов</small></span></button></div> : <div className="cabinet-product-switcher"><button className={product === "scout" ? "active" : ""} type="button" onClick={() => setProduct("scout")}><span className="cabinet-product-icon scout">S</span><span><strong>Scout</strong><small>Поиск возможностей</small></span></button><button className={isConstructive ? "active" : ""} type="button" onClick={() => setProduct("constructive")}><span className="cabinet-product-icon constructive">C</span><span><strong>Constructive</strong><small>Контроль объектов</small></span></button></div>}
      <div className="cabinet-nav-label">КАБИНЕТ</div>
      <nav className="cabinet-nav"><button className="active" type="button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}><span>01</span>Обзор</button><button type="button" onClick={() => setMessage("Новых уведомлений: 3") }><span>02</span>Уведомления <b>3</b></button><button type="button" onClick={() => setMessage("Раздел компании открывается в настройках профиля.")}><span>03</span>Компания</button><button type="button" onClick={() => setMessage("Пользователи доступны владельцу кабинета.")}><span>04</span>Пользователи</button><button type="button" onClick={() => setMessage("Оплата теста — 25 000 ₽. Подключение через менеджера.")}><span>05</span>Оплата</button><button type="button" onClick={() => setMessage("Настройки профиля поиска доступны в карточке Scout.")}><span>06</span>Настройки</button></nav>
      <div className="cabinet-sidebar-foot"><span className="cabinet-live-dot" /><div><strong>{isConstructive ? "ASmeT" : "Scout active"}</strong><small>{isConstructive ? "рабочее пространство активно" : "синхронизация включена"}</small></div></div>
    </aside>
    <div className="cabinet-main"><header className="cabinet-topbar">{!isConstructive && <div className="cabinet-top-actions"><span className="cabinet-org">{overview.organization}</span><button className="cabinet-icon-button" type="button" aria-label="Уведомления" onClick={() => setMessage("Новых уведомлений: 3")}>◌<i /></button><a className="cabinet-avatar" href="/constructive/login" aria-label="Профиль">AS</a></div>}</header>
      {product === "constructive" ? <ConstructiveView /> : <div className="cabinet-wrap"><div className="cabinet-page-heading"><div><p className="cabinet-kicker">SCOUT / РАБОЧИЙ ЭКРАН</p><h1>Новые возможности</h1><p>Scout уже ищет подходящие заказы для {overview.organization.toLowerCase()}.</p></div><div className="cabinet-heading-status"><span className="cabinet-live-dot" /> ACTIVE<br /><small>DAY 2 / 5</small></div></div>{message && <div className={`cabinet-message ${demo ? "is-demo" : ""}`} role="status">{message}</div>}
        <section className="scout-status-row"><div><span className="cabinet-kicker">SCOUT SEARCHING...</span><strong>Поиск активен</strong><small>первые 5 дней работы Scout бесплатны · только подходящие возможности</small></div><div className="scout-progress"><span><b>02</b> / 05 день теста</span><i><em /></i></div></section>
        <section className="scout-metrics"><Metric label="Новые сегодня" value={overview.new_opportunities} accent /><Metric label="Подходят" value={overview.in_work + 2} /><Metric label="Отфильтровано" value={overview.skipped} /><Metric label="Контакты" value={1} /><Metric label="Потенциал" value="—" /><Metric label="Работает" value="31 ч" /></section>
        <div className="scout-layout"><section className="cabinet-panel scout-feed"><div className="cabinet-panel-head"><div><p className="cabinet-kicker">РАБОЧАЯ ЛЕНТА</p><h2>Новые возможности</h2></div><span className="cabinet-count">{visibleOpportunities.length} / {opportunities.length}</span></div><div className="scout-filters">{[["NEW", "Новые"], ["TAKEN", "Подходят"], ["CONTACT", "На проверке"], ["SKIPPED", "Архив"], ["ALL", "Все"]].map(([value, label]) => <button className={filter === value ? "active" : ""} type="button" key={value} onClick={() => setFilter(value)}>{label}</button>)}</div>{visibleOpportunities.length ? <div className="scout-opportunities">{visibleOpportunities.map((opportunity) => <OpportunityCard key={opportunity.id} opportunity={opportunity} onFeedback={feedback} />)}</div> : <div className="cabinet-empty"><strong>В этой вкладке пока пусто.</strong><span>Scout продолжает искать и обновит ленту автоматически.</span></div>}</section>
          <aside className="scout-rail"><section className="cabinet-panel scout-profile"><div className="cabinet-panel-head"><div><p className="cabinet-kicker">ПРОФИЛЬ ПОИСКА</p><h2>{selected.company}</h2></div><button type="button" className="cabinet-quiet-action" onClick={() => setMessage("Профиль поиска можно изменить через поддержку.")}>Изменить</button></div><p>{selected.task}</p><dl><div><dt>ГЕОГРАФИЯ</dt><dd>{selected.geography || "Красноярск"}</dd></div><div><dt>КАТЕГОРИИ</dt><dd>{selected.understanding.what_we_sell?.join(", ") || "инженерные работы"}</dd></div><div><dt>МИНИМАЛЬНЫЙ БЮДЖЕТ</dt><dd>от 400 000 ₽</dd></div></dl></section><section className="cabinet-panel scout-activity"><div className="cabinet-panel-head"><div><p className="cabinet-kicker">ПОСЛЕДНИЕ СОБЫТИЯ</p><h2>Активность Scout</h2></div></div>{["Новая возможность подходит профилю", "Контакт передан в кабинет", "Фильтр географии применён", "Профиль поиска обновлён"].map((item, index) => <div className="scout-activity-row" key={item}><span className={index === 0 ? "is-live" : ""} /> <div><strong>{item}</strong><small>{index === 0 ? "сейчас" : `${index + 1} ч. назад`}</small></div></div>)}</section></aside></div>
        <section className="cabinet-panel scout-onboarding" id="new-campaign"><div><p className="cabinet-kicker">НАСТРОИТЬ ЕЩЁ ОДИН ПОИСК</p><h2>Расскажите, что искать.</h2><p>Обычными словами. Scout уточнит детали и начнёт фильтровать возможности под ваш бизнес.</p></div><form onSubmit={onboard} className="scout-form">{[["name", "Название компании"], ["region", "Город или регион"], ["demand", "Какие клиенты нужны?"], ["minimum_value", "Минимальная сумма заказа"]].map(([key, label]) => <label key={key}>{label}<input value={form[key as keyof typeof form]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} required={key === "name" || key === "demand"} /></label>)}<label className="scout-form-wide">Коротко о задаче<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label><button className="cabinet-primary-action" type="submit">Добавить поиск</button></form></section><SupportChat campaignId={selected.id} /></div>}</div>
    <nav className="cabinet-mobile-nav" aria-label="Мобильная навигация"><button className="active" type="button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>⌂<span>Обзор</span></button>{!isConstructive && <button type="button" onClick={() => setProduct("scout")}>S<span>Scout</span></button>}{!isConstructive && <button type="button" onClick={() => setProduct("constructive")}>C<span>Constructive</span></button>}<button type="button" onClick={() => setMessage("Новых уведомлений: 3")}>◌<span>События</span></button></nav>
  </main>;
}

function Metric({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) { return <article className={`scout-metric ${accent ? "accent" : ""}`}><small>{label}</small><strong>{value}</strong></article>; }
function OpportunityCard({ opportunity, onFeedback }: { opportunity: Opportunity; onFeedback: (id: string, action: "TAKE" | "SKIP") => void }) { const fresh = opportunity.freshness < 24 ? "Свежая возможность" : `${opportunity.freshness} ч. назад`; return <article className={`scout-opportunity ${opportunity.status !== "NEW" ? "acted" : ""}`}><div className="scout-opportunity-top"><span className="fresh">{fresh}</span><span>{opportunity.location ?? "Удалённо"}</span></div><h3>{opportunity.title}</h3><p>{opportunity.summary}</p><div className="scout-need"><small>ЧТО НУЖНО</small><strong>{opportunity.need}</strong></div><div className="scout-opportunity-meta"><span><small>БЮДЖЕТ</small><b>{opportunity.budget ?? "Уточняется"}</b></span><span><small>ПОЧЕМУ ПОДХОДИТ</small><b>{opportunity.why_matches}</b></span></div>{opportunity.status === "NEW" ? <div className="scout-opportunity-actions"><button className="cabinet-primary-action" type="button" onClick={() => onFeedback(opportunity.id, "TAKE")}>В работу</button><button className="cabinet-secondary-action" type="button" onClick={() => onFeedback(opportunity.id, "SKIP")}>Не подходит</button></div> : <span className="scout-acted">{opportunity.status === "TAKEN" ? "В РАБОТЕ" : "В АРХИВЕ"}</span>}</article>; }

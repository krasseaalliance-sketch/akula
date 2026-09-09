"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { strictApiFetch } from "./api-client";
import { appPath } from "./paths";

type Organization = { id: string; name: string; role: string };
type ConstructiveObject = { id: string; name: string; address: string | null; status: string };
type Employee = { id: string; full_name: string; role: string; telegram_username: string | null };
type Warehouse = { id: string; name: string; address: string | null; status: string };
type Rate = { id: string; work_type: string; amount: number; currency: string };
type LedgerRow = { id: string; source_message_id: string | null; work_date: string; work_type: string; quantity: number; rate: number; amount: number; raw_line: string };
type CabinetData = { organization: Organization[]; objects: ConstructiveObject[]; employees: Employee[]; warehouses: Warehouse[]; rates: Rate[]; ledger: LedgerRow[] };
type AsmetMessage = { id: string; external_message_id: string; text: string; status: string; historical: boolean; rejections: Array<{ reason?: string }>; created_at: string };

const sections = ["Обзор", "Объекты", "Сотрудники", "Склады", "Журнал", "ASmeT"] as const;
type Section = (typeof sections)[number];

function money(value: number) {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)} ₽`;
}

export function ConstructiveView() {
  const [data, setData] = useState<CabinetData | null>(null);
  const [messages, setMessages] = useState<AsmetMessage[]>([]);
  const [section, setSection] = useState<Section>("Обзор");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await strictApiFetch("/constructive/cabinets/me");
      if (response.status === 401) {
        window.location.assign(appPath("/login"));
        return;
      }
      if (!response.ok) throw new Error("CABINET_UNAVAILABLE");
      const payload = await response.json() as CabinetData;
      setData(payload);
      const history = await strictApiFetch(`/constructive/asmet?organization_id=${encodeURIComponent(payload.organization[0]?.id ?? "")}`);
      if (history.ok) setMessages((await history.json() as { messages: AsmetMessage[] }).messages);
    } catch {
      setError("Рабочий кабинет недоступен. Проверьте соединение с сервером.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const organization = data?.organization[0];
  const totalAmount = useMemo(() => data?.ledger.reduce((sum, row) => sum + row.amount, 0) ?? 0, [data]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!organization || !question.trim()) return;
    setNotice("");
    const response = await strictApiFetch("/constructive/asmet/query", { method: "POST", body: JSON.stringify({ organization_id: organization.id, question }) });
    if (!response.ok) { setNotice("ASmeT не смог обработать запрос."); return; }
    const payload = await response.json() as { answer: string };
    setAnswer(payload.answer);
  }

  async function inviteMaster(event: FormEvent) {
    event.preventDefault();
    if (!organization) return;
    setNotice("Создаём персональное приглашение…");
    const response = await strictApiFetch("/constructive/cabinets/master-invite", { method: "POST", body: JSON.stringify({ organization_id: organization.id, name: inviteName, email: inviteEmail }) });
    if (!response.ok) { setNotice("Не удалось создать приглашение."); return; }
    const payload = await response.json() as { url: string };
    setInviteUrl(payload.url);
    setNotice("Приглашение создано и записано в приватную доставку ASmeT.");
    setInviteName("");
    setInviteEmail("");
  }

  if (loading) return <main className="customer-app cabinet-shell"><div className="customer-loading">Открываем рабочее пространство…</div></main>;
  if (error || !data || !organization) return <main className="customer-app cabinet-shell"><div className="cabinet-wrap"><div className="cabinet-message" role="alert">{error || "Организация не назначена."}</div><button className="cabinet-primary-action" type="button" onClick={() => void load()}>Повторить</button></div></main>;

  return (
    <main className="customer-app cabinet-shell constructive-app">
      <aside className="cabinet-sidebar" aria-label="Навигация кабинета">
        <a href={appPath("/")} className="cabinet-brand"><span className="cabinet-brand-mark">AS</span><span><strong>ASmeT</strong><small>CONSTRUCTIVE</small></span></a>
        <div className="cabinet-product-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <div className="cabinet-product-switcher"><button className="active" type="button"><span className="cabinet-product-icon constructive">C</span><span><strong>Constructive</strong><small>Контроль объектов</small></span></button></div>
        <div className="cabinet-nav-label">КАБИНЕТ</div>
        <nav className="cabinet-nav">{sections.map((item, index) => <button className={section === item ? "active" : ""} type="button" key={item} onClick={() => setSection(item)}><span>{String(index + 1).padStart(2, "0")}</span>{item}</button>)}</nav>
      </aside>
      <div className="cabinet-main">
        <header className="cabinet-topbar"><div className="cabinet-top-actions"><span className="cabinet-org">{organization.name} / {organization.role}</span><span className="cabinet-live-dot" /><span className="cabinet-avatar">{organization.role.slice(0, 2)}</span></div></header>
        <div className="cabinet-wrap">
          <div className="cabinet-page-heading constructive-heading"><div><p className="cabinet-kicker">CONSTRUCTIVE / РАБОЧИЙ КОНТУР</p><h1>Личный кабинет</h1><p>Контроль доступа, команды и рабочих данных.</p></div><div className="constructive-date"><span className="cabinet-live-dot" /> СЕССИЯ АКТИВНА<br /><small>{organization.role}</small></div></div>
          {notice && <div className="cabinet-message" role="status">{notice}</div>}
          {section === "Обзор" && <Overview data={data} totalAmount={totalAmount} onInvite={inviteMaster} inviteName={inviteName} inviteEmail={inviteEmail} setInviteName={setInviteName} setInviteEmail={setInviteEmail} inviteUrl={inviteUrl} />}
          {section === "Объекты" && <EntityList title="Объекты" items={data.objects.map((item) => ({ title: item.name, detail: item.address || "Адрес не указан", status: item.status }))} empty="Назначенных объектов нет." />}
          {section === "Сотрудники" && <EntityList title="Сотрудники" items={data.employees.map((item) => ({ title: item.full_name, detail: item.telegram_username ? `MAX / @${item.telegram_username}` : "MAX-профиль не привязан", status: item.role }))} empty="Сотрудников в доступной области нет." />}
          {section === "Склады" && <EntityList title="Склады" items={data.warehouses.map((item) => ({ title: item.name, detail: item.address || "Адрес не указан", status: item.status }))} empty="Складов в доступной области нет." />}
          {section === "Журнал" && <Ledger data={data} />}
          {section === "ASmeT" && <Asmet messages={messages} question={question} setQuestion={setQuestion} answer={answer} ask={ask} />}
        </div>
      </div>
    </main>
  );
}

function Overview({ data, totalAmount, onInvite, inviteName, inviteEmail, setInviteName, setInviteEmail, inviteUrl }: { data: CabinetData; totalAmount: number; onInvite: (event: FormEvent) => void; inviteName: string; inviteEmail: string; setInviteName: (value: string) => void; setInviteEmail: (value: string) => void; inviteUrl: string }) {
  const creator = data.organization[0]?.role === "CREATOR";
  return <>
    <section className="constructive-role-hero"><div><p className="cabinet-kicker">ТЕКУЩАЯ РОЛЬ</p><h2>{data.organization[0]?.role === "CREATOR" ? "Создатель" : data.organization[0]?.role}</h2><p>Доступ к данным определяется ролью и назначенной организацией.</p></div><div className="constructive-role-mark" aria-hidden="true">C</div></section>
    <section className="constructive-access-summary"><div><p className="cabinet-kicker">ДОСТУП ПОДТВЕРЖДЁН</p><h2>{data.organization[0]?.name}</h2><p>Роль: {data.organization[0]?.role}. Все показатели ниже загружены из кабинета.</p></div><div className="constructive-access-stat"><strong>{data.objects.length}</strong><span>объектов</span></div></section>
    <div className="constructive-overview-grid"><section className="constructive-panel"><div className="constructive-section-head"><h2>Сводка</h2><span className="constructive-count">ASmeT / LIVE DATA</span></div><div className="constructive-cabinet-grid"><div className="constructive-stat-card"><strong>{data.ledger.length}</strong><span>строк журнала</span></div><div className="constructive-stat-card"><strong>{money(totalAmount)}</strong><span>начислено</span></div><div className="constructive-stat-card"><strong>{data.employees.length}</strong><span>сотрудников</span></div><div className="constructive-stat-card"><strong>{data.warehouses.length}</strong><span>складов</span></div></div></section>
      {creator ? <section className="constructive-panel"><div className="constructive-section-head"><h2>Кабинет Master</h2><span className="constructive-count">ONE-TIME LINK</span></div><p className="constructive-muted">Создайте персональную ссылку. Она будет записана для приватной отправки ASmeT и станет недействительной после регистрации.</p><form className="scout-form" onSubmit={onInvite}><label>Имя Master<input value={inviteName} onChange={(event) => setInviteName(event.target.value)} required /></label><label>Email<input type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} required /></label><button className="cabinet-primary-action" type="submit">Создать приглашение</button></form>{inviteUrl && <p className="constructive-muted">Ссылка: <a href={inviteUrl}>{inviteUrl}</a></p>}</section> : <section className="constructive-panel"><div className="constructive-section-head"><h2>Роль</h2></div><p className="constructive-muted">Вы видите только назначенные организации, объекты, сотрудников и строки журнала.</p></section>}
    </div>
  </>;
}

function EntityList({ title, items, empty }: { title: string; items: Array<{ title: string; detail: string; status: string }>; empty: string }) {
  return <section className="constructive-panel"><div className="constructive-section-head"><h2>{title}</h2><span className="constructive-count">{items.length} записей</span></div>{items.length ? <div className="constructive-list">{items.map((item) => <div key={`${item.title}-${item.status}`}><strong>{item.title}</strong><span>{item.detail}</span><em className="constructive-status">{item.status}</em></div>)}</div> : <EmptyState text={empty} />}</section>;
}

function Ledger({ data }: { data: CabinetData }) {
  return <section className="constructive-panel"><div className="constructive-section-head"><h2>Журнал работ</h2><span className="constructive-count">{data.ledger.length} строк</span></div>{data.ledger.length ? <div className="constructive-list">{data.ledger.map((row) => <div key={row.id}><strong>{row.work_type} · {row.quantity}</strong><span>{new Date(row.work_date).toLocaleDateString("ru-RU")} · {money(row.amount)}</span><em className="constructive-status">Подтверждено</em></div>)}</div> : <EmptyState text="Распознанных строк работ пока нет." />}</section>;
}

function Asmet({ messages, question, setQuestion, answer, ask }: { messages: AsmetMessage[]; question: string; setQuestion: (value: string) => void; answer: string; ask: (event: FormEvent) => void }) {
  return <div className="constructive-overview-grid"><section className="constructive-panel"><div className="constructive-section-head"><h2>Запрос ASmeT</h2><span className="constructive-count">РОЛЬ С УЧЁТОМ ДОСТУПА</span></div><form className="scout-form" onSubmit={ask}><label className="scout-form-wide">Вопрос<textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Например: сколько начислено?" required /></label><button className="cabinet-primary-action" type="submit">Получить ответ</button></form>{answer && <div className="cabinet-message" role="status">{answer}</div>}</section><section className="constructive-panel"><div className="constructive-section-head"><h2>История</h2><span className="constructive-count">{messages.length} сообщений</span></div>{messages.length ? <div className="constructive-list">{messages.map((message) => <div key={message.id}><strong>{message.status} · {message.external_message_id}</strong><span>{message.text}</span>{message.rejections.length > 0 && <em className="constructive-status">Причины: {message.rejections.map((item) => item.reason).join(", ")}</em>}</div>)}</div> : <EmptyState text="Сообщений ASmeT в доступной истории нет." />}</section></div>;
}

function EmptyState({ text }: { text: string }) { return <div className="constructive-empty" role="status"><strong>Нет данных</strong><span>{text}</span></div>; }

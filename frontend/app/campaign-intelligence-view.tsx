"use client";

import { useCallback, useEffect, useState } from "react";

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type Campaign = { id: string; name: string; objective: string; status: string };
type TopCommunity = { id: string; title: string; score: number; lead_probability: number; recommendation: string; reason: string; collections: string[] };
type Dashboard = { campaign: Campaign; audience: { summary: string | null; segments: string[]; goal: string }; communities_found: number; communities_analyzed: number; average_score: number; top_communities: TopCommunity[]; prepared_messages: number; ai_cost: number; projected_reach: number; collection_distribution: Record<string, number>; economics: { analysis_cost: number; cost_per_lead: number; cost_per_publication: number; cost_per_successful_application: number }; learning: { leads: number; responses: number; converted: number } };

const goals = ["Получить заявки", "Получить подписчиков", "Найти попутчиков", "Продать услугу", "Пригласить на мероприятие"];

export function CampaignIntelligenceView({ apiFetch, onAction }: { apiFetch: ApiFetch; onAction: (message: string) => void }) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [offer, setOffer] = useState("");
  const [audience, setAudience] = useState("");
  const [geography, setGeography] = useState("");
  const [languages, setLanguages] = useState("ru");
  const [budget, setBudget] = useState("0");
  const [platforms, setPlatforms] = useState("TELEGRAM");
  const [goal, setGoal] = useState(goals[0]);

  const load = useCallback(async (campaignId?: string) => {
    setState("loading");
    try {
      const response = await apiFetch("/campaigns");
      if (!response.ok) throw new Error("Campaigns API failed");
      const rows = await response.json() as Campaign[];
      setCampaigns(rows);
      const nextId = campaignId ?? selectedId ?? rows[0]?.id ?? "";
      setSelectedId(nextId);
      if (nextId) {
        const dashboardResponse = await apiFetch(`/campaign-intelligence/campaigns/${nextId}/dashboard`);
        if (dashboardResponse.ok) setDashboard(await dashboardResponse.json() as Dashboard);
      }
      setState("ready");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Campaign Intelligence request failed"); setState("error"); }
  }, [apiFetch, selectedId]);
  useEffect(() => { void load(); }, [load]);

  async function createWizardCampaign() {
    if (!offer || !audience) return;
    setBusy(true); setError("");
    try {
      const workspaceResponse = await apiFetch("/workspaces");
      const workspaces = await workspaceResponse.json() as Array<{ id: string }>;
      const response = await apiFetch("/campaign-intelligence/wizard", { method: "POST", body: JSON.stringify({ workspace_id: workspaces[0]?.id, offer, audience, geography: geography || null, languages: languages.split(",").map((item) => item.trim()).filter(Boolean), budget: Number(budget) || 0, platforms: platforms.split(",").map((item) => item.trim()).filter(Boolean), goal, use_llm: true }) });
      if (!response.ok) throw new Error((await response.json().catch(() => null) as { detail?: string } | null)?.detail ?? "Campaign Wizard failed");
      const result = await response.json() as { campaign: Campaign };
      setOffer(""); setAudience(""); await load(result.campaign.id); onAction("Campaign profile created from Wizard");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Campaign Wizard failed"); } finally { setBusy(false); }
  }

  async function analyze() {
    if (!selectedId) return;
    setBusy(true); setError("");
    try { const response = await apiFetch(`/campaign-intelligence/campaigns/${selectedId}/analyze`, { method: "POST", body: JSON.stringify({ use_llm: true }) }); if (!response.ok) throw new Error("Campaign analysis failed"); setDashboard(await response.json() as Dashboard); onAction("Audience, community scores and recommendations updated"); } catch (cause) { setError(cause instanceof Error ? cause.message : "Campaign analysis failed"); } finally { setBusy(false); }
  }

  async function learn() {
    if (!selectedId) return;
    setBusy(true);
    try { const response = await apiFetch(`/campaign-intelligence/campaigns/${selectedId}/learn`, { method: "POST", body: JSON.stringify({}) }); onAction(response.ok ? "Campaign learning snapshot recorded" : "Learning snapshot failed"); if (response.ok) await load(selectedId); } finally { setBusy(false); }
  }

  return <section className="campaign-intelligence-view"><div className="page-head intelligence-head"><div><p className="eyebrow">НАСТРОЙКА КАМПАНИИ · АНАЛИТИКА СПРОСА</p><h2>Находим нужную аудиторию, а не просто чаты</h2><p className="subtitle">Кампания → аудитория → намерение → поиск → оценка → стратегия сообщения → план публикации.</p></div><button className="button button-primary" disabled={busy || !selectedId} onClick={() => void analyze()}>{busy ? "Анализируем…" : "Анализировать аудиторию"}</button></div><div className="campaign-intelligence-grid"><article className="panel campaign-wizard"><div className="panel-head"><div><p className="eyebrow">МАСТЕР КАМПАНИИ</p><h3>Расскажите, чего хотите достичь</h3></div><span className="badge badge-green">Сначала аудитория</span></div><div className="wizard-fields"><label>Что вы предлагаете?<input value={offer} onChange={(event) => setOffer(event.target.value)} placeholder="Поездка на север Бали" /></label><label>Кому это может быть интересно?<textarea value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Путешественники, экспаты, любители природы…" rows={3} /></label><label>Где?<input value={geography} onChange={(event) => setGeography(event.target.value)} placeholder="Бали, Убуд, Чангу" /></label><div className="wizard-two"><label>Языки<input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="ru, en" /></label><label>Бюджет<input value={budget} onChange={(event) => setBudget(event.target.value)} inputMode="decimal" placeholder="0" /></label></div><div className="wizard-two"><label>Площадки<input value={platforms} onChange={(event) => setPlatforms(event.target.value)} placeholder="TELEGRAM" /></label><label>Цель<select value={goal} onChange={(event) => setGoal(event.target.value)}>{goals.map((item) => <option key={item}>{item}</option>)}</select></label></div></div><button className="button button-primary" disabled={busy || !offer || !audience} onClick={() => void createWizardCampaign()}>Собрать профиль кампании</button></article><article className="panel campaign-list-panel"><div className="panel-head"><div><p className="eyebrow">АКТИВНЫЕ КАМПАНИИ</p><h3>Выберите кампанию</h3></div></div>{campaigns.length === 0 ? <p className="telegram-muted">Профилей кампаний пока нет. Ответьте на вопросы, чтобы создать первый.</p> : campaigns.slice(0, 8).map((campaign) => <button className={`campaign-intelligence-row ${selectedId === campaign.id ? "selected" : ""}`} key={campaign.id} onClick={() => { setSelectedId(campaign.id); void load(campaign.id); }}><span className="campaign-icon">◎</span><span><strong>{campaign.name}</strong><small>{campaign.objective} · {campaign.status}</small></span></button>)}</article></div>{error && <div className="telegram-error" role="alert">{error}</div>}{state === "loading" && <div className="panel" role="status">Загружаем аналитику кампании…</div>}{state === "error" && <div className="panel" role="alert">Данные кампании временно недоступны.</div>}{state === "ready" && dashboard && <CampaignDashboard dashboard={dashboard} onLearn={learn} busy={busy} />}</section>;
}

function CampaignDashboard({ dashboard, onLearn, busy }: { dashboard: Dashboard; onLearn: () => void; busy: boolean }) {
  return <div className="campaign-dashboard"><div className="metric-grid campaign-intelligence-metrics"><article className="metric-card"><span>Найдено сообществ</span><strong>{dashboard.communities_found}</strong><small className="green">Смысловой поиск</small></article><article className="metric-card"><span>Средняя оценка</span><strong>{Math.round(dashboard.average_score)}</strong><small className="green">0–100</small></article><article className="metric-card"><span>Прогноз охвата</span><strong>{dashboard.projected_reach.toLocaleString()}</strong><small className="amber">Лучшие рекомендации</small></article><article className="metric-card"><span>Стоимость анализа</span><strong>${dashboard.ai_cost.toFixed(2)}</strong><small className="amber">Учёт расходов</small></article></div><div className="dashboard-grid"><article className="panel"><div className="panel-head"><div><p className="eyebrow">АНАЛИТИКА АУДИТОРИИ</p><h3>{dashboard.audience.summary || "Профиль аудитории"}</h3></div><button className="button button-secondary" disabled={busy} onClick={onLearn}>Обновить знания кампании</button></div><div className="tag-row">{dashboard.audience.segments.map((segment) => <span className="badge badge-neutral" key={segment}>{segment}</span>)}</div><div className="campaign-economics"><span>Лиды <strong>{dashboard.learning.leads}</strong></span><span>Ответы <strong>{dashboard.learning.responses}</strong></span><span>Конверсии <strong>{dashboard.learning.converted}</strong></span><span>Подготовлено сообщений <strong>{dashboard.prepared_messages}</strong></span></div></article><article className="panel"><div className="panel-head"><div><p className="eyebrow">ПОДБОРКИ</p><h3>Распределение аудитории</h3></div></div><div className="stage31-collection-list">{Object.entries(dashboard.collection_distribution).sort(([, left], [, right]) => right - left).slice(0, 8).map(([slug, count]) => <div className="stage31-collection" key={slug}><div><strong>{slug}</strong><small>Подходящие сообщества</small></div><span className="badge badge-neutral">{count}</span></div>)}</div></article></div><article className="panel campaign-top-communities"><div className="panel-head"><div><p className="eyebrow">РЕКОМЕНДАЦИЯ СИСТЕМЫ</p><h3>Начните с этих сообществ</h3></div><span className="badge badge-green">Топ {Math.min(15, dashboard.top_communities.length)}</span></div>{dashboard.top_communities.length === 0 ? <p className="telegram-muted">Запустите анализ, чтобы получить список сообществ.</p> : dashboard.top_communities.map((community) => <div className="campaign-score-row" key={community.id}><div className="campaign-score-title"><strong>{community.title}</strong><small>{community.collections.join(" · ") || "без категории"}</small></div><span className="score score-emphasis">{Math.round(community.score)}</span><span className="badge badge-neutral">Вероятность лида: {Math.round(community.lead_probability)}%</span><span className={`badge ${community.recommendation === "PUBLISH" ? "badge-green" : community.recommendation === "REVIEW" ? "badge-amber" : "badge-red"}`}>{community.recommendation}</span><p>{community.reason}</p></div>)}</article><div className="campaign-cost-strip"><span>Анализ ${dashboard.economics.analysis_cost.toFixed(2)}</span><span>За лид ${dashboard.economics.cost_per_lead.toFixed(2)}</span><span>За публикацию ${dashboard.economics.cost_per_publication.toFixed(2)}</span><span>За успешную заявку ${dashboard.economics.cost_per_successful_application.toFixed(2)}</span></div></div>;
}

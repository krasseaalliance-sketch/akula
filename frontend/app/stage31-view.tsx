"use client";

import { useCallback, useEffect, useState } from "react";

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type Collection = { id: string; name: string; slug: string; parent_id?: string | null; chat_count: number; member_count: number; lead_count: number; active_campaign_count: number };
type WritingRun = { run: { id: string; persona_id: string; provider: string; naturalness_score?: number }; selected?: { content: string; similarity_score?: number }; variant_count: number; operator_visible_variants: number };
type Persona = { id: string; name: string };

export function Stage31View({ apiFetch, workspaceId, onAction }: { apiFetch: ApiFetch; workspaceId: string; onAction: (message: string) => void }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [runs, setRuns] = useState<WritingRun[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const load = useCallback(async () => {
    setState("loading");
    try {
      const [dashboardResponse, runsResponse, personasResponse] = await Promise.all([apiFetch("/community-collections/dashboard"), apiFetch("/human-writing/runs"), apiFetch("/human-writing/personas")]);
      if (!dashboardResponse.ok || !runsResponse.ok || !personasResponse.ok) throw new Error("Stage 3.1 API failed");
      setCollections(await dashboardResponse.json() as Collection[]);
      setRuns(await runsResponse.json() as WritingRun[]);
      setPersonas(await personasResponse.json() as Persona[]);
      setState("ready");
    } catch { setState("error"); }
  }, [apiFetch]);
  useEffect(() => { void load(); }, [load]);
  async function classify() {
    if (!workspaceId) return;
    setBusy(true);
    try {
      const response = await apiFetch("/community-collections/classify", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) });
      onAction(response.ok ? "Community classification completed" : "Community classification failed");
      if (response.ok) await load();
    } finally { setBusy(false); }
  }
  const bali = collections.find((collection) => collection.slug === "bali");
  const latest = runs[0];
  return <section className="stage31-stack">
    <div className="panel stage31-hero"><div><p className="eyebrow">STAGE 3.1 · COMMUNITY INTELLIGENCE</p><h3>Collections stay organized after every sync</h3><p>Automatic region, category, tags and subcategory assignment. Manual operator decisions remain authoritative.</p></div><button className="button button-primary" disabled={busy || !workspaceId} onClick={() => void classify()}>{busy ? "Classifying…" : "Classify workspace"}</button></div>
    {state === "loading" && <div className="panel" role="status">Loading classification dashboard…</div>}
    {state === "error" && <div className="panel stage31-error" role="alert">Stage 3.1 data is temporarily unavailable. <button className="text-button" onClick={() => void load()}>Retry</button></div>}
    {state === "ready" && <>
      <div className="stage31-metrics"><article className="metric-card"><span>Bali chats</span><strong>{bali?.chat_count ?? 0}</strong><small className="green">Auto-assigned</small></article><article className="metric-card"><span>Bali members</span><strong>{bali?.member_count ?? 0}</strong><small className="green">When available</small></article><article className="metric-card"><span>Leads in Bali</span><strong>{bali?.lead_count ?? 0}</strong><small className="amber">Source communities</small></article><article className="metric-card"><span>Active campaigns</span><strong>{bali?.active_campaign_count ?? 0}</strong><small className="amber">Collection scope</small></article></div>
      <div className="dashboard-grid"><article className="panel"><div className="panel-head"><div><p className="eyebrow">SYSTEM COLLECTIONS</p><h3>Community Collections</h3></div><button className="text-button" onClick={() => void load()}>Refresh ↻</button></div><div className="stage31-collection-list">{collections.filter((collection) => !collection.parent_id).map((collection) => <div className="stage31-collection" key={collection.id}><div><strong>{collection.name}</strong><small>{collection.chat_count} chats · {collection.member_count} members</small></div><span className="badge badge-neutral">{collection.lead_count} leads</span></div>)}</div></article><article className="panel"><div className="panel-head"><div><p className="eyebrow">HUMAN WRITING ENGINE</p><h3>Operator sees the selected draft</h3></div><span className="badge badge-green">{personas.length} personas</span></div>{latest?.selected ? <div className="stage31-draft"><div className="stage31-draft-meta"><span className="badge badge-green">{Math.round(latest.run.naturalness_score ?? 0)} naturalness</span><span className="badge badge-neutral">{latest.variant_count} generated · {latest.operator_visible_variants} visible</span></div><p>{latest.selected.content}</p><small>{latest.run.provider} · {latest.run.persona_id} · similarity {Math.round((latest.selected.similarity_score ?? 0) * 100)}%</small></div> : <p className="telegram-muted">No generated draft yet. Drafts created by the message workflow will appear here with only the best variant exposed to the operator.</p>}</article></div>
    </>}
  </section>;
}

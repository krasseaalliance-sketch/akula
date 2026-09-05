"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type Workspace = { id: string; name: string };
type Account = { id: string; display_name: string; username: string | null };
type Progress = { total: number; reviewed: number; remaining: number; skipped: number; needs_context: number; in_review: number; batches_remaining: number; batch_size: number };
type Suggestion = { type: string; confidence: number; collection_slugs: string[]; tag_slugs: string[] };
type Decision = { review_status: string; manual_dialog_type: string; manual_eligibility: string; operator_notes: string | null; needs_context_reason: string | null; version: number; manual_override: boolean; collection_slugs: string[]; tag_slugs: string[] };
type DialogCard = { id: string; number: number | null; title: string; username: string | null; entity_type: string; avatar_url: string | null; member_count: number | null; last_message_at: string | null; message_preview: { text: string; sent_at: string; sender: string | null }[]; current_automatic_tags: string[]; current_automatic_collections: string[]; suggestion: Suggestion; decision: Decision };
type Collection = { id: string; name: string; slug: string; is_system: boolean };
type Draft = { review_status: "REVIEWED" | "SKIPPED" | "NEEDS_CONTEXT"; manual_dialog_type: string; manual_eligibility: string; operator_notes: string; needs_context_reason: string; collection_slugs: string[]; tag_slugs: string[]; version: number };
type Completion = { complete: boolean; total_dialogs: number; processed_dialogs: number; remaining: number; community_dataset: number; personal: number; bots: number; channels: number; groups: number; service: number; unknown: number };

const types = ["PERSON", "GROUP", "SUPERGROUP", "CHANNEL", "BOT", "SAVED_MESSAGES", "SERVICE", "UNKNOWN"];
const eligibilities = ["ELIGIBLE", "READ_ONLY", "NOT_ELIGIBLE", "MANUAL_REVIEW"];
const statuses = ["REVIEWED", "SKIPPED", "NEEDS_CONTEXT"] as const;
const batchOptions = [10, 20, 30, 50, 100];

function csvValues(value: string) { return value.split(",").map((item) => item.trim()).filter(Boolean); }

export function DialogTriageView({ apiFetch, onAction }: { apiFetch: ApiFetch; onAction: (message: string) => void }) {
  const [workspaceId, setWorkspaceId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [cards, setCards] = useState<DialogCard[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [collections, setCollections] = useState<Collection[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [batchSize, setBatchSize] = useState(30);
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkAction, setBulkAction] = useState("MARK_PERSONAL");
  const [bulkCollection, setBulkCollection] = useState("bali");
  const [bulkTag, setBulkTag] = useState("manual-review");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [filterType, setFilterType] = useState("ALL");
  const [filterCollection, setFilterCollection] = useState("ALL");
  const [filterUsername, setFilterUsername] = useState("");
  const [showReviewed, setShowReviewed] = useState(false);
  const [reviewedRows, setReviewedRows] = useState<Array<{ id: string; dialog_id: string; title: string; review_status: string; manual_dialog_type: string; manual_eligibility: string; collection_slugs: string[]; version: number }>>([]);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [completion, setCompletion] = useState<Completion | null>(null);

  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await apiFetch(path, init);
    if (!response.ok) throw new Error((await response.json().catch(() => null) as { detail?: string } | null)?.detail ?? "Dialog triage request failed");
    return response.json() as Promise<unknown>;
  }, [apiFetch]);

  const query = useMemo(() => `workspace_id=${encodeURIComponent(workspaceId)}&account_id=${encodeURIComponent(accountId)}`, [workspaceId, accountId]);

  const refreshProgress = useCallback(async () => {
    if (!workspaceId || !accountId) return;
    setProgress(await request(`/dialog-triage/progress?${query}&batch_size=${batchSize}`) as Progress);
  }, [accountId, batchSize, query, request, workspaceId]);

  const loadBatch = useCallback(async (size = batchSize) => {
    if (!workspaceId || !accountId) return;
    const response = await request(`/dialog-triage/next-batch?${query}&limit=${size}`) as { dialogs: DialogCard[]; progress: Progress; completion?: Completion };
    setCards(response.dialogs);
    setCompletion(response.completion ?? null);
    setActiveCardId(response.dialogs[0]?.id ?? null);
    setDrafts(Object.fromEntries(response.dialogs.map((card) => [card.id, {
      review_status: "REVIEWED",
      manual_dialog_type: card.suggestion.type,
      manual_eligibility: card.suggestion.type === "PERSON" || card.suggestion.type === "BOT" ? "NOT_ELIGIBLE" : "MANUAL_REVIEW",
      operator_notes: card.decision.operator_notes ?? "",
      needs_context_reason: card.decision.needs_context_reason ?? "",
      collection_slugs: card.decision.collection_slugs,
      tag_slugs: card.decision.tag_slugs,
      version: card.decision.version,
    }])));
    setSelected([]);
    setProgress(response.progress);
  }, [accountId, batchSize, query, request, workspaceId]);

  const visibleCards = useMemo(() => cards.filter((card) => {
    const typeMatch = filterType === "ALL" || card.entity_type === filterType || card.suggestion.type === filterType;
    const collectionMatch = filterCollection === "ALL" || card.current_automatic_collections.includes(filterCollection) || card.decision.collection_slugs.includes(filterCollection);
    const usernameMatch = !filterUsername.trim() || (card.username ?? "").toLowerCase().includes(filterUsername.trim().toLowerCase());
    return typeMatch && collectionMatch && usernameMatch;
  }), [cards, filterCollection, filterType, filterUsername]);

  const loadReviewed = useCallback(async () => {
    setReviewedRows(await request(`/dialog-triage/reviewed?${query}&limit=200`) as Array<{ id: string; dialog_id: string; title: string; review_status: string; manual_dialog_type: string; manual_eligibility: string; collection_slugs: string[]; version: number }>);
  }, [query, request]);

  const bootstrap = useCallback(async () => {
    try {
      setError("");
      const [workspaces, accountRows] = await Promise.all([request("/workspaces") as Promise<Workspace[]>, request("/integrations/telegram/accounts") as Promise<Account[]>]);
      const workspace = workspaces[0];
      const account = accountRows.find((row) => row.username === "Alexey_Mifanyuk") ?? accountRows[0];
      setAccounts(accountRows);
      if (workspace) setWorkspaceId(workspace.id);
      if (account) setAccountId(account.id);
      if (workspace && account) {
        setCollections(await request(`/dialog-triage/collections?workspace_id=${encodeURIComponent(workspace.id)}`) as Collection[]);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load triage context"); }
  }, [request]);

  useEffect(() => { void bootstrap(); }, [bootstrap]);
  useEffect(() => { if (workspaceId && accountId) void loadBatch(); }, [accountId, loadBatch, workspaceId]);

  function updateDraft(id: string, patch: Partial<Draft>) { setDrafts((current) => ({ ...current, [id]: { ...current[id], ...patch } })); }
  function toggleSelected(id: string) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  function toggleAll() { setSelected(selected.length === visibleCards.length ? [] : visibleCards.map((item) => item.id)); }

  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Dialog triage request failed"); } finally { setBusy(false); }
  }

  function saveBatch(advance: boolean) {
    void run(async () => {
      const decisions = cards.map((card) => ({ dialog_id: card.id, expected_version: drafts[card.id].version || undefined, ...drafts[card.id] }));
      const result = await request(`/dialog-triage/batch?${query}&limit=${batchSize}`, { method: "POST", body: JSON.stringify({ decisions, advance }) }) as { next_batch?: { dialogs: DialogCard[]; progress: Progress; completion?: Completion }; progress: Progress; completion?: Completion; downstream?: { communities_updated: number; campaign_scores_refreshed: number } };
      if (advance && result.next_batch) {
        setCards(result.next_batch.dialogs);
        setCompletion(result.completion ?? result.next_batch.completion ?? null);
        setActiveCardId(result.next_batch.dialogs[0]?.id ?? null);
        setProgress(result.next_batch.progress);
        setDrafts(Object.fromEntries(result.next_batch.dialogs.map((card) => [card.id, {
          review_status: "REVIEWED", manual_dialog_type: card.suggestion.type, manual_eligibility: card.suggestion.type === "PERSON" || card.suggestion.type === "BOT" ? "NOT_ELIGIBLE" : "MANUAL_REVIEW", operator_notes: "", needs_context_reason: "", collection_slugs: [], tag_slugs: [], version: card.decision.version,
        }])));
      } else { await loadBatch(); }
      const refreshNote = result.downstream ? ` Dataset ${result.downstream.communities_updated} · scores ${result.downstream.campaign_scores_refreshed}` : "";
      onAction(advance ? `Batch saved; next dialogs loaded${refreshNote}` : `Batch saved${refreshNote}`);
    });
  }

  function doBulkAction() {
    if (!selected.length) return;
    if (!window.confirm(`Apply ${bulkAction} to ${selected.length} selected dialogs? This is an explicit manual decision.`)) return;
    void run(async () => {
      await request(`/dialog-triage/bulk-action?${query}`, { method: "POST", body: JSON.stringify({ dialog_ids: selected, action: bulkAction, collection_slug: ["ADD_COLLECTION", "REMOVE_COLLECTION"].includes(bulkAction) ? bulkCollection : undefined, tag_slug: ["ADD_TAG", "REMOVE_TAG"].includes(bulkAction) ? bulkTag : undefined, confirm_overwrite: false }) });
      await loadBatch();
      onAction(`${selected.length} dialogs updated`);
    });
  }

  function returnToQueue(row: { dialog_id: string; version: number }) {
    void run(async () => {
      await request(`/dialog-triage/${row.dialog_id}/return-to-queue?${query}`, { method: "POST", body: JSON.stringify({ expected_version: row.version, reason: "Returned from Reviewed" }) });
      await loadReviewed();
      await loadBatch();
      onAction("Dialog returned to the triage queue");
    });
  }

  useEffect(() => {
    const typeShortcuts: Record<string, string> = { "1": "PERSON", "2": "GROUP", "3": "SUPERGROUP", "4": "CHANNEL", "5": "BOT", "6": "SERVICE", "7": "UNKNOWN" };
    const collectionShortcuts: Record<string, string> = { b: "bali", g: "georgia", k: "krasnoyarsk", t: "thailand", y: "yoga", e: "expats", r: "relocation", q: "online-quizzes", d: "digital", n: "real-estate", p: "travel" };
    const handler = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        if (!busy && cards.length) saveBatch(true);
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      const activeId = activeCardId ?? visibleCards[0]?.id;
      if (!activeId || showReviewed) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        const currentIndex = Math.max(0, visibleCards.findIndex((card) => card.id === activeId));
        const nextIndex = event.key === "ArrowDown" ? Math.min(visibleCards.length - 1, currentIndex + 1) : Math.max(0, currentIndex - 1);
        setActiveCardId(visibleCards[nextIndex]?.id ?? activeId);
        event.preventDefault();
        return;
      }
      if (event.code === "Space") {
        setSelected((current) => event.shiftKey ? (current.includes(activeId) ? current.filter((id) => id !== activeId) : [...current, activeId]) : [activeId]);
        event.preventDefault();
        return;
      }
      const shortcut = event.key.toLowerCase();
      const dialogType = typeShortcuts[event.key];
      if (dialogType) {
        const ids = selected.length ? selected : [activeId];
        ids.forEach((id) => updateDraft(id, { manual_dialog_type: dialogType }));
        event.preventDefault();
      } else if (collectionShortcuts[shortcut]) {
        const ids = selected.length ? selected : [activeId];
        ids.forEach((id) => setDrafts((current) => ({ ...current, [id]: { ...current[id], collection_slugs: Array.from(new Set([...(current[id]?.collection_slugs ?? []), collectionShortcuts[shortcut]]) ) } })));
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeCardId, batchSize, busy, cards.length, drafts, saveBatch, selected, showReviewed, visibleCards]);

  return <section className="dialog-triage-view">
    <div className="dialog-triage-hero"><div><p className="eyebrow">STAGE 3.2.2 · INTERACTIVE OPERATOR REVIEW</p><h2>Interactive dialog review</h2><p>Система сама открывает следующий пакет, сохраняет решения оператора и обновляет downstream-индексы без Telegram writes.</p></div><div className="dialog-triage-lock"><strong>TELEGRAM SEND OFF</strong><small>No joins · no writes · no publications</small></div></div>
    {error && <div className="telegram-error" role="alert">{error}</div>}
    <div className="dialog-triage-toolbar"><label>Account<select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label>Batch size<select value={batchSize} onChange={(event) => { const next = Number(event.target.value); setBatchSize(next); void run(async () => { await loadBatch(next); }); }}>{batchOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label><label>Type<select value={filterType} onChange={(event) => setFilterType(event.target.value)}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label>Collection<select value={filterCollection} onChange={(event) => setFilterCollection(event.target.value)}><option value="ALL">All collections</option>{collections.map((collection) => <option key={collection.slug} value={collection.slug}>{collection.name}</option>)}</select></label><label>Username<input value={filterUsername} onChange={(event) => setFilterUsername(event.target.value)} placeholder="Search username" /></label><button className="button button-secondary" disabled={busy || !visibleCards.length} onClick={toggleAll}>{selected.length === visibleCards.length ? "Clear selection" : "Select visible"}</button><button className="button button-secondary" disabled={busy} onClick={() => void run(async () => loadBatch())}>Refresh batch</button><button className="button button-secondary" disabled={busy} onClick={() => void run(async () => { await loadReviewed(); setShowReviewed(true); })}>Reviewed</button></div>
    {progress && <div className="dialog-triage-progress"><div><span>Total</span><strong>{progress.total}</strong></div><div><span>Reviewed / total</span><strong>{progress.reviewed} / {progress.total}</strong></div><div><span>Remaining</span><strong>{progress.remaining}</strong></div><div><span>Skipped</span><strong>{progress.skipped}</strong></div><div><span>Context</span><strong>{progress.needs_context}</strong></div><div className="dialog-triage-progress-wide"><span>Approx. batches remaining</span><strong>{progress.batches_remaining}</strong></div></div>}
    <div className="dialog-triage-hotkeys" aria-label="Keyboard shortcuts"><strong>Hotkeys</strong><span>1–7 type</span><span>B/G/K/T/Y/E/R/Q/D/N/P collections</span><span>Space select</span><span>Shift+Space multi-select</span><span>Ctrl+Enter save & next</span></div>
    {showReviewed && <div className="panel dialog-triage-reviewed"><div className="dialog-triage-reviewed-head"><strong>Reviewed dialogs</strong><button className="button button-secondary" onClick={() => setShowReviewed(false)}>Back to queue</button></div>{reviewedRows.length === 0 ? <p>No reviewed dialogs yet.</p> : reviewedRows.map((row) => <div className="dialog-triage-reviewed-row" key={row.id}><span><strong>{row.title}</strong><small>{row.review_status} · {row.manual_dialog_type} · {row.manual_eligibility} · {row.collection_slugs.join(", ") || "no collections"}</small></span><button className="button button-secondary" disabled={busy} onClick={() => returnToQueue(row)}>Return to queue</button></div>)}</div>}
    <div className="dialog-triage-actions" style={{ display: showReviewed ? "none" : undefined }}><div className="dialog-triage-selection"><strong>{selected.length} selected</strong><span>Bulk action never overwrites a saved decision without explicit confirmation.</span></div><select aria-label="Bulk action" value={bulkAction} onChange={(event) => setBulkAction(event.target.value)}><option value="MARK_PERSONAL">Mark personal</option><option value="MARK_BOT">Mark bot</option><option value="EXCLUDE_CAMPAIGNS">Exclude from campaigns</option><option value="ADD_COLLECTION">Add to collection</option><option value="REMOVE_COLLECTION">Remove from collection</option><option value="ADD_TAG">Add tag</option><option value="REMOVE_TAG">Remove tag</option><option value="SKIP">Decide later</option><option value="NEEDS_CONTEXT">Needs context</option></select>{["ADD_COLLECTION", "REMOVE_COLLECTION"].includes(bulkAction) && <select aria-label="Bulk collection" value={bulkCollection} onChange={(event) => setBulkCollection(event.target.value)}>{collections.map((collection) => <option key={collection.slug} value={collection.slug}>{collection.name}</option>)}</select>}{["ADD_TAG", "REMOVE_TAG"].includes(bulkAction) && <input aria-label="Bulk tag" value={bulkTag} onChange={(event) => setBulkTag(event.target.value)} placeholder="tag-slug" />}{<button className="button button-secondary" disabled={busy || !selected.length} onClick={doBulkAction}>Apply to selected</button>}</div>
    {completion ? <div className="panel dialog-triage-complete" role="status"><p className="eyebrow">REVIEW COMPLETE</p><h3>Разобрано {completion.processed_dialogs} диалогов.</h3><p>Очередь аккаунта полностью обработана. Downstream-индексы обновлены без Telegram writes.</p><div className="dialog-triage-complete-grid"><div><span>Community Dataset</span><strong>{completion.community_dataset}</strong></div><div><span>Личные переписки</span><strong>{completion.personal}</strong></div><div><span>Боты</span><strong>{completion.bots}</strong></div><div><span>Каналы</span><strong>{completion.channels}</strong></div><div><span>Группы</span><strong>{completion.groups}</strong></div></div><button className="button button-secondary" onClick={() => { setCompletion(null); void run(async () => { await loadReviewed(); setShowReviewed(true); }); }}>Open Reviewed</button></div> : cards.length === 0 ? <div className="panel dialog-triage-empty" role="status"><p className="eyebrow">QUEUE CLEAR</p><h3>All available dialogs are reviewed</h3><p>There are no UNREVIEWED dialogs in this account. Use Reviewed to return a dialog to the queue if needed.</p></div> : <div className="dialog-triage-list" style={{ display: showReviewed ? "none" : undefined }}>{visibleCards.map((card) => { const draft = drafts[card.id]; return <article className={`panel dialog-triage-card ${selected.includes(card.id) ? "selected" : ""} ${activeCardId === card.id ? "active" : ""}`} key={card.id} tabIndex={0} onFocus={() => setActiveCardId(card.id)} onClick={() => setActiveCardId(card.id)}><div className="dialog-triage-card-head"><div className="dialog-triage-avatar">{card.avatar_url ? <img src={card.avatar_url} alt="" /> : <span>{card.title.slice(0, 1).toUpperCase()}</span>}</div><label className="dialog-check"><input type="checkbox" checked={selected.includes(card.id)} onChange={() => toggleSelected(card.id)} /><span>#{card.number}</span></label><div className="dialog-triage-ident"><strong>{card.title}</strong><small>{card.username ? `@${card.username}` : "No username"} · metadata: {card.entity_type} · {card.member_count ?? "—"} members</small></div><span className="badge badge-amber">AI hint: {card.suggestion.type} · {Math.round(card.suggestion.confidence * 100)}%</span></div><div className="dialog-triage-card-body"><div className="dialog-triage-meta"><span>Last activity</span><strong>{card.last_message_at ? new Date(card.last_message_at).toLocaleString() : "Not available"}</strong>{card.message_preview[0] && <small>“{card.message_preview[0].text}”</small>}<small>Current collections: {card.current_automatic_collections.join(", ") || "none"}</small><small>AI tags: {card.current_automatic_tags.join(", ") || "none"}</small></div><div className="dialog-triage-fields"><label>Status<select value={draft.review_status} onChange={(event) => updateDraft(card.id, { review_status: event.target.value as Draft["review_status"] })}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label><label>Manual type<select value={draft.manual_dialog_type} onChange={(event) => updateDraft(card.id, { manual_dialog_type: event.target.value })}>{types.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label>Eligibility<select value={draft.manual_eligibility} onChange={(event) => updateDraft(card.id, { manual_eligibility: event.target.value })}>{eligibilities.map((eligibility) => <option key={eligibility} value={eligibility}>{eligibility}</option>)}</select></label><label>Collections<select multiple size={3} value={draft.collection_slugs} onChange={(event) => updateDraft(card.id, { collection_slugs: Array.from(event.target.selectedOptions, (option) => option.value) })}>{collections.map((collection) => <option key={collection.slug} value={collection.slug}>{collection.name}</option>)}</select></label><label>Tags<input value={draft.tag_slugs.join(", ")} onChange={(event) => updateDraft(card.id, { tag_slugs: csvValues(event.target.value) })} placeholder="bali, personal" /></label><label>Notes<input value={draft.operator_notes} onChange={(event) => updateDraft(card.id, { operator_notes: event.target.value })} placeholder="Operator note" /></label>{draft.review_status === "NEEDS_CONTEXT" && <label>Context reason<input value={draft.needs_context_reason} onChange={(event) => updateDraft(card.id, { needs_context_reason: event.target.value })} placeholder="What must be checked?" /></label>}</div></div></article>; })}</div>}
    <div className="dialog-triage-footer" style={{ display: showReviewed ? "none" : undefined }}><button className="button button-secondary" disabled={busy || !cards.length} onClick={() => saveBatch(false)}>Save without advancing</button><button className="button button-primary" disabled={busy || !cards.length} onClick={() => saveBatch(true)}>Save and show next {batchSize}</button></div>
  </section>;
}

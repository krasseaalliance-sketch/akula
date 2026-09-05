"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type Account = { id: string; display_name: string; username: string | null; phone_masked: string | null; authorization_status: string; safety_status: string; connection_status: string; manual_unlock_required: boolean; safety_lock: boolean };
type Dialog = { id: string; title: string; external_dialog_id: string; dialog_type: string; username: string | null; is_public: boolean; is_joined: boolean; can_send_messages: boolean; can_view_history: boolean; has_slow_mode: boolean; slow_mode_seconds: number | null; member_count: number | null; community_id: string | null };
type Row = Record<string, unknown>;
type Tab = "Accounts" | "Dialogs" | "Discovery" | "Rules" | "Messages" | "Incidents" | "Safety";

const tabs: Tab[] = ["Accounts", "Dialogs", "Discovery", "Rules", "Messages", "Incidents", "Safety"];

export function TelegramView({ apiFetch, onAction }: { apiFetch: ApiFetch; onAction: (message: string) => void }) {
  const [tab, setTab] = useState<Tab>("Accounts");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [dialogs, setDialogs] = useState<Dialog[]>([]);
  const [candidates, setCandidates] = useState<Row[]>([]);
  const [incidents, setIncidents] = useState<Row[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedAccount, setSelectedAccount] = useState("");
  const [phone, setPhone] = useState("+79991234567");
  const [code, setCode] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [query, setQuery] = useState("Бали попутчики");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const account = useMemo(() => accounts.find((item) => item.id === selectedAccount) ?? accounts[0], [accounts, selectedAccount]);
  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await apiFetch(path, init);
    if (!response.ok) throw new Error((await response.json().catch(() => null) as { detail?: string } | null)?.detail ?? "Telegram API request failed");
    return response.json() as Promise<unknown>;
  }, [apiFetch]);
  const refresh = useCallback(async () => {
    try {
      setError("");
      const [accountRows, workspaces] = await Promise.all([request("/integrations/telegram/accounts"), request("/workspaces")]);
      setAccounts(accountRows as Account[]);
      const nextWorkspace = (workspaces as Row[])[0]?.id;
      if (typeof nextWorkspace === "string") setWorkspaceId(nextWorkspace);
      const nextAccount = (accountRows as Account[]).find((item) => item.id === selectedAccount) ?? (accountRows as Account[])[0];
      if (nextAccount) {
        setSelectedAccount(nextAccount.id);
        setDialogs(await request(`/integrations/telegram/dialogs?account_id=${nextAccount.id}`) as Dialog[]);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Telegram API request failed"); }
  }, [request, selectedAccount]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Telegram action failed"); } finally { setBusy(false); }
  }
  function selectAccount(id: string) { setSelectedAccount(id); void run(async () => { setDialogs(await request(`/integrations/telegram/dialogs?account_id=${id}`) as Dialog[]); }); }
  function createMockAccount() { void run(async () => { await request("/integrations/telegram/accounts", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, display_name: "Telegram mock account", phone }) }); await refresh(); onAction("Mock Telegram account created"); }); }
  function startAuth() { if (!account) return; void run(async () => { const response = await request(`/integrations/telegram/accounts/${account.id}/authorize/start`, { method: "POST", body: JSON.stringify({ phone }) }) as { attempt_id: string }; setAttemptId(response.attempt_id); onAction("Authorization code requested; it is never stored"); }); }
  function verifyAuth() { if (!account || !attemptId || !code) return; void run(async () => { await request(`/integrations/telegram/accounts/${account.id}/authorize/code`, { method: "POST", body: JSON.stringify({ attempt_id: attemptId, code }) }); setCode(""); await refresh(); onAction("Telegram mock account authorized"); }); }
  function syncDialogs() { if (!account) return; void run(async () => { setDialogs(await request("/integrations/telegram/dialogs/sync", { method: "POST", body: JSON.stringify({ account_id: account.id }) }) as Dialog[]); onAction("Dialogs synchronized without auto-joining"); }); }
  function discover() { if (!account) return; void run(async () => { setCandidates(await request("/integrations/telegram/discovery/run", { method: "POST", body: JSON.stringify({ account_id: account.id, query }) }) as Row[]); setTab("Discovery"); }); }
  function syncMessages(dialog: Dialog) { if (!account) return; void run(async () => { await request("/integrations/telegram/messages/sync", { method: "POST", body: JSON.stringify({ account_id: account.id, dialog_id: dialog.id, max_messages: 100 }) }); setTab("Messages"); onAction(`Messages synced for ${dialog.title}`); }); }
  function lock() { if (!account) return; void run(async () => { await request(`/integrations/telegram/accounts/${account.id}/safety-lock`, { method: "POST", body: JSON.stringify({ reason: "Manual review from Safety Center" }) }); await refresh(); setTab("Safety"); }); }
  function unlock() { if (!account) return; void run(async () => { await request(`/integrations/telegram/accounts/${account.id}/unlock`, { method: "POST" }); await refresh(); onAction("Manual unlock recorded"); }); }

  return <section className="telegram-console">
    <div className="telegram-hero"><div><p className="eyebrow">TELEGRAM ENGINE · MOCK-FIRST</p><h2>Telegram operations</h2><p>Communities → messages → leads → approved publications, with account safety visible at every step.</p></div><div className="telegram-hero-status"><span className="status-dot" /><strong>DRY_RUN</strong><small>Real connect and send disabled</small></div></div>
    <div className="telegram-tabs" role="tablist" aria-label="Telegram sections">{tabs.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "telegram-tab active" : "telegram-tab"} onClick={() => setTab(item)}>{item}</button>)}</div>
    {error && <div className="telegram-error" role="alert">{error}</div>}
    {tab === "Accounts" && <div className="telegram-grid"><article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">ACCOUNT MANAGEMENT</p><h3>Workspace accounts</h3></div><button className="button button-primary" disabled={busy || !workspaceId} onClick={createMockAccount}>+ Mock account</button></div>{accounts.length === 0 && <p className="telegram-muted">No Telegram accounts yet. Create a mock account to run the safe authorization flow.</p>}{accounts.map((item) => <button key={item.id} className={`telegram-account-row ${account?.id === item.id ? "selected" : ""}`} onClick={() => selectAccount(item.id)}><span className="telegram-account-mark">TG</span><span><strong>{item.display_name}</strong><small>{item.username ? `@${item.username}` : item.phone_masked ?? "Phone not configured"}</small></span><BadgeText value={item.authorization_status} tone={item.authorization_status === "AUTHORIZED" ? "green" : "amber"} /><BadgeText value={item.safety_status} tone={item.manual_unlock_required ? "red" : "green"} /></button>)}</article><article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">AUTHORIZATION WIZARD</p><h3>{account?.display_name ?? "Select an account"}</h3></div>{account && <BadgeText value={account.connection_status} tone={account.connection_status === "CONNECTED" ? "green" : "amber"} />}</div>{account ? <><label className="telegram-field">Phone number<input value={phone} onChange={(event) => setPhone(event.target.value)} inputMode="tel" /></label><div className="telegram-actions"><button className="button button-secondary" disabled={busy} onClick={startAuth}>1. Send code</button><input aria-label="Authorization code" className="telegram-code" placeholder="Code" value={code} onChange={(event) => setCode(event.target.value)} /><button className="button button-primary" disabled={busy || !attemptId || !code} onClick={verifyAuth}>2. Verify</button></div><p className="telegram-hint">Mock code: <code>12345</code>. The code and 2FA password are never persisted.</p><div className="telegram-safety-note"><strong>Safety boundary</strong><span>Session reference only · no session string in API/frontend · no automatic account rotation.</span></div></> : <p className="telegram-muted">Choose an account to start authorization.</p>}</article></div>}
    {tab === "Dialogs" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">AVAILABLE TO ACCOUNT</p><h3>Telegram dialogs</h3></div><button className="button button-secondary" disabled={busy || !account} onClick={syncDialogs}>Sync dialogs</button></div><div className="telegram-table">{dialogs.map((item) => <div className="telegram-table-row" key={item.id}><div><strong>{item.title}</strong><small>{item.username ? `@${item.username}` : item.external_dialog_id} · {item.dialog_type}</small></div><span>{item.is_public ? "Public" : "Private"}</span><span>{item.can_send_messages ? "Can post" : "Read only"}</span><span>{item.has_slow_mode ? `Slow ${item.slow_mode_seconds}s` : "No slow mode"}</span><button className="text-button" onClick={() => syncMessages(item)}>Sync messages</button></div>)}</div></article>}
    {tab === "Discovery" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">NO AUTO-JOIN</p><h3>Community discovery</h3></div><div className="telegram-actions"><input className="telegram-search" aria-label="Discovery query" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="button button-primary" disabled={busy || !account} onClick={discover}>Run search</button></div></div><div className="telegram-candidate-grid">{candidates.map((item) => <div className="telegram-candidate" key={String(item.id)}><BadgeText value={String(item.review_status)} tone={item.review_status === "NEW" ? "amber" : "green"} /><strong>{String(item.title)}</strong><small>{String(item.reason ?? "")}</small><span>{Math.round(Number(item.relevance_score ?? 0) * 100)} relevance · no automatic join</span></div>)}</div></article>}
    {tab === "Rules" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">HUMAN REVIEW</p><h3>Rules and permissions</h3></div><BadgeText value="Permission never auto-created" tone="amber" /></div><p className="telegram-muted">Import and rules analysis produce evidence only. A CommunityPermission is created or reactivated only after an explicit operator approval.</p><div className="telegram-rule-list">{dialogs.filter((item) => item.community_id).map((item) => <div className="telegram-table-row" key={item.id}><div><strong>{item.title}</strong><small>{item.can_send_messages ? "Account can send" : "Account cannot send"} · {item.can_view_history ? "History available" : "History unavailable"}</small></div><button className="button button-secondary" onClick={() => onAction("Rules review is available from the community workflow")}>Review evidence</button></div>)}</div></article>}
    {tab === "Messages" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">CONTROLLED HISTORY SYNC</p><h3>Messages and leads</h3></div><button className="button button-secondary" onClick={() => onAction("Use Dialogs to select a bounded sync window")}>Text only by default</button></div><p className="telegram-muted">History is bounded per dialog, idempotent by external message ID and stores attachment metadata only.</p><div className="telegram-message-callout"><strong>Lead discovery</strong><span>Signals create a reviewable Lead card. Automatic DM is disabled; a public reply is never sent from this screen.</span><button className="button button-primary" onClick={() => onAction("Lead discovery is queued through the tenant-safe API")}>Review queue</button></div></article>}
    {tab === "Incidents" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">ACCOUNT HEALTH</p><h3>Incidents</h3></div><button className="button button-secondary" onClick={() => void run(async () => setIncidents(await request("/integrations/telegram/incidents") as Row[]))}>Refresh incidents</button></div>{incidents.length === 0 ? <p className="telegram-muted">No incidents recorded for this workspace.</p> : incidents.map((item) => <div className="telegram-table-row" key={String(item.id)}><div><strong>{String(item.incident_type)}</strong><small>{String(item.source)} · {String(item.detected_at)}</small></div><BadgeText value={String(item.severity)} tone="red" /><span>{String(item.status)}</span></div>)}</article>}
    {tab === "Safety" && <article className="panel telegram-panel"><div className="panel-head"><div><p className="eyebrow">SAFETY CENTER</p><h3>Outbound control</h3></div>{account && <BadgeText value={account.manual_unlock_required ? "SAFETY_LOCK" : "HEALTHY"} tone={account.manual_unlock_required ? "red" : "green"} />}</div><div className="telegram-safety-grid"><div><strong>Emergency Stop</strong><small>Global publication control remains authoritative.</small><button className="button button-secondary" onClick={() => onAction("Use the global Control Center to toggle Emergency Stop")}>Open Control Center</button></div><div><strong>Account SAFETY_LOCK</strong><small>FloodWait, spam warning and restrictions require manual OWNER/ADMIN action.</small><div className="telegram-actions"><button className="button button-secondary" disabled={busy || !account} onClick={lock}>Lock account</button><button className="button button-primary" disabled={busy || !account || !account.manual_unlock_required} onClick={unlock}>Manual unlock</button></div></div></div></article>}
  </section>;
}

function BadgeText({ value, tone }: { value: string; tone: "green" | "amber" | "red" }) { return <span className={`badge badge-${tone}`}>{value}</span>; }

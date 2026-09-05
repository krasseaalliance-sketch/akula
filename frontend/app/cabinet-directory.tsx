"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api-client";

type Workspace = { id?: string; name?: string; slug?: string; status?: string; plan?: string };

const SLOT_COUNT = 10;

export function CabinetDirectoryView({ onAction }: { onAction: (message: string) => void }) {
  const [rows, setRows] = useState<Workspace[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    apiFetch("/workspaces").then(async (response) => {
      if (!response.ok) throw new Error("Workspaces unavailable");
      const payload = await response.json() as Workspace[] | { workspaces?: Workspace[] };
      if (!cancelled) {
        setRows(Array.isArray(payload) ? payload : payload.workspaces ?? []);
        setState("ready");
      }
    }).catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, []);

  const slots = useMemo(() => Array.from({ length: SLOT_COUNT }, (_, index) => rows[index] ?? null), [rows]);
  const active = rows.filter((row) => row.status !== "INACTIVE").length;

  return <section className="cabinet-directory">
    <div className="cabinet-directory-head">
      <div><p className="eyebrow">SCOUT · CLIENT ACCESS</p><h2>10 личных кабинетов</h2><p>Каждый клиент получает отдельный workspace, кампанию и отдельную тему поддержки в супер-группе.</p></div>
      <div className="cabinet-directory-stat"><strong>{active}/{SLOT_COUNT}</strong><span>кабинетов занято</span></div>
    </div>
    {state === "loading" && <div className="cabinet-state">Загружаем реальные workspace…</div>}
    {state === "error" && <div className="cabinet-state cabinet-state-error"><strong>Не удалось загрузить кабинеты.</strong><button className="button button-secondary" onClick={() => onAction("Повторите открытие раздела Workspaces")}>Повторить</button></div>}
    {state === "ready" && <div className="cabinet-grid">{slots.map((workspace, index) => <article className={`cabinet-card ${workspace ? "is-active" : "is-empty"}`} key={workspace?.id ?? `slot-${index}`}>
      <div className="cabinet-card-top"><span className="cabinet-slot">{String(index + 1).padStart(2, "0")}</span><span className={`cabinet-state-dot ${workspace ? "active" : "empty"}`} /></div>
      <h3>{workspace?.name ?? "Свободный кабинет"}</h3>
      <p>{workspace ? `/${workspace.slug ?? "workspace"}` : "Готов к подключению нового человека"}</p>
      {workspace ? <><span className="cabinet-status">{workspace.status ?? "ACTIVE"}</span><button className="button button-secondary" onClick={() => window.location.assign("/customer")}>Открыть кабинет</button></> : <button className="button button-ghost" onClick={() => onAction("Новый кабинет создаётся вместе с клиентом и его кампанией")}>Подключить клиента</button>}
    </article>)}</div>}
  </section>;
}

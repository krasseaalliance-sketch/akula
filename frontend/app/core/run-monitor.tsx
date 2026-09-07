"use client";

type Run = { id: string; task_id: string; agent_id: string; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"; context: { goal: string }; result_summary?: string | null; error_reason?: string | null };
type Agent = { id: string; name: string; current_load?: number };

type Props = {
  runs: Run[];
  agents: Agent[];
  onTransition: (runId: string, status: Run["status"], payload?: Record<string, unknown>) => void;
};

export default function RunMonitor({ runs, agents, onTransition }: Props) {
  return <section className="core-panel core-run-monitor">
    <div className="core-panel-head"><div><span className="core-kicker">ОРКЕСТРАТОР / RUNS</span><h2>Очередь запусков</h2><p>Запуски создаются только вручную и остаются в журнале.</p></div><span className="core-status">{runs.length} запусков</span></div>
    {runs.length === 0 ? <div className="core-empty"><strong>Запусков пока нет.</strong><span>Откройте карточку задачи и подтвердите ручной запуск агента.</span></div> : <div className="core-run-list">{runs.map((run) => <article className="core-run-row" key={run.id}><div><strong>{run.context.goal}</strong><small>Задача {run.task_id.slice(0, 8)} · {agents.find((agent) => agent.id === run.agent_id)?.name ?? "Агент"}</small></div><span className={`core-status status-${run.status.toLowerCase()}`}>{run.status}</span><div className="core-run-actions">{run.status === "QUEUED" && <button className="core-secondary" type="button" onClick={() => onTransition(run.id, "RUNNING")}>Запустить</button>}{run.status === "RUNNING" && <><button className="core-secondary" type="button" onClick={() => onTransition(run.id, "SUCCEEDED", { result_summary: "Результат подтверждён Создателем" })}>Успешно</button><button className="core-archive" type="button" onClick={() => onTransition(run.id, "FAILED", { error_reason: "Запуск завершён с ошибкой" })}>Ошибка</button></>}{(run.status === "QUEUED" || run.status === "RUNNING") && <button className="core-secondary" type="button" onClick={() => onTransition(run.id, "CANCELLED", { error_reason: "Отменено Создателем" })}>Отменить</button>}</div></article>)}</div>}
  </section>;
}

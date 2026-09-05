"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { appPath } from "../../paths";

type LoginPayload = { access_token: string };

export default function ConstructiveLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("Проверяем доступ к рабочему кабинету…");
    try {
      const response = await fetch(appPath("/api/auth/login"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!response.ok) throw new Error("INVALID_CREDENTIALS");
      const payload = await response.json() as LoginPayload;
      window.sessionStorage.setItem("lead-hunter-token", payload.access_token);
      window.location.assign(appPath("/"));
    } catch {
      setMessage("Не удалось войти. Проверьте email и пароль или запросите доступ у Creator.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <div className="auth-shell">
        <Link className="lh-brand" href={appPath("/")}>
          <span className="lh-brand-mark">C</span>
          <span><strong>CONSTRUCTIVE</strong><small>ASmeT WORKSPACE</small></span>
        </Link>
        <div className="auth-grid">
          <div className="auth-intro">
            <p className="lh-eyebrow">CONSTRUCTIVE / ЛИЧНЫЙ КАБИНЕТ</p>
            <h1>Вход в<br /><em>Constructive</em></h1>
            <p>Рабочее пространство объектов, организации, сотрудников, складов и журнала ASmeT.</p>
            <div className="auth-product-line"><span className="cabinet-live-dot" /> CONSTRUCTIVE WORKSPACE</div>
          </div>
          <section className="auth-card">
            <p className="cabinet-kicker">ВОЙТИ В CONSTRUCTIVE</p>
            <h2>Добро пожаловать</h2>
            <form onSubmit={submit}>
              <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.ru" required /></label>
              <label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Введите пароль" required /></label>
              <button className="cabinet-primary-action" type="submit" disabled={busy}>{busy ? "Проверяем…" : "Открыть Constructive"}</button>
            </form>
            {message && <p className="auth-message" role="status">{message}</p>}
            <Link className="auth-back" href={appPath("/")}>← Вернуться в Constructive</Link>
          </section>
        </div>
      </div>
    </main>
  );
}

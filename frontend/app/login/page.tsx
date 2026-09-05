"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { appPath } from "../paths";
import ConstructiveLoginPage from "../constructive/login/page";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  if (process.env.NEXT_PUBLIC_APP_PRODUCT === "constructive") return <ConstructiveLoginPage />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("Проверяем доступ к Scout…");
    try {
      const response = await fetch(appPath("/api/auth/login"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: email.trim(), password }) });
      if (!response.ok) throw new Error("INVALID_CREDENTIALS");
      const payload = await response.json() as { access_token: string };
      window.sessionStorage.setItem("lead-hunter-token", payload.access_token);
      window.location.assign(appPath("/customer"));
    } catch {
      setMessage("Не удалось войти — проверьте email и пароль");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-screen"><div className="auth-shell"><Link className="lh-brand" href={appPath("/")}><span className="lh-brand-mark">LH</span><span><strong>LEADHUNTER</strong><small>SCOUT / WORKSPACE</small></span></Link><div className="auth-grid"><div className="auth-intro"><p className="lh-eyebrow">SCOUT / ЛИЧНЫЙ КАБИНЕТ</p><h1>Рынок видит спрос<br /><em>Scout находит его</em></h1><p>После входа вы увидите только рабочие данные своего аккаунта, возможности и доступные действия</p><div className="auth-product-line"><span className="cabinet-live-dot" /> SCOUT WORKSPACE</div></div><section className="auth-card"><p className="cabinet-kicker">ВОЙТИ В SCOUT</p><h2>Добро пожаловать</h2><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.ru" required /></label><label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Введите пароль" required /></label><button className="cabinet-primary-action" type="submit" disabled={busy}>{busy ? "Проверяем…" : "Открыть кабинет"}</button></form>{message && <p className="auth-message" role="status">{message}</p>}<Link className="auth-back" href={appPath("/")}>← Вернуться к LeadHunter</Link></section></div></div></main>;
}

"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { appPath } from "../../../paths";

export default function ConstructiveRegisterPage() {
  const params = useParams<{ token: string }>();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("Создаём доступ Master…");
    try {
      const response = await fetch(appPath(`/api/constructive/invites/${params.token}/register`), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), password }),
      });
      const payload = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !payload.access_token) throw new Error(payload.detail || "REGISTER_FAILED");
      window.sessionStorage.setItem("lead-hunter-token", payload.access_token);
      window.location.assign(appPath("/cabinet"));
    } catch (error) {
      setMessage(error instanceof Error && error.message === "INVITE_ALREADY_USED" ? "Эта ссылка уже использована." : "Ссылка недействительна или срок её действия истёк.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-screen"><div className="auth-shell"><Link className="lh-brand" href={appPath("/")}><span className="lh-brand-mark">C</span><span><strong>CONSTRUCTIVE</strong><small>ASmeT WORKSPACE</small></span></Link><div className="auth-grid"><div className="auth-intro"><p className="lh-eyebrow">CONSTRUCTIVE / MASTER</p><h1>Ваша рабочая<br /><em>область</em></h1><p>Задайте имя и пароль. После регистрации откроется только назначенная вам область Constructive.</p><div className="auth-product-line"><span className="cabinet-live-dot" /> ПЕРСОНАЛЬНОЕ ПРИГЛАШЕНИЕ</div></div><section className="auth-card"><p className="cabinet-kicker">РЕГИСТРАЦИЯ MASTER</p><h2>Создать доступ</h2><form onSubmit={submit}><label>Имя<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} /></label><label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} /></label><button className="cabinet-primary-action" type="submit" disabled={busy}>{busy ? "Создаём…" : "Войти в Constructive"}</button></form>{message && <p className="auth-message" role="status">{message}</p>}</section></div></div></main>;
}

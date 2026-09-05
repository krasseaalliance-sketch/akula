"use client";

import { appPath } from "./paths";

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let token = typeof window === "undefined" ? "" : window.sessionStorage.getItem("lead-hunter-token") ?? "";
  if (!token) {
    const session = await fetch(appPath("/api/session"), { method: "POST" });
    if (!session.ok) throw new Error("Session bootstrap failed");
    const payload = await session.json() as { access_token: string };
    token = payload.access_token;
    window.sessionStorage.setItem("lead-hunter-token", token);
  }
  const headers = new Headers(init?.headers);
  headers.set("authorization", `Bearer ${token}`);
  headers.set("content-type", "application/json");
  const response = await fetch(appPath(`/api${path}`), { ...init, headers, cache: "no-store" });
  if (response.status === 401 && typeof window !== "undefined") {
    window.sessionStorage.removeItem("lead-hunter-token");
    const session = await fetch(appPath("/api/session"), { method: "POST" });
    if (!session.ok) return response;
    const payload = await session.json() as { access_token: string };
    window.sessionStorage.setItem("lead-hunter-token", payload.access_token);
    const retryHeaders = new Headers(init?.headers);
    retryHeaders.set("authorization", `Bearer ${payload.access_token}`);
    retryHeaders.set("content-type", "application/json");
    return fetch(appPath(`/api${path}`), { ...init, headers: retryHeaders, cache: "no-store" });
  }
  return response;
}

/** Constructive is a real authenticated cabinet; it must never bootstrap demo data. */
export async function strictApiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = typeof window === "undefined" ? "" : window.sessionStorage.getItem("lead-hunter-token") ?? "";
  const headers = new Headers(init?.headers);
  headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  const response = await fetch(appPath(`/api${path}`), { ...init, headers, cache: "no-store" });
  if (response.status === 401 && typeof window !== "undefined") {
    window.sessionStorage.removeItem("lead-hunter-token");
  }
  return response;
}

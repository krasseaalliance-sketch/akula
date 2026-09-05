import { NextResponse } from "next/server";

export async function POST() {
  const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
  const response = await fetch(`${backend}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: process.env.DEMO_EMAIL ?? "demo@leadhunter.local",
      password: process.env.DEMO_PASSWORD ?? "demo-password",
    }),
    cache: "no-store",
  });
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": "application/json" } });
}

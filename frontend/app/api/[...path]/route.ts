import { NextRequest, NextResponse } from "next/server";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
  const url = `${backend}/api/${path.join("/")}${request.nextUrl.search}`;
  const response = await fetch(url, { method: request.method, headers: { "content-type": request.headers.get("content-type") ?? "application/json", authorization: request.headers.get("authorization") ?? "" }, body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(), cache: "no-store" });
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };

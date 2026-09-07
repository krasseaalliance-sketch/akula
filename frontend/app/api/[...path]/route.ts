import { NextRequest, NextResponse } from "next/server";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
  const url = `${backend}/api/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ "content-type": request.headers.get("content-type") ?? "application/json", authorization: request.headers.get("authorization") ?? "" });
  const fileName = request.headers.get("x-file-name");
  if (fileName) headers.set("x-file-name", fileName);
  const response = await fetch(url, { method: request.method, headers, body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(), cache: "no-store" });
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };

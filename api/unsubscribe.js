// GET /api/unsubscribe?id=...&s=...: one click, no questions.
import { del, head } from "@vercel/blob";
import { signed } from "./_lib/common.js";

export async function GET(request) {
  const q = new URL(request.url).searchParams;
  const id = q.get("id") || "";
  if (/^[0-9a-f]{24}$/.test(id) && signed(id, q.get("s"))) {
    await head(`subs/active/${id}.json`).then((b) => del(b.url)).catch(() => {});
  }
  return new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stopped</title><body style="font:16px/1.6 system-ui;background:#f2eee3;color:#1e2f26;max-width:32rem;margin:15vh auto;padding:0 16px"><h1 style="font:400 2rem Georgia,serif">Stopped</h1><p>No more morning notes. Your trails are still saved on your device if you come back.</p>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export const POST = GET; // List-Unsubscribe-Post one-click

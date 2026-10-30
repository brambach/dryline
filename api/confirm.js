// GET /api/confirm?t=...: turns a pending signup into an active one.
import { del, head, put } from "@vercel/blob";
import { hash, readJson, sign } from "./_lib/common.js";

const page = (title, text) =>
  new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><body style="font:16px/1.6 system-ui;background:#f2eee3;color:#1e2f26;max-width:32rem;margin:15vh auto;padding:0 16px"><h1 style="font:400 2rem Georgia,serif">${title}</h1><p>${text}</p><p><a href="/" style="color:inherit">Back to dryline</a></p>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );

export async function GET(request) {
  const t = new URL(request.url).searchParams.get("t") || "";
  if (!/^[0-9a-f]{48}$/.test(t)) return page("That link doesn't work", "It may be old. Sign up again from My trails.");
  const pending = await readJson(`subs/pending/${t}.json`).catch(() => null);
  if (!pending) return page("That link doesn't work", "It may already be used. Sign up again from My trails.");
  const id = hash(pending.email, 24);
  await put(`subs/active/${id}.json`, JSON.stringify({ ...pending, id, unsub: sign(id) }), {
    access: "private",
    contentType: "application/json",
    addRandomSuffix: false,
    allowOverwrite: true,
  });
  await head(`subs/pending/${t}.json`).then((b) => del(b.url)).catch(() => {});
  return page("You're in", "Your first note comes tomorrow around 7am Pacific. Every one has a link to stop.");
}

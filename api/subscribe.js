// POST /api/subscribe {email, trails}: sends a confirm link. Nothing is stored as active until
// the link is clicked, and nothing sends if email isn't configured.
import { put } from "@vercel/blob";
import { emailReady, escape, fail, json, origin, sendEmail, token, trails } from "./_lib/common.js";

export async function POST(request) {
  if (!emailReady()) {
    return fail("The morning email isn't switched on yet. Your trails are saved on this device.", 503);
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("Send JSON.");
  }
  const email = String(body?.email || "").trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200) return fail("That email doesn't look right.");
  const known = new Map((await trails()).map((t) => [t.id, t]));
  const picked = [...new Set((body?.trails || []).filter((id) => known.has(id)))].slice(0, 20);
  if (!picked.length) return fail("Pick at least one trail first.");

  const t = token();
  await put(`subs/pending/${t}.json`, JSON.stringify({ email, trails: picked, at: new Date().toISOString() }), {
    access: "private",
    contentType: "application/json",
    addRandomSuffix: false,
  });
  const link = `${origin(request)}/api/confirm?t=${t}`;
  const names = picked.map((id) => known.get(id).short).join(", ");
  await sendEmail({
    to: email,
    subject: "Confirm your dryline mornings",
    text: `Tap to start getting one short note each morning about ${names}:\n\n${link}\n\nIf you didn't ask for this, ignore it and nothing will send.`,
    html: `<p>Tap to start getting one short note each morning about ${escape(names)}.</p><p><a href="${link}">Start my mornings</a></p><p style="color:#6f766f">If you didn't ask for this, ignore it and nothing will send.</p>`,
  });
  return json({ ok: true }, 202);
}

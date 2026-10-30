// GET /api/morning: the daily note, run by Vercel Cron after the morning build deploys.
// Skips the day entirely when the build didn't run, so nobody gets yesterday's call.
import { list } from "@vercel/blob";
import { emailReady, escape, json, localDay, origin, readJson, sendEmail } from "./_lib/common.js";
import { compose } from "./_lib/compose.js";

export async function GET(request) {
  if (process.env.CRON_SECRET && request.headers.get("authorization") !== `Bearer ${process.env.CRON_SECRET}`) {
    return json({ error: "nope" }, 401);
  }
  if (!emailReady()) return json({ skipped: "email not configured" });
  const site = origin(request);
  const [lines, outlook, trailList] = await Promise.all(
    ["today.json", "outlook.json", "trails.json"].map((f) => fetch(`${site}/${f}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))),
  );
  const today = localDay();
  if (!lines?.length || lines[0].date !== today) return json({ skipped: `no build for ${today}` });
  const byId = Object.fromEntries(lines.map((l) => [l.trail_id, l]));
  const outlooks = Object.fromEntries((outlook?.trails || []).map((o) => [o.trail_id, o]));
  const names = Object.fromEntries((trailList || []).map((t) => [t.id, t.short]));

  let sent = 0, failed = 0, cursor;
  do {
    const page = await list({ prefix: "subs/active/", limit: 1000, cursor });
    for (const blob of page.blobs) {
      const sub = await readJson(blob.pathname).catch(() => null);
      const note = sub && compose(sub, byId, outlooks, names, today);
      if (!note) continue;
      const stop = `${site}/api/unsubscribe?id=${sub.id}&s=${sub.unsub}`;
      const text = [
        ...note.rows.map((r) => `${r.name}: ${r.status}${r.next ? `, ${r.next}` : ""}. ${r.why}`),
        "",
        `Every reason, with sources: ${site}/`,
        `Stop these: ${stop}`,
      ].join("\n");
      const html = `<div style="font:15px/1.55 -apple-system,system-ui,sans-serif;color:#1e2f26;max-width:34rem">${note.rows
        .map((r) => `<p style="margin:0 0 14px"><b>${escape(r.name)}</b>: ${r.status}${r.next ? `, ${escape(r.next)}` : ""}<br><span style="color:#5f6a62;font-size:13px">${escape(r.why)}</span></p>`)
        .join("")}<p style="margin:20px 0 0;font-size:13px;color:#6f766f"><a href="${site}/" style="color:#1e2f26">See the ridge and every source</a> · <a href="${stop}" style="color:#6f766f">Stop these</a></p></div>`;
      try {
        await sendEmail({
          to: sub.email,
          subject: note.subject,
          text,
          html,
          headers: { "List-Unsubscribe": `<${stop}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" },
        });
        sent++;
      } catch {
        failed++;
      }
    }
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);
  return json({ today, sent, failed });
}

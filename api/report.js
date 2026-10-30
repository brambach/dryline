// POST /api/report {trail, condition, note?}: a 10-second report from the trailhead.
import { list, put } from "@vercel/blob";
import { CONDITIONS, fail, json, localDay, NO_STORAGE, storageReady, token, trails, visitor } from "./_lib/common.js";

export async function POST(request) {
  if (!storageReady()) return json({ error: NO_STORAGE, reports: [] }, 503);
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("Send JSON.");
  }
  const known = await trails();
  const trail = known.find((t) => t.id === body?.trail);
  if (!trail) return fail("Unknown trail.");
  if (!CONDITIONS.includes(body?.condition)) return fail("Pick dry, tacky, muddy or snow.");
  const note = typeof body.note === "string" ? body.note.replace(/\s+/g, " ").trim().slice(0, 140) : "";
  if (/https?:\/\/|www\./i.test(note)) return fail("No links in notes, sorry.");

  const day = localDay();
  const who = visitor(request);
  const prefix = `reports/${day}/${trail.id}/`;
  const { blobs } = await list({ prefix, limit: 1000 });
  const now = Date.now();
  const recent = blobs.filter((b) => b.pathname.includes(`-${who}-`) && now - b.uploadedAt.getTime() < 30 * 60e3);
  if (recent.length) return fail("You already reported this trail. Thanks!", 429);

  const at = new Date(now).toISOString();
  const stamp = at.replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const pathname = `${prefix}${stamp}-${body.condition}-${who}-${token().slice(0, 8)}.json`;
  const report = { trail: trail.id, condition: body.condition, note, at };
  await put(pathname, JSON.stringify(report), {
    access: "private",
    contentType: "application/json",
    addRandomSuffix: false,
  });
  return json({ ok: true, report }, 201);
}

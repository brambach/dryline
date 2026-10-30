// GET /api/reports?days=2: recent rider reports, newest first. Public, cached for a minute.
import { list } from "@vercel/blob";
import { json, localDay, NO_STORAGE, readJson, storageReady } from "./_lib/common.js";

export async function GET(request) {
  if (!storageReady()) return json({ error: NO_STORAGE, reports: [] }, 503);
  const days = Math.min(7, Math.max(1, Number(new URL(request.url).searchParams.get("days")) || 2));
  const wanted = [];
  for (let k = 0; k < days; k++) wanted.push(localDay(new Date(Date.now() - k * 864e5)));
  const blobs = [];
  for (const day of wanted) {
    let cursor;
    do {
      const page = await list({ prefix: `reports/${day}/`, limit: 1000, cursor });
      blobs.push(...page.blobs);
      cursor = page.hasMore ? page.cursor : undefined;
    } while (cursor);
  }
  blobs.sort((a, b) => b.uploadedAt - a.uploadedAt);
  const reports = (await Promise.all(blobs.slice(0, 200).map((b) => readJson(b.pathname).catch(() => null))))
    .filter(Boolean)
    .map(({ trail, condition, note, at }) => ({ trail, condition, note, at }));
  return json(
    { reports, days: wanted },
    200,
    { "cache-control": "public, s-maxage=60, stale-while-revalidate=300" },
  );
}

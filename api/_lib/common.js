// Shared bits for dryline's tiny API. Storage is a private Vercel Blob store: nothing here is
// readable without the store's token, so emails and IP hashes never leave the server.
import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import { get } from "@vercel/blob";

export const CONDITIONS = ["dry", "tacky", "muddy", "snow"];

export const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...headers },
  });

export const fail = (error, status = 400) => json({ error }, status);

let trailsCache;
export async function trails() {
  if (!trailsCache) {
    const raw = await readFile(new URL("../../site/trails.json", import.meta.url), "utf8");
    trailsCache = JSON.parse(raw);
  }
  return trailsCache;
}

export function hash(text, n = 64) {
  return createHash("sha256").update(text).digest("hex").slice(0, n);
}

// The per-visitor key for rate limits: a salted hash of the IP, never the IP itself.
export function visitor(request) {
  const ip = (request.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
  const day = new Date().toISOString().slice(0, 10);
  return hash(`${process.env.SUB_SECRET || "dryline"}:${day}:${ip}`, 10);
}

export function sign(value) {
  return createHmac("sha256", process.env.SUB_SECRET || "").update(value).digest("hex").slice(0, 32);
}

export function signed(value, sig) {
  if (!process.env.SUB_SECRET || typeof sig !== "string" || sig.length !== 32) return false;
  return timingSafeEqual(Buffer.from(sign(value)), Buffer.from(sig));
}

export const token = () => randomBytes(24).toString("hex");

export async function readJson(pathname) {
  const res = await get(pathname, { access: "private", useCache: false });
  if (!res || res.statusCode !== 200) return null;
  return JSON.parse(await new Response(res.stream).text());
}

export function localDay(date = new Date()) {
  // YYYY-MM-DD in Pacific time: a report at 9pm belongs to that day's ride.
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles" }).format(date);
}

export function origin(request) {
  return process.env.SITE_ORIGIN || new URL(request.url).origin;
}

// Reports and signups need the private Blob store connected to the project (Storage tab).
export const storageReady = () => Boolean(process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID);
export const NO_STORAGE = "Reports aren't switched on yet. They will be soon.";

export const emailReady = () => Boolean(storageReady() && process.env.RESEND_API_KEY && process.env.MAIL_FROM && process.env.SUB_SECRET);

export async function sendEmail({ to, subject, text, html, headers }) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${process.env.RESEND_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ from: process.env.MAIL_FROM, to, subject, text, html, headers }),
  });
  if (!r.ok) throw new Error(`email failed: ${r.status} ${await r.text()}`);
}

export const escape = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

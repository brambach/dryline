// The morning note, as data. Kept apart from the handler so it can be tested without a network.
const WORD = { dry: "dry", muddy: "muddy", snow: "snowy", closed: "closed", unknown: "unknown" };

function dayWord(iso, today) {
  const d = new Date(`${iso}T12:00:00Z`), t = new Date(`${today}T12:00:00Z`);
  const k = Math.round((d - t) / 864e5);
  if (k === 1) return "tomorrow";
  return d.toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" });
}

export function compose(sub, lines, outlooks, names, today) {
  const mine = sub.trails.map((id) => ({ id, line: lines[id], o: outlooks[id], name: names[id] })).filter((x) => x.line);
  if (!mine.length) return null;
  const dry = mine.filter((x) => x.line.status === "dry");
  const n = mine.length;
  let subject = dry.length === n
    ? (n === 1 ? `${mine[0].name} is dry.` : `All ${n} of your trails are dry.`)
    : dry.length === 0
      ? (n === 1 ? `${mine[0].name} is ${WORD[mine[0].line.status]}.` : `None of your ${n} trails are dry.`)
      : `${dry.length} of your ${n} are dry.`;
  const soonest = mine.filter((x) => x.o?.dry_by).sort((a, b) => a.o.dry_by.localeCompare(b.o.dry_by))[0];
  if (soonest) subject += ` ${soonest.name} dries ${dayWord(soonest.o.dry_by, today)}.`;
  const rows = mine.map(({ id, line, o, name }) => {
    let next = "";
    if (o?.dry_by) next = `dry by ${dayWord(o.dry_by, today)}`;
    else if (o?.wet_from) next = `wet from ${dayWord(o.wet_from, today)}`;
    else if (line.status === "dry" && o?.days?.length > 1) next = "dry all week";
    const why = line.status === "unknown" ? `Missing: ${line.missing?.[0]?.what || "data"}` : line.claims?.[0]?.statement || "";
    return { id, name, status: line.status, next, why };
  });
  return { subject, rows };
}


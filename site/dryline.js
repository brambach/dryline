// dryline: the ridge scrubber, my trails, rider reports, the morning email form.
// No framework. Everything here is an extra on a page that already reads complete without it.
(() => {
  "use strict";
  const root = document.body.dataset.root || "";
  const api = (path) => `${root}api/${path}`;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const MINE = "dryline:mine";
  const WORDS = { dry: "Dry", tacky: "Tacky", muddy: "Muddy", snow: "Snow" };

  const mine = {
    get() {
      try { return JSON.parse(localStorage.getItem(MINE) || "[]"); } catch { return []; }
    },
    set(ids) {
      try { localStorage.setItem(MINE, JSON.stringify(ids)); } catch { /* private mode */ }
    },
  };

  const ago = (iso) => {
    const m = Math.max(1, Math.round((Date.now() - Date.parse(iso)) / 60000));
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
  };
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  // ---- The ridge: the snow line is the one moving thing --------------------------------
  function ridge() {
    const fig = document.querySelector("[data-ridge]");
    if (!fig) return null;
    const tl = JSON.parse(fig.dataset.timeline);
    const yTop = +fig.dataset.yTop, yBot = +fig.dataset.yBottom;
    const ftTop = +fig.dataset.ftTop, ftBot = +fig.dataset.ftBottom;
    const yOf = (ft) => yBot - ((ft - ftBot) * (yBot - yTop)) / (ftTop - ftBot);
    const SKY = yOf(ftTop) - 40; // a snow line above everything: no snow drawn
    const caps = fig.querySelectorAll("[data-cap]");
    const line = fig.querySelector("[data-snowline]");
    const lineLabel = fig.querySelector("[data-snowline-label]");
    const marks = [...fig.querySelectorAll("[data-mk]")];
    const markers = fig.querySelector(".markers");
    const days = fig.querySelector("[data-days]");
    const dayName = fig.querySelector("[data-scrub-day]");
    const dayNote = fig.querySelector("[data-scrub-note]");
    const today = Math.max(0, tl.findIndex((d) => d.kind === "today"));
    const n = tl.length;

    tl.forEach((d, i) => {
      const [w, num] = d.label.split(" ");
      const t = el("span", `sd is-${d.kind}`, w);
      t.append(el("span", "d2", ` ${num}`));
      t.dataset.i = i;
      days.append(t);
    });
    const thumb = el("span", "thumb");
    days.append(thumb);
    if (today < n - 1) {
      const div = el("span", "divider");
      div.style.left = `${((today + 1) / n) * 100}%`;
      days.append(div);
    }

    const yFor = (i) => {
      const d = tl[Math.max(0, Math.min(n - 1, i))];
      return d.snow_line_ft == null ? SKY : yOf(d.snow_line_ft);
    };
    let cur = SKY, target = yFor(today), pos = today, shown = -1, last = 0, raf = 0;

    const paint = () => {
      caps.forEach((c) => c.setAttribute("height", Math.max(0, cur).toFixed(1)));
      line.setAttribute("transform", `translate(0 ${cur.toFixed(1)})`);
      line.toggleAttribute("hidden", cur <= SKY + 2);
      thumb.style.left = `${((pos + 0.5) / n) * 100}%`;
    };
    const tick = (now) => {
      const dt = Math.min(64, now - (last || now));
      last = now;
      const k = 1 - Math.exp(-dt / 110);
      cur += (target - cur) * k;
      paint();
      if (Math.abs(target - cur) > 0.15) raf = requestAnimationFrame(tick);
      else { cur = target; paint(); raf = 0; last = 0; }
    };
    const go = () => {
      if (reduce) { cur = target; paint(); return; }
      if (!raf) raf = requestAnimationFrame(tick);
    };

    const show = (i) => {
      if (i === shown) return;
      shown = i;
      const d = tl[i];
      const counts = {};
      for (const m of marks) {
        const s = d.status[m.dataset.mk] || "unknown";
        m.setAttribute("class", `mk s-${s}`);
        counts[s] = (counts[s] || 0) + 1;
      }
      const date = new Date(`${d.date}T12:00:00`);
      const nice = date.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
      dayName.textContent = d.kind === "today" ? `Today, ${nice}` : nice;
      const order = ["dry", "muddy", "snow", "closed", "unknown"];
      const tally = order.filter((s) => counts[s]).map((s) => `${counts[s]} ${s}`).join(" · ");
      const kind = d.kind === "forecast" ? "forecast" : d.kind === "past" ? "as published" : "";
      dayNote.textContent = [kind, tally].filter(Boolean).join(" · ");
      lineLabel.textContent = d.snow_line_ft == null ? "" : `snow line ~${d.snow_line_ft.toLocaleString()} ft`;
      days.setAttribute("aria-valuetext", `${nice}: ${tally}`);
    };

    const setPos = (f, settle) => {
      pos = Math.max(0, Math.min(n - 1, f));
      const i = Math.floor(pos), t = pos - i;
      target = settle || t === 0 ? yFor(Math.round(pos)) : yFor(i) + (yFor(i + 1) - yFor(i)) * t;
      show(Math.round(pos));
      go();
    };

    days.setAttribute("aria-valuemin", 0);
    days.setAttribute("aria-valuemax", n - 1);
    const fromX = (x) => {
      const r = days.getBoundingClientRect();
      return ((x - r.left) / r.width) * n - 0.5;
    };
    let dragging = false;
    days.addEventListener("pointerdown", (e) => {
      dragging = true;
      days.setPointerCapture(e.pointerId);
      setPos(fromX(e.clientX));
    });
    days.addEventListener("pointermove", (e) => { if (dragging) setPos(fromX(e.clientX)); });
    const end = () => {
      if (!dragging) return;
      dragging = false;
      setPos(Math.round(pos), true);
      days.setAttribute("aria-valuenow", Math.round(pos));
    };
    days.addEventListener("pointerup", end);
    days.addEventListener("pointercancel", end);
    days.addEventListener("keydown", (e) => {
      const step = { ArrowLeft: -1, ArrowRight: 1, Home: -n, End: n }[e.key];
      if (step == null) return;
      e.preventDefault();
      setPos(Math.round(pos) + step, true);
      days.setAttribute("aria-valuenow", Math.round(pos));
    });

    // Rows and markers light each other up.
    const lit = (id, on) => {
      const m = marks.find((x) => x.dataset.mk === id);
      if (!m) return;
      m.classList.toggle("is-lit", on);
      markers.classList.toggle("has-lit", on);
    };
    document.querySelectorAll("[data-line]").forEach((row) => {
      row.addEventListener("pointerenter", () => lit(row.dataset.line, true));
      row.addEventListener("pointerleave", () => lit(row.dataset.line, false));
    });

    // On a phone the ridge is wider than the screen: start on the middle of the lake.
    const scroller = fig.querySelector("[data-ridge-scroll]");
    if (scroller && scroller.scrollWidth > scroller.clientWidth) {
      scroller.scrollLeft = (scroller.scrollWidth - scroller.clientWidth) / 2;
    }

    // On load the snow line settles from the sky to today's height.
    show(today);
    days.setAttribute("aria-valuenow", today);
    paint();
    if (document.visibilityState === "visible") setTimeout(() => setPos(today, true), 250);
    else setPos(today, true);
    return { marks, todayIndex: today };
  }

  // ---- Rider reports --------------------------------------------------------------------
  async function loadReports() {
    try {
      const r = await fetch(api("reports?days=2"), { headers: { accept: "application/json" } });
      if (r.status === 503) {
        // Storage isn't connected yet: say so once, instead of a form that can't send.
        const form = document.querySelector("[data-report-form]");
        if (form) {
          form.classList.add("sent");
          const msg = form.querySelector("[data-form-msg]");
          msg.textContent = "Rider reports open soon. Until then, the call above is all rules and public data.";
        }
        return null;
      }
      if (!r.ok) return null;
      const body = await r.json();
      return Array.isArray(body.reports) ? body.reports : null;
    } catch {
      return null;
    }
  }

  function showReports(reports, ridgeState) {
    const byTrail = {};
    for (const rep of reports) (byTrail[rep.trail] ||= []).push(rep);
    for (const list of Object.values(byTrail)) list.sort((a, b) => b.at.localeCompare(a.at));
    // Row chips on the list pages
    document.querySelectorAll("[data-reports]").forEach((box) => {
      const list = byTrail[box.dataset.reports];
      if (!list) return;
      box.replaceChildren(...list.slice(0, 3).map((rep) => {
        const chip = el("span", "rep");
        chip.append(el("b", null, WORDS[rep.condition] || rep.condition), el("span", "t", ago(rep.at)));
        return chip;
      }));
      box.hidden = false;
    });
    // Pins pop onto the ridge, one per trail with fresh reports
    if (ridgeState) {
      const ns = "http://www.w3.org/2000/svg";
      ridgeState.marks.forEach((m, k) => {
        const list = byTrail[m.dataset.mk];
        if (!list) return;
        const x = +m.dataset.x, y = +m.dataset.y;
        const pin = document.createElementNS(ns, "g");
        pin.setAttribute("class", "pin");
        const c = document.createElementNS(ns, "circle");
        c.setAttribute("cx", x + 9); c.setAttribute("cy", y - 40); c.setAttribute("r", 6.5);
        const t = document.createElementNS(ns, "text");
        t.setAttribute("x", x + 9); t.setAttribute("y", y - 37); t.setAttribute("text-anchor", "middle");
        t.textContent = list.length > 9 ? "9+" : list.length;
        pin.append(c, t);
        m.append(pin);
        if (!reduce) {
          pin.animate(
            [{ transform: "scale(0)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
            { duration: 480, delay: 900 + k * 40, easing: "cubic-bezier(.34,1.5,.64,1)", fill: "backwards" },
          );
        }
      });
    }
    // The trail page's own list
    const full = document.querySelector("[data-report-list]");
    const block = document.querySelector("[data-report-block]");
    if (full && block) {
      const list = byTrail[block.dataset.trail] || [];
      if (list.length) {
        full.replaceChildren(...list.map((rep) => {
          const li = el("li");
          li.append(el("b", null, WORDS[rep.condition] || rep.condition));
          if (rep.note) li.append(el("span", "n", rep.note));
          li.append(el("span", "t", ago(rep.at)));
          return li;
        }));
      }
    }
  }

  function reportForm() {
    const form = document.querySelector("[data-report-form]");
    const block = document.querySelector("[data-report-block]");
    if (!form || !block) return;
    const msg = form.querySelector("[data-form-msg]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = new FormData(form);
      const btn = form.querySelector("button");
      btn.disabled = true;
      msg.className = "form-msg";
      msg.textContent = "Sending…";
      try {
        const r = await fetch(api("report"), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            trail: block.dataset.trail,
            condition: data.get("condition"),
            note: (data.get("note") || "").toString().slice(0, 140),
          }),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || "That didn't go through. Try again in a minute.");
        form.classList.add("sent");
        msg.className = "form-msg ok";
        msg.textContent = `Thanks. Your report is on ${block.dataset.name} now.`;
        const list = await loadReports();
        if (list) showReports(list, null);
      } catch (err) {
        msg.className = "form-msg err";
        msg.textContent = err.message.startsWith("Failed to fetch")
          ? "Couldn't reach dryline. Check your signal and try again."
          : err.message;
        btn.disabled = false;
      }
    });
  }

  // ---- My trails ------------------------------------------------------------------------
  function mineOnToday() {
    const box = document.querySelector("[data-mine]");
    if (!box) return;
    const ids = mine.get();
    if (!ids.length) return;
    const list = box.querySelector("[data-mine-list]");
    for (const id of ids) {
      const row = document.querySelector(`.group:not([data-mine]) [data-line="${CSS.escape(id)}"]`);
      if (row) list.append(row.cloneNode(true));
    }
    box.hidden = !list.children.length;
  }

  function minePage() {
    const form = document.querySelector("[data-pick]");
    if (!form) return;
    const ids = new Set(mine.get());
    form.querySelectorAll("input[name=trail]").forEach((box) => {
      box.checked = ids.has(box.value);
      box.addEventListener("change", () => {
        box.checked ? ids.add(box.value) : ids.delete(box.value);
        mine.set([...ids]);
      });
    });
    const sub = document.querySelector("[data-subscribe]");
    if (!sub) return;
    const msg = sub.querySelector("[data-form-msg]");
    sub.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = sub.querySelector("button");
      if (!ids.size) {
        msg.className = "form-msg err";
        msg.textContent = "Pick at least one trail first.";
        return;
      }
      btn.disabled = true;
      msg.className = "form-msg";
      msg.textContent = "Sending…";
      try {
        const r = await fetch(api("subscribe"), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email: new FormData(sub).get("email"), trails: [...ids] }),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || "That didn't go through. Try again in a minute.");
        msg.className = "form-msg ok";
        msg.textContent = "Check your inbox for a link to confirm. Nothing sends until you click it.";
      } catch (err) {
        msg.className = "form-msg err";
        msg.textContent = err.message.startsWith("Failed to fetch") ? "Couldn't reach dryline. Try again." : err.message;
        btn.disabled = false;
      }
    });
  }

  const ridgeState = ridge();
  mineOnToday();
  minePage();
  reportForm();
  if (document.querySelector("[data-reports], [data-report-list]")) {
    loadReports().then((list) => { if (list) showReports(list, ridgeState); });
  }
})();

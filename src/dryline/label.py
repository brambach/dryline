"""A small local labeling page: pick what each trail was really like, saved to the labels CSV.

Runs on localhost only. dryline's own call is hidden until you open it, so it doesn't anchor you.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dryline.evaluate import TRUTHS, Label, read_labels, write_label
from dryline.models import TrailLine
from dryline.site import LABEL, load_lines

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label trail-days</title>
<style>
:root {{ --bg:#fbfaf8; --ink:#1b1b1a; --ink-3:#8c8a86; --rule:#e6e3de; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121211; --ink:#ecebe8; --rule:#2a2927; }} }}
body {{ margin:0 auto; max-width:46rem; padding:24px 16px 64px; background:var(--bg);
  color:var(--ink); font:16px/1.5 system-ui, sans-serif; }}
h1 {{ font-weight:400; font-size:2.2rem; margin:0 0 4px; }}
h2 {{ font-size:.8rem; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3);
  margin:32px 0 8px; }}
.row {{ border-bottom:1px solid var(--rule); padding:12px 0; }}
.name {{ font-weight:600; }}
.opts {{ display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }}
.opts label {{ border:1px solid var(--rule); border-radius:4px; padding:4px 10px; cursor:pointer;
  transition:background 200ms ease-out; }}
.opts input {{ margin-right:4px; }}
.opts label:has(input:checked) {{ background:var(--ink); color:var(--bg); }}
input[type=text] {{ width:100%; font:inherit; padding:4px 8px; border:1px solid var(--rule);
  background:transparent; color:inherit; }}
details {{ color:var(--ink-3); font-size:.9rem; margin-top:6px; }}
.saved {{ color:var(--ink-3); font-size:.8rem; }}
</style></head><body>
<h1>Label trail-days</h1>
<p>Pick what the trail was actually like that day, from your own visit or a report you trust.
Saved to <code>{labels_path}</code>. Leave a trail blank if you don't know.</p>
{sections}
<script>
document.querySelectorAll('.row').forEach(row => {{
  const send = () => {{
    const truth = row.querySelector('input[type=radio]:checked');
    if (!truth) return;
    fetch('/label', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{date: row.dataset.date, trail: row.dataset.trail,
        truth: truth.value, note: row.querySelector('input[type=text]').value}})}})
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(() => row.querySelector('.saved').textContent = 'saved')
      .catch(e => row.querySelector('.saved').textContent = 'error: ' + e);
  }};
  row.querySelectorAll('input[type=radio]').forEach(i => i.addEventListener('change', send));
  row.querySelector('input[type=text]').addEventListener('change', send);
}});
</script>
</body></html>"""


def render_page(
    days: dict[dt.date, list[TrailLine]], labels: list[Label], labels_path: str, max_days: int = 7
) -> str:
    have = {(lab.date, lab.trail): lab for lab in labels}
    sections = []
    for day in sorted(days, reverse=True)[:max_days]:
        rows = []
        for line in sorted(days[day], key=lambda x: x.trail_name):
            lab = have.get((day, line.trail_id))
            opts = "".join(
                f'<label><input type="radio" name="{day}-{line.trail_id}" value="{t}"'
                f"{' checked' if lab and lab.truth == t else ''}>{t}</label>"
                for t in TRUTHS
            )
            reasons = line.claims or ()
            why = (
                html.escape(reasons[0].statement)
                if reasons
                else html.escape(line.missing[0].what if line.missing else "")
            )
            rows.append(
                f'<div class="row" data-date="{day}" data-trail="{html.escape(line.trail_id)}">'
                f'<div class="name">{html.escape(line.trail_name)}</div>'
                f'<div class="opts">{opts}</div>'
                f'<input type="text" placeholder="note (optional)"'
                f' value="{html.escape(lab.note) if lab else ""}">'
                f'<span class="saved">{"saved" if lab else ""}</span>'
                f"<details><summary>dryline said</summary>{LABEL[line.status]}. {why}</details>"
                "</div>"
            )
        sections.append(f"<h2>{day:%A, %B %-d}</h2>" + "".join(rows))
    return PAGE.format(labels_path=html.escape(labels_path), sections="".join(sections))


def serve(lines_dir: Path, labels_path: Path, port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            labels = read_labels(labels_path) if labels_path.exists() else []
            body = render_page(load_lines(lines_dir), labels, str(labels_path)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/label":
                self.send_error(404)
                return
            # JSON only: a cross-site form post can't set this content type without CORS.
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_error(415)
                return
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            truth = data.get("truth")
            if truth not in TRUTHS:
                self.send_error(400, "bad truth")
                return
            write_label(
                labels_path,
                Label(
                    date=dt.date.fromisoformat(data["date"]),
                    trail=str(data["trail"]),
                    truth=truth,
                    note=str(data.get("note", ""))[:300],
                ),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Labeling page: http://127.0.0.1:{port}/  (Ctrl-C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()

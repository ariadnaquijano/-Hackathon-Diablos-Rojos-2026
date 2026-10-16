"""A small local browser dashboard for hypothetical Stuff+ pitch profiles."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from .data import ALTITUDES, PITCH_TYPES, RAW_PHYSICS
from .pipeline import predict_profile


_DEFAULT = {
    "pitch_group": "Four-Seam",
    "pitcher_hand": "Right",
    "altitude_category": "No Altitude",
    "RelSpeed": 93.0,
    "SpinRate": 2300.0,
    "SpinAxis": 200.0,
    "RelHeight": 6.0,
    "RelSide": 2.0,
    "Extension": 6.2,
    "InducedVertBreak": 17.0,
    "HorzBreak": 9.0,
}

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stuff+ Sandbox</title>
<style>
:root{--navy:#102a43;--ink:#172b3a;--muted:#607180;--red:#d64045;--cream:#f6f5f1;--line:#dce3e8;--pale:#eaf0f4;--green:#276749;--amber:#8b5d11}
*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);font:16px/1.45 "Segoe UI",Arial,sans-serif}.wrap{max-width:1120px;margin:auto;padding:34px 24px 56px}.top{border-left:7px solid var(--red);padding-left:20px;margin-bottom:24px}.eyebrow{color:var(--red);font-weight:800;font-size:13px;letter-spacing:.1em;text-transform:uppercase}h1{color:var(--navy);font-size:clamp(30px,4vw,44px);line-height:1.1;margin:8px 0}p{margin:8px 0;color:var(--muted)}.notice{background:#fff1e2;border:1px solid #f2d5ae;border-radius:12px;padding:12px 16px;color:#684914;margin:20px 0}.grid{display:grid;grid-template-columns:minmax(340px,1fr) minmax(350px,1fr);gap:22px;align-items:start}.panel{background:white;border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 5px 18px #102a430b}.panel h2{margin:0 0 16px;color:var(--navy);font-size:20px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px}.field label{display:block;font-size:13px;font-weight:700;color:#344a5b;margin-bottom:5px}.field input,.field select{width:100%;height:42px;border:1px solid #cbd5dc;border-radius:8px;padding:8px 10px;font:inherit;color:var(--ink);background:#fff}.field small{display:block;color:#748390;font-size:11px;margin-top:3px}.range-row{display:flex;align-items:center;gap:10px}.field input[type=range]{height:24px;padding:0;border:0;accent-color:var(--red);flex:1;min-width:80px}.field input[type=number]{flex:0 0 100px;width:100px}.wide{grid-column:1/-1}.actions{display:flex;gap:12px;align-items:center;margin-top:18px}.button{border:0;background:var(--red);color:#fff;font-weight:800;padding:12px 18px;border-radius:9px;font:inherit;cursor:pointer}.button:disabled{opacity:.55;cursor:wait}.status{font-size:13px;color:var(--muted)}.result-title{display:flex;justify-content:space-between;gap:12px;align-items:center}.badge{background:var(--pale);color:var(--navy);font-size:12px;font-weight:800;padding:6px 10px;border-radius:999px}.score{font-size:56px;font-weight:850;color:var(--navy);line-height:1}.score small{font-size:14px;font-weight:600;color:var(--muted)}.metric{margin:12px 0 19px}.scenarios{display:grid;gap:10px;margin-top:16px}.scenario{border:1px solid var(--line);border-radius:12px;padding:13px}.scenario-head{display:flex;justify-content:space-between;gap:10px;font-weight:750}.bar{height:8px;background:#e7edf1;border-radius:99px;margin:9px 0 7px;overflow:hidden}.bar span{display:block;background:#36745a;height:100%;border-radius:99px}.detail{font-size:13px;color:var(--muted)}.flag{color:var(--amber);font-weight:750}.empty{padding:20px 0;color:var(--muted)}.foot{font-size:13px;margin-top:18px}.foot strong{color:var(--ink)}
@media(max-width:780px){.grid{grid-template-columns:1fr}.fields{gap:10px}.wrap{padding:24px 14px 40px}}
</style></head><body><main class="wrap">
<header class="top"><div class="eyebrow">Diablos Rojos · Stuff+ prototype</div><h1>Pitch Stuff+ Sandbox</h1><p>Enter one hypothetical pitch profile to see its family-relative score and modeled altitude scenarios.</p></header>
<div class="notice"><strong>Experimental:</strong> this scores one pitch at a time, not a full pitcher arsenal. Altitude outputs are observational movement projections, not causal park effects or guarantees.</div>
<div class="grid"><section class="panel"><h2>Pitch profile</h2><p>Type an exact value or adjust it with its slider.</p><form id="profile"><div class="fields">
<div class="field"><label for="pitch_group">Pitch family</label><select id="pitch_group" name="pitch_group">{{PITCH_OPTIONS}}</select></div>
<div class="field"><label for="pitcher_hand">Throwing hand</label><select id="pitcher_hand" name="pitcher_hand"><option>Right</option><option>Left</option></select></div>
<div class="field"><label for="altitude_category">Source altitude</label><select id="altitude_category" name="altitude_category">{{ALTITUDE_OPTIONS}}</select><small>Altitude where the entered movement is assumed to occur.</small></div>
{{NUMBER_FIELDS}}
</div><div class="actions"><button id="submit" class="button" type="submit">Calculate Stuff+</button><span id="status" class="status" aria-live="polite"></span></div></form>
<p class="foot"><strong>Coordinates:</strong> enter the original, unmirrored sensor values. For left-handed pitchers, the model mirrors horizontal geometry internally.</p></section>
<section class="panel"><div class="result-title"><h2>Score scenarios</h2><span id="familyBadge" class="badge">Awaiting profile</span></div><div id="result" class="empty">Submit a pitch profile to compare the three altitude categories.</div></section></div>
<p class="foot">Stuff+ is centered at 100 within each pitch family; 10 points represent one historical standard deviation on the model scale. Values outside the training reference range should be treated with extra caution.</p>
</main><script>
const form=document.querySelector('#profile'),button=document.querySelector('#submit'),statusEl=document.querySelector('#status'),out=document.querySelector('#result');
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function score(v){return v==null?'—':Number(v).toFixed(1)}
for(const slider of form.querySelectorAll('input[type="range"]')){const number=form.elements.namedItem(slider.dataset.field);slider.addEventListener('input',()=>{number.value=slider.value});number.addEventListener('input',()=>{const v=Number(number.value);if(number.value!==''&&v>=Number(slider.min)&&v<=Number(slider.max))slider.value=String(v)})}
form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;statusEl.textContent='Scoring…';out.innerHTML='<div class="empty">Running the saved model…</div>';try{const data=Object.fromEntries(new FormData(form).entries());for(const k of ['RelSpeed','SpinRate','SpinAxis','RelHeight','RelSide','Extension','InducedVertBreak','HorzBreak'])data[k]=Number(data[k]);const response=await fetch('/score',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const payload=await response.json();if(!response.ok)throw new Error(payload.error||'Could not score this profile.');document.querySelector('#familyBadge').textContent=payload.pitch_type;const max=160,min=40,span=max-min;const primary=`<div class="metric"><div class="score">${score(payload.observed_stuff_plus)} <small>Stuff+</small></div><div class="detail">Entered profile at ${esc(payload.source_altitude)} · ${esc(payload.pitch_type)}</div></div>`;const cards=payload.scenarios.map(s=>{const width=s.stuff_plus==null?0:Math.max(3,Math.min(100,(s.stuff_plus-min)/span*100));const alert=s.outside_reference_range?'<div class="flag">Outside the historical reference range</div>':'';return `<article class="scenario"><div class="scenario-head"><span>${esc(s.altitude)}</span><span>${score(s.stuff_plus)}</span></div><div class="bar"><span style="width:${width}%"></span></div><div class="detail">Projected movement: IVB ${s.ivb_inches==null?'—':s.ivb_inches.toFixed(1)} in · arm-side HB ${s.hb_arm_side_inches==null?'—':s.hb_arm_side_inches.toFixed(1)} in</div>${s.supported?'': '<div class="flag">Insufficient model support for this scenario</div>'}${alert}</article>`}).join('');const delta=payload.delta_extreme_vs_no_altitude==null?'Not available':`${payload.delta_extreme_vs_no_altitude>0?'+':''}${payload.delta_extreme_vs_no_altitude.toFixed(1)} points`;out.innerHTML=primary+`<div class="detail"><strong>Extreme vs no altitude:</strong> ${delta}</div><div class="scenarios">${cards}</div><p class="foot">${esc(payload.interpretation)}</p>`;statusEl.textContent='Updated';}catch(err){out.innerHTML=`<div class="flag">${esc(err.message)}</div>`;statusEl.textContent='Please review the inputs.'}finally{button.disabled=false}});
</script></body></html>"""


def _page() -> bytes:
    pitch_options = "".join(f'<option>{name}</option>' for name in PITCH_TYPES)
    altitude_options = "".join(f'<option>{name}</option>' for name in ALTITUDES)
    descriptions = {
        "RelSpeed": ("Release speed", "mph", 40, 110, 0.1),
        "SpinRate": ("Spin rate", "rpm", 0, 4000, 1),
        "SpinAxis": ("Spin axis", "degrees · 0–360", 0, 360, 0.1),
        "RelHeight": ("Release height", "ft", 1, 8.5, 0.01),
        "RelSide": ("Release side", "ft · signed sensor value", -6, 6, 0.01),
        "Extension": ("Extension", "ft", 3, 9.5, 0.01),
        "InducedVertBreak": ("Induced vertical break", "in", -35, 35, 0.1),
        "HorzBreak": ("Horizontal break", "in · signed sensor value", -35, 35, 0.1),
    }
    fields = []
    for key in RAW_PHYSICS:
        label, unit, low, high, step = descriptions[key]
        fields.append(
            f'<div class="field"><label for="{key}">{label} ({unit})</label>'
            f'<div class="range-row"><input id="{key}_slider" type="range" min="{low}" max="{high}" step="{step}" '
            f'value="{_DEFAULT[key]}" data-field="{key}" aria-label="{label} slider">'
            f'<input id="{key}" name="{key}" type="number" min="{low}" max="{high}" step="{step}" '
            f'value="{_DEFAULT[key]}" aria-label="{label} exact value" required></div></div>'
        )
    html = (_PAGE.replace("{{PITCH_OPTIONS}}", pitch_options)
            .replace("{{ALTITUDE_OPTIONS}}", altitude_options)
            .replace("{{NUMBER_FIELDS}}", "".join(fields)))
    return html.encode("utf-8")


def make_handler(model_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[{self.log_date_time_string()}] {fmt % args}")

        def _send(self, code: int, body: bytes, content_type: str):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            self._send(200, _page(), "text/html; charset=utf-8")

        def do_POST(self):
            if urlparse(self.path).path != "/score":
                self._send(404, b'{"error":"Not found"}', "application/json; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    raise ValueError("Request body is missing or too large.")
                profile = json.loads(self.rfile.read(length))
                if not isinstance(profile, dict):
                    raise ValueError("A pitch profile is required.")
                result = predict_profile(model_dir, profile)
                body = json.dumps(result, allow_nan=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": f"Scoring failed: {exc}"}).encode("utf-8"), "application/json; charset=utf-8")

    return Handler


def serve(model_dir: Path, host: str = "127.0.0.1", port: int = 8501):
    model_dir = model_dir.expanduser().resolve()
    if not (model_dir / "manifest.json").is_file():
        raise FileNotFoundError(f"Model manifest not found in {model_dir}. Train the model first.")
    server = ThreadingHTTPServer((host, port), make_handler(model_dir))
    print(f"Stuff+ dashboard: http://{host}:{port}  (models: {model_dir})")
    print("Press Ctrl+C to stop the local dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()

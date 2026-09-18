/* Minimal SVG chart layer: line, horizontal bars (grouped/stacked), vertical bars,
   waterfall and line+markers. No dependencies, theme-token aware, redraws on resize.
   Specs follow the house style: 2px lines, <=24px bars with 4px rounded data ends,
   2px surface gaps between touching fills, hairline grid, crosshair tooltip. */
(function (global) {
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const SVG = "http://www.w3.org/2000/svg";
  const mk = (tag, attrs) => {
    const n = document.createElementNS(SVG, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };
  const fmtPct = (v, d = 0) => (v * 100).toFixed(d) + "%";
  const col = c => (typeof c === "string" && c.startsWith("--")) ? css(c) : c;
  /* Same hue, washed out: lets one portfolio keep one colour and still show sign. */
  const fade = (c, a) => {
    const h = col(c).trim();
    const m = /^#?([0-9a-f]{6})$/i.exec(h);
    if (!m) return h;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  const niceTicks = (lo, hi, count = 5) => {
    if (!isFinite(lo) || !isFinite(hi) || lo === hi) return [lo];
    const span = hi - lo;
    const step0 = Math.pow(10, Math.floor(Math.log10(span / count)));
    const err = span / count / step0;
    const step = step0 * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(Math.round(v / step) * step);
    return out;
  };

  const REGISTRY = [];

  class Chart {
    constructor(host, opts) {
      this.host = host;
      this.opts = opts;
      REGISTRY.push(this);
      host.style.position = "relative";
      this.tip = document.createElement("div");
      Object.assign(this.tip.style, {
        position: "absolute", pointerEvents: "none", opacity: "0", transition: "opacity .08s",
        background: "var(--surface)", border: "1px solid var(--rule-strong)", borderRadius: "5px",
        padding: "7px 9px", font: "500 11.5px var(--mono)", color: "var(--ink)",
        boxShadow: "0 2px 10px rgba(0,0,0,.10)", zIndex: "5", whiteSpace: "nowrap",
      });
      host.appendChild(this.tip);
      this.draw();
      new ResizeObserver(() => this.draw()).observe(host);
      const redraw = () => setTimeout(() => this.draw(), 30);
      matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
      new MutationObserver(redraw).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
    }
    showTip(html, x, y) {
      this.tip.innerHTML = "";
      this.tip.appendChild(html);
      this.tip.style.opacity = "1";
      const w = this.tip.offsetWidth, hw = this.host.clientWidth;
      this.tip.style.left = Math.max(4, Math.min(hw - w - 4, x - w / 2)) + "px";
      this.tip.style.top = Math.max(0, y - this.tip.offsetHeight - 12) + "px";
    }
    hideTip() { this.tip.style.opacity = "0"; }
    draw() {
      const w = this.host.clientWidth || 640;
      if (this.svg) this.svg.remove();
      this.svg = mk("svg", {width: "100%", height: String(this.opts.height), viewBox: `0 0 ${w} ${this.opts.height}`,
                            role: "img", "aria-label": this.opts.label || ""});
      this.svg.style.display = "block";
      this.host.appendChild(this.svg);
      this.render(this.svg, w, this.opts.height);
      this.animate();
    }
    /* One entrance per chart: lines draw themselves, bars grow off the axis.
       Re-running draw() replays it, which is how a tab switch re-animates. */
    animate() {
      const kind = this.opts.animate;
      if (!kind || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      if (kind === "line") {
        this.svg.querySelectorAll("path[data-line]").forEach((el, i) => {
          const len = el.getTotalLength ? el.getTotalLength() : 4000;
          el.style.strokeDasharray = len;
          el.style.strokeDashoffset = len;
          el.style.animation = `chartDraw 1.4s cubic-bezier(.25,.8,.3,1) ${i * 0.12}s forwards`;
        });
        return;
      }
      const g = this.svg.querySelector("g[data-bars]");
      if (!g) return;
      g.style.transformBox = "fill-box";
      g.style.transformOrigin = {barsL: "left center", barsR: "right center", barsUp: "center bottom"}[kind];
      g.style.animation = (kind === "barsUp" ? "chartGrowY" : "chartGrowX")
                          + " .8s cubic-bezier(.2,.85,.25,1) both";
    }
    tipRow(color, label, value) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:7px;justify-content:space-between";
      const left = document.createElement("span");
      left.style.cssText = "display:inline-flex;align-items:center;gap:6px;color:var(--ink-2)";
      const key = document.createElement("i");
      key.style.cssText = `width:12px;height:2px;background:${color};display:inline-block;flex:none`;
      left.appendChild(key);
      left.appendChild(document.createTextNode(label));
      const right = document.createElement("strong");
      right.textContent = value;
      row.appendChild(left); row.appendChild(right);
      return row;
    }
  }

  /* series: [{name, color, x:[dates], y:[values]}] ; opts.fmt(v) */
  class LineChart extends Chart {
    render(svg, W, H) {
      const o = this.opts, S = o.series;
      const pad = {l: 52, r: 14, t: 10, b: 26};
      const n = S[0].y.length;
      const all = S.flatMap(s => s.y).filter(v => v !== null && isFinite(v));
      let lo = Math.min(...all), hi = Math.max(...all);
      if (o.zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
      const ticks = niceTicks(lo, hi, 5);
      lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
      const X = i => pad.l + (W - pad.l - pad.r) * (n === 1 ? 0.5 : i / (n - 1));
      const Y = v => H - pad.b - (H - pad.t - pad.b) * (v - lo) / (hi - lo || 1);
      ticks.forEach(t => {
        svg.appendChild(mk("line", {x1: pad.l, x2: W - pad.r, y1: Y(t), y2: Y(t),
                                    stroke: t === 0 ? css("--rule-strong") : css("--rule"), "stroke-width": 1}));
        const lb = mk("text", {x: pad.l - 8, y: Y(t) + 3.5, "text-anchor": "end", fill: css("--muted"),
                               "font-size": 10.5, "font-family": "var(--mono)"});
        lb.textContent = o.fmt(t);
        svg.appendChild(lb);
      });
      // x labels: first of each year
      const seen = new Set();
      S[0].x.forEach((d, i) => {
        const y = String(d).slice(0, 4);
        if (seen.has(y) || i < 2) { seen.add(y); return; }
        seen.add(y);
        const t = mk("text", {x: X(i), y: H - 8, "text-anchor": "middle", fill: css("--muted"),
                              "font-size": 10.5, "font-family": "var(--mono)"});
        t.textContent = y;
        svg.appendChild(t);
      });
      S.forEach(s => {
        let d = "";
        s.y.forEach((v, i) => { if (v === null || !isFinite(v)) return; d += (d ? "L" : "M") + X(i) + " " + Y(v); });
        if (o.area) {
          const a = mk("path", {d: d + `L${X(n - 1)} ${Y(0)}L${X(0)} ${Y(0)}Z`, fill: col(s.color), opacity: 0.10});
          svg.appendChild(a);
        }
        svg.appendChild(mk("path", {d, fill: "none", stroke: col(s.color), "stroke-width": s.width || 2,
                                    "stroke-linejoin": "round", "stroke-linecap": "round",
                                    "data-line": "1"}));
      });
      /* Threshold lines: the level a monitor triggers at, drawn where the eye
         already is rather than described in the caption. */
      (o.hlines || []).forEach(h => {
        svg.appendChild(mk("line", {x1: pad.l, x2: W - pad.r, y1: Y(h.value), y2: Y(h.value),
                                    stroke: col(h.color || "--neg"), "stroke-width": 1.2,
                                    "stroke-dasharray": "5 4"}));
        if (h.text) {
          const t = mk("text", {x: pad.l + 4, y: Y(h.value) - 5, fill: col(h.color || "--neg"),
                                "font-size": 10.5, "font-weight": 700});
          t.textContent = h.text;
          svg.appendChild(t);
        }
      });
      /* Callouts: point at the tallest reading inside a date window, so the rest of
         the chart is read relative to it rather than hovered for. */
      (o.notes || []).forEach(nt => {
        let bi = -1, bv = -Infinity;
        S.forEach(s => s.y.forEach((v, i) => {
          const d = String(s.x[i]);
          if (v === null || !isFinite(v) || d < nt.from || d > nt.to) return;
          if (v > bv) { bv = v; bi = i; }
        }));
        if (bi < 0) return;
        const px = X(bi), py = Y(bv);
        const right = px < W * 0.62;
        const tx = px + (right ? 26 : -26), ty = Math.max(pad.t + 12, py - 20);
        svg.appendChild(mk("line", {x1: px, y1: py - 3, x2: tx, y2: ty + 3,
                                    stroke: css("--muted"), "stroke-width": 1}));
        const t = mk("text", {x: tx + (right ? 4 : -4), y: ty, "text-anchor": right ? "start" : "end",
                              fill: css("--ink-2"), "font-size": 10.5, "font-weight": 700});
        t.textContent = nt.text;
        svg.appendChild(t);
        const bb = t.getBBox();
        const bg = mk("rect", {x: bb.x - 4, y: bb.y - 3, width: bb.width + 8, height: bb.height + 6,
                               fill: "var(--surface)", stroke: css("--rule-strong"), "stroke-width": 1, rx: 2});
        svg.insertBefore(bg, t);
      });
      const cross = mk("line", {y1: pad.t, y2: H - pad.b, stroke: css("--rule-strong"), "stroke-width": 1, opacity: 0});
      svg.appendChild(cross);
      const dots = S.map(s => {
        const c = mk("circle", {r: 4, fill: col(s.color), stroke: css("--surface"), "stroke-width": 2, opacity: 0});
        svg.appendChild(c);
        return c;
      });
      const hit = mk("rect", {x: pad.l, y: pad.t, width: Math.max(1, W - pad.l - pad.r), height: Math.max(1, H - pad.t - pad.b),
                              fill: "transparent"});
      svg.appendChild(hit);
      const move = ev => {
        const r = svg.getBoundingClientRect();
        const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
        const i = Math.max(0, Math.min(n - 1, Math.round((px - pad.l) / ((W - pad.l - pad.r) / (n - 1 || 1)))));
        cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", 1);
        const box = document.createElement("div");
        const head = document.createElement("div");
        head.style.cssText = "color:var(--muted);margin-bottom:4px";
        head.textContent = S[0].x[i];
        box.appendChild(head);
        S.forEach((s, k) => {
          const v = s.y[i];
          dots[k].setAttribute("cx", X(i));
          dots[k].setAttribute("cy", Y(v === null ? lo : v));
          dots[k].setAttribute("opacity", v === null || !isFinite(v) ? 0 : 1);
          box.appendChild(this.tipRow(col(s.color), s.name, v === null || !isFinite(v) ? "n/a" : o.fmt(v, 2)));
        });
        this.showTip(box, X(i), pad.t + 10);
      };
      hit.addEventListener("pointermove", move);
      hit.addEventListener("pointerleave", () => {
        this.hideTip(); cross.setAttribute("opacity", 0); dots.forEach(d => d.setAttribute("opacity", 0));
      });
    }
  }

  /* categories down the y axis; series [{name,color,x:[...]}]; mode group|stack */
  class BarsH extends Chart {
    render(svg, W, H) {
      const o = this.opts, S = o.series, cats = o.categories;
      const pad = {l: o.labelWidth || 150, r: 46, t: 8, b: 26};
      const vals = S.flatMap(s => s.x.filter(v => v !== null && isFinite(v)));
      const stackTot = cats.map((_, i) => S.reduce((a, s) => a + Math.max(0, s.x[i] || 0), 0));
      let lo = Math.min(0, ...vals), hi = o.mode === "stack" ? Math.max(...stackTot) : Math.max(0, ...vals);
      const ticks = niceTicks(lo, hi, 4);
      lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
      const X = v => pad.l + (W - pad.l - pad.r) * (v - lo) / (hi - lo || 1);
      const band = (H - pad.t - pad.b) / cats.length;
      ticks.forEach(t => {
        svg.appendChild(mk("line", {x1: X(t), x2: X(t), y1: pad.t, y2: H - pad.b,
                                    stroke: t === 0 ? css("--rule-strong") : css("--rule"), "stroke-width": 1}));
        const lb = mk("text", {x: X(t), y: H - 8, "text-anchor": "middle", fill: css("--muted"),
                               "font-size": 10.5, "font-family": "var(--mono)"});
        lb.textContent = o.fmt(t);
        svg.appendChild(lb);
      });
      // labels are right-aligned into the pad.l gutter, so they have to fit it
      const maxChars = Math.max(8, Math.floor((pad.l - 14) / 6.2));
      cats.forEach((cat, i) => {
        const lb = mk("text", {x: pad.l - 10, y: pad.t + band * (i + 0.5) + 4, "text-anchor": "end",
                               fill: css("--ink-2"), "font-size": 11.5});
        lb.textContent = cat.length > maxChars ? cat.slice(0, maxChars - 1) + "…" : cat;
        if (cat.length > maxChars) lb.appendChild(mk("title")).textContent = cat;
        svg.appendChild(lb);
      });
      const thick = Math.min(22, (band - 8) / (o.mode === "stack" ? 1 : S.length));
      const bars = mk("g", {"data-bars": "1"});
      svg.appendChild(bars);
      S.forEach((s, k) => {
        s.x.forEach((v, i) => {
          if (v === null || !isFinite(v)) return;
          let x0, x1, y;
          if (o.mode === "stack") {
            const prev = S.slice(0, k).reduce((a, q) => a + Math.max(0, q.x[i] || 0), 0);
            x0 = X(prev); x1 = X(prev + v); y = pad.t + band * (i + 0.5) - thick / 2;
          } else {
            x0 = X(Math.min(0, v)); x1 = X(Math.max(0, v));
            y = pad.t + band * i + (band - thick * S.length) / 2 + k * thick;
          }
          const r = mk("rect", {x: Math.min(x0, x1), y, width: Math.max(1, Math.abs(x1 - x0) - (o.mode === "stack" ? 2 : 0)),
                                height: Math.max(1, thick - (o.mode === "group" ? 2 : 0)), fill: col(s.color), rx: 2});
          r.style.cursor = "default";
          r.addEventListener("pointerenter", ev => {
            const box = document.createElement("div");
            const head = document.createElement("div");
            head.style.cssText = "color:var(--muted);margin-bottom:4px";
            head.textContent = cats[i];
            box.appendChild(head);
            box.appendChild(this.tipRow(col(s.color), s.name, o.fmt(v, 2)));
            const rect = svg.getBoundingClientRect();
            this.showTip(box, ev.clientX - rect.left, y + thick);
          });
          r.addEventListener("pointerleave", () => this.hideTip());
          bars.appendChild(r);
          if (o.labelEnds && o.mode === "group") {
            const t = mk("text", {x: (v >= 0 ? x1 + 5 : x0 - 5), y: y + thick / 2 + 3.5,
                                  "text-anchor": v >= 0 ? "start" : "end", fill: css("--muted"),
                                  "font-size": 10, "font-family": "var(--mono)"});
            t.textContent = o.fmt(v, 1);
            svg.appendChild(t);
          }
        });
      });
    }
  }

  /* vertical bars / waterfall: items [{label, value, color}] */
  class BarsV extends Chart {
    render(svg, W, H) {
      const o = this.opts, items = o.items;
      const pad = {l: 50, r: 12, t: 12, b: o.tall ? 56 : 30};
      let run = 0;
      const spans = items.map(d => {
        if (!o.waterfall) return [Math.min(0, d.value), Math.max(0, d.value)];
        if (d.total) return [Math.min(0, d.value), Math.max(0, d.value)];
        const a = run, b = run + d.value;
        run = b;
        return [Math.min(a, b), Math.max(a, b)];
      });
      let lo = Math.min(0, ...spans.map(s => s[0])), hi = Math.max(0, ...spans.map(s => s[1]));
      const ticks = niceTicks(lo, hi, 4);
      lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
      const Y = v => H - pad.b - (H - pad.t - pad.b) * (v - lo) / (hi - lo || 1);
      const band = (W - pad.l - pad.r) / items.length;
      ticks.forEach(t => {
        svg.appendChild(mk("line", {x1: pad.l, x2: W - pad.r, y1: Y(t), y2: Y(t),
                                    stroke: t === 0 ? css("--rule-strong") : css("--rule"), "stroke-width": 1}));
        const lb = mk("text", {x: pad.l - 8, y: Y(t) + 3.5, "text-anchor": "end", fill: css("--muted"),
                               "font-size": 10.5, "font-family": "var(--mono)"});
        lb.textContent = o.fmt(t);
        svg.appendChild(lb);
      });
      const thick = Math.min(30, band - 10);
      const bars = mk("g", {"data-bars": "1"});
      svg.appendChild(bars);
      items.forEach((d, i) => {
        const [a, b] = spans[i];
        const x = pad.l + band * i + (band - thick) / 2;
        if (o.waterfall && i > 0 && !items[i - 1].total) {
          const prevTop = d.total ? spans[i - 1][d.value >= 0 ? 1 : 0]
                                  : (items[i - 1].value >= 0 ? spans[i - 1][1] : spans[i - 1][0]);
          svg.appendChild(mk("line", {x1: pad.l + band * (i - 1) + (band + thick) / 2, x2: x,
                                      y1: Y(prevTop), y2: Y(prevTop),
                                      stroke: css("--muted"), "stroke-width": 1.2,
                                      "stroke-dasharray": "3 3"}));
        }
        const r = mk("rect", {x, y: Y(b), width: thick, height: Math.max(1.5, Y(a) - Y(b)),
                              fill: d.hollow ? fade(d.color, 0.22) : col(d.color), rx: 3});
        if (d.hollow || d.outline) {
          r.setAttribute("stroke", d.outline ? css("--ink") : col(d.color));
          r.setAttribute("stroke-width", 1.3);
        }
        r.addEventListener("pointerenter", ev => {
          const box = document.createElement("div");
          box.appendChild(this.tipRow(col(d.color), d.label, o.fmt(d.value, 2)));
          const rect = svg.getBoundingClientRect();
          this.showTip(box, ev.clientX - rect.left, Y(Math.max(a, b)));
        });
        r.addEventListener("pointerleave", () => this.hideTip());
        bars.appendChild(r);
        if (o.valueLabels) {                     /* sign is in the number as well as the direction */
          const up = d.value >= 0;
          const vt = mk("text", {x: x + thick / 2, y: (up ? Y(b) - 6 : Y(a) + 13), "text-anchor": "middle",
                                 fill: css("--ink-2"), "font-size": 10, "font-family": "var(--mono)"});
          vt.textContent = o.fmt(d.value, 1);
          svg.appendChild(vt);
        }
        const lbl = mk("text", {x: pad.l + band * (i + 0.5), y: H - (o.tall ? 34 : 10),
                                "text-anchor": o.tall ? "end" : "middle", fill: css("--muted"), "font-size": 10.5});
        lbl.textContent = d.label;
        if (o.tall) lbl.setAttribute("transform", `rotate(-35 ${pad.l + band * (i + 0.5)} ${H - 34})`);
        svg.appendChild(lbl);
      });
    }
  }

  /* points [{name,color,x:[],y:[]}] with markers */
  class LineMarkers extends Chart {
    render(svg, W, H) {
      const o = this.opts, S = o.series;
      const pad = {l: 54, r: 16, t: 12, b: 34};
      const xs = S.flatMap(s => s.x), ys = S.flatMap(s => s.y);
      const xlo = Math.min(...xs), xhi = Math.max(...xs);
      let lo = Math.min(...ys), hi = Math.max(...ys);
      const ticks = niceTicks(lo, hi, 4);
      lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
      const X = v => pad.l + (W - pad.l - pad.r) * (v - xlo) / (xhi - xlo || 1);
      const Y = v => H - pad.b - (H - pad.t - pad.b) * (v - lo) / (hi - lo || 1);
      ticks.forEach(t => {
        svg.appendChild(mk("line", {x1: pad.l, x2: W - pad.r, y1: Y(t), y2: Y(t), stroke: css("--rule"), "stroke-width": 1}));
        const lb = mk("text", {x: pad.l - 8, y: Y(t) + 3.5, "text-anchor": "end", fill: css("--muted"),
                               "font-size": 10.5, "font-family": "var(--mono)"});
        lb.textContent = o.fmt(t);
        svg.appendChild(lb);
      });
      [...new Set(xs)].forEach(v => {
        const t = mk("text", {x: X(v), y: H - 12, "text-anchor": "middle", fill: css("--muted"),
                              "font-size": 10.5, "font-family": "var(--mono)"});
        t.textContent = v + "×";
        svg.appendChild(t);
      });
      if (o.xlabel) {
        const t = mk("text", {x: (pad.l + W - pad.r) / 2, y: H - 1, "text-anchor": "middle",
                              fill: css("--muted"), "font-size": 10.5});
        t.textContent = o.xlabel;
        svg.appendChild(t);
      }
      S.forEach(s => {
        let d = "";
        s.x.forEach((v, i) => { d += (d ? "L" : "M") + X(v) + " " + Y(s.y[i]); });
        svg.appendChild(mk("path", {d, fill: "none", stroke: col(s.color), "stroke-width": 2, "stroke-linejoin": "round"}));
        s.x.forEach((v, i) => {
          const c = mk("circle", {cx: X(v), cy: Y(s.y[i]), r: 4.5, fill: col(s.color),
                                  stroke: css("--surface"), "stroke-width": 2});
          const hit = mk("circle", {cx: X(v), cy: Y(s.y[i]), r: 13, fill: "transparent"});
          hit.addEventListener("pointerenter", ev => {
            const box = document.createElement("div");
            const head = document.createElement("div");
            head.style.cssText = "color:var(--muted);margin-bottom:4px";
            head.textContent = v + "× costs";
            box.appendChild(head);
            box.appendChild(this.tipRow(col(s.color), s.name, o.fmt(s.y[i], 2)));
            const rect = svg.getBoundingClientRect();
            this.showTip(box, ev.clientX - rect.left, Y(s.y[i]));
          });
          hit.addEventListener("pointerleave", () => this.hideTip());
          svg.appendChild(c);
          svg.appendChild(hit);
        });
      });
    }
  }

  global.Charts = {LineChart, BarsH, BarsV, LineMarkers, fmtPct, niceTicks, REGISTRY};
})(window);

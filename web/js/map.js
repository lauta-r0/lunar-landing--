// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// Canvas map: LOLA hillshade + km grid + 5 m data footprint + landing ellipse + classified points
// + target. A click on empty terrain picks a new target (onPickTarget); a click on a point pins it.
// World coordinates are south polar stereographic metres (x right, y up). One uniform
// metres-per-pixel factor is used on both axes, so the terrain, the ellipse, the grid
// and the scale bar always stay aligned.

const C = {
  viable: "#3DDC84",
  risky: "#FF9F43",
  not_viable: "#FF6B6B",
};

const NICE_STEPS = [250, 500, 1000, 2000, 5000, 10000];
const CLICK_SLOP_PX = 5; // a press that moves farther than this is a drag (pan), not a click

export class MapView {
  constructor({ frame, canvas, tip, overlays, onTip }) {
    this.frame = frame;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.tipEl = tip;
    this.overlays = overlays || [];
    this.onTip = onTip; // (point) => html
    this.img = null;
    this.imgBounds = null;
    this.data = null;
    this.view = null; // {cx, cy, mpp}
    this.home = null;
    this.hoverId = null;
    this.pinnedId = null;
    this.cw = 0;
    this.ch = 0;
    this.onViewChange = null;
    this.onPickTarget = null; // (x_m, y_m) => void
    this.hires = null; // {bounds, label, coarseLabel}
    this.pin = null; // [x_m, y_m] of the last picked spot, until its analysis arrives

    this._bindEvents();
    new ResizeObserver(() => this._resize()).observe(frame);
    this._resize();
  }

  /* ---------------- public API ---------------- */

  setHillshade(url, bounds) {
    if (!url || !bounds) return;
    if (this.imgUrl === url && this.img) { this.imgBounds = bounds; this.draw(); return; }
    this.imgUrl = url;
    this.imgBounds = bounds;
    const img = new Image();
    img.decoding = "async";
    img.onload = () => { this.img = img; this.draw(); };
    img.onerror = () => { this.img = null; this.imgFailed = true; this.draw(); };
    img.src = url;
  }

  /** Extent of the 5 m/px tile (schema 1.5 map.hires_bounds_xy_m) and the labels of the two levels. */
  setHires(bounds, label, coarseLabel) {
    this.hires = Array.isArray(bounds) && bounds.length === 4 ? { bounds, label, coarseLabel } : null;
    this.draw();
  }

  /** Pin at a picked spot (map metres); null clears it. */
  setPin(xy) { this.pin = xy; this.draw(); }

  /** Move the view centre to a world point, keeping the zoom. */
  centerOn(x, y) {
    if (!this.view) return;
    this.view.cx = x; this.view.cy = y;
    this.draw();
  }

  /** resp = /api/analyze response. Keeps the current zoom when the target is unchanged. */
  setData(resp) {
    const prevTarget = this.data && this.data.target;
    this.data = resp;
    this.points = resp.points || [];
    this.hoverId = null;
    this.pinnedId = null;
    this._hideTip();
    const e = resp.inputs && resp.inputs.ellipse;
    const n = Math.max(1, this.points.length);
    const area = e ? Math.PI * e.semi_major_m * e.semi_minor_m : 1e6;
    this.spacingM = Math.sqrt(area / n);
    const vb = resp.map && resp.map.view_bounds_xy_m;
    this.home = vb
      ? { cx: (vb[0] + vb[2]) / 2, cy: (vb[1] + vb[3]) / 2, w: vb[2] - vb[0], h: vb[3] - vb[1] }
      : { cx: resp.target.x_m, cy: resp.target.y_m, w: 5000, h: 3333 };
    const sameTarget = prevTarget && this.view &&
      Math.abs(prevTarget.x_m - resp.target.x_m) < 1 && Math.abs(prevTarget.y_m - resp.target.y_m) < 1;
    if (!sameTarget) this.resetView(false);
    // the picked spot is now the analysed target: its crosshair replaces the pin
    if (this.pin && Math.hypot(this.pin[0] - resp.target.x_m, this.pin[1] - resp.target.y_m) < 30) this.pin = null;
    this.draw();
  }

  resetView(redraw = true) {
    if (!this.home || !this.cw) return;
    const mpp = Math.max(this.home.w / this.cw, this.home.h / this.ch);
    this.view = { cx: this.home.cx, cy: this.home.cy, mpp };
    if (redraw) this.draw();
  }

  zoom(factor, px = this.cw / 2, py = this.ch / 2) {
    if (!this.view) return;
    const [wx, wy] = this.toWorld(px, py);
    const homeMpp = Math.max(this.home.w / this.cw, this.home.h / this.ch);
    const mpp = Math.min(homeMpp * 8, Math.max(homeMpp / 8, this.view.mpp / factor));
    this.view.mpp = mpp;
    // keep the world point under the cursor fixed
    this.view.cx = wx - (px - this.cw / 2) * mpp;
    this.view.cy = wy + (py - this.ch / 2) * mpp;
    this.draw();
  }

  pan(dxPx, dyPx) {
    if (!this.view) return;
    this.view.cx -= dxPx * this.view.mpp;
    this.view.cy += dyPx * this.view.mpp;
    this.draw();
  }

  /** Clockwise angle (deg) from screen-up to local north at the target. */
  northAngleDeg() {
    if (!this.data) return 0;
    const t = this.data.target;
    return (Math.atan2(t.x_m, t.y_m) * 180) / Math.PI;
  }

  toPx(x, y) {
    const v = this.view;
    return [this.cw / 2 + (x - v.cx) / v.mpp, this.ch / 2 - (y - v.cy) / v.mpp];
  }

  toWorld(px, py) {
    const v = this.view;
    return [v.cx + (px - this.cw / 2) * v.mpp, v.cy - (py - this.ch / 2) * v.mpp];
  }

  /* ---------------- drawing ---------------- */

  _resize() {
    const r = this.frame.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(r.width));
    const h = Math.max(1, Math.round(r.height));
    if (w === this.cw && h === this.ch && this.dpr === dpr) return;
    const oldCw = this.cw;
    this.cw = w; this.ch = h; this.dpr = dpr;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    if (this.view && oldCw) {
      // keep the same visible width in metres
      this.view.mpp *= oldCw / w;
    } else if (this.home) {
      this.resetView(false);
    }
    this.draw();
  }

  draw() {
    const ctx = this.ctx;
    const { cw, ch } = this;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = "#050505";
    ctx.fillRect(0, 0, cw, ch);
    if (!this.view || !this.data) { this._notify(); return; }

    // 1. hillshade, placed by its bounds with the same metres-per-pixel on both axes
    if (this.img && this.imgBounds) {
      const b = this.imgBounds;
      const [x0, y0] = this.toPx(b[0], b[3]);
      const [x1, y1] = this.toPx(b[2], b[1]);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(this.img, x0, y0, x1 - x0, y1 - y0);
      // grade the image darker so type and points land cleanly
      ctx.fillStyle = "rgba(0,0,0,0.46)";
      ctx.fillRect(Math.max(0, x0), Math.max(0, y0), Math.min(cw, x1) - Math.max(0, x0), Math.min(ch, y1) - Math.max(0, y0));
    }

    // 2. km grid relative to the target
    this._drawGrid();

    // 2b. footprint of the 5 m/px data (thin, dashed: it must not compete with the points)
    this._drawHires();

    // 3. landing ellipse
    const poly = this.data.map && this.data.map.ellipse_polygon_xy_m;
    if (poly && poly.length > 2) {
      ctx.beginPath();
      poly.forEach(([x, y], i) => { const [px, py] = this.toPx(x, y); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
      ctx.closePath();
      ctx.fillStyle = "rgba(255,255,255,0.05)";
      ctx.fill();
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 1.25;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 4. points
    const r = this._markerRadius();
    this._r = r;
    const pad = 12;
    for (const p of this.points) {
      const [px, py] = this.toPx(p.x_m, p.y_m);
      if (px < -pad || py < -pad || px > cw + pad || py > ch + pad) continue;
      drawMarker(ctx, p.class, px, py, r);
    }

    // 4b. pin at a picked spot while its analysis runs (or when it was outside the data)
    if (this.pin) {
      const [qx, qy] = this.toPx(this.pin[0], this.pin[1]);
      drawPin(ctx, qx, qy);
    }

    // 5. target crosshair (no text label, so it never covers points)
    const t = this.data.target;
    const [tx, ty] = this.toPx(t.x_m, t.y_m);
    drawTarget(ctx, tx, ty);

    // 6. hover / pinned highlight
    const hid = this.pinnedId ?? this.hoverId;
    if (hid != null) {
      const p = this.points.find((q) => q.id === hid);
      if (p) {
        const [px, py] = this.toPx(p.x_m, p.y_m);
        ctx.beginPath();
        ctx.arc(px, py, r + 5, 0, Math.PI * 2);
        ctx.lineWidth = 3; ctx.strokeStyle = "#000"; ctx.stroke();
        ctx.lineWidth = 1.5; ctx.strokeStyle = "#fff"; ctx.stroke();
      }
    }
    this._notify();
  }

  _notify() { if (this.onViewChange) this.onViewChange(this); }

  _markerRadius() {
    const spacingPx = (this.spacingM || 50) / this.view.mpp;
    return Math.max(2.5, Math.min(6.5, spacingPx * 0.4));
  }

  gridStep() {
    const widthM = this.cw * this.view.mpp;
    return NICE_STEPS.find((s) => widthM / s <= 8) || 20000;
  }

  /** Scale bar length in metres and pixels. */
  scaleBar() {
    if (!this.view) return null;
    const targetPx = Math.min(140, this.cw * 0.22);
    const m = targetPx * this.view.mpp;
    const choices = [100, 200, 250, 500, 1000, 2000, 5000, 10000, 20000];
    let best = choices[0];
    for (const c of choices) if (c <= m) best = c;
    return { m: best, px: best / this.view.mpp };
  }

  _overlayRects() {
    const fr = this.frame.getBoundingClientRect();
    return this.overlays
      .filter((el) => el && !el.hidden && el.offsetParent !== null)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { x0: r.left - fr.left - 6, y0: r.top - fr.top - 6, x1: r.right - fr.left + 6, y1: r.bottom - fr.top + 6 };
      });
  }

  _drawGrid() {
    const ctx = this.ctx;
    const { cw, ch } = this;
    const t = this.data.target;
    const step = this.gridStep();
    const [wx0, wy1] = this.toWorld(0, 0);
    const [wx1, wy0] = this.toWorld(cw, ch);
    const rects = this._overlayRects();
    const hits = (x0, y0, x1, y1) => rects.some((r) => x0 < r.x1 && x1 > r.x0 && y0 < r.y1 && y1 > r.y0);
    const label = (k) => `${k > 0 ? "+" : "−"}${Math.abs((k * step) / 1000)} km`;

    ctx.font = "500 11px Barlow, Arial, sans-serif";
    ctx.textBaseline = "alphabetic";
    const gridLine = (x0, y0, x1, y1) => {
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.16)";
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    };

    const kx0 = Math.ceil((wx0 - t.x_m) / step), kx1 = Math.floor((wx1 - t.x_m) / step);
    for (let k = kx0; k <= kx1; k++) {
      if (k === 0) continue;
      const [px] = this.toPx(t.x_m + k * step, 0);
      const x = Math.round(px) + 0.5;
      gridLine(x, 0, x, ch);
      const txt = label(k);
      const w = ctx.measureText(txt).width;
      const lx = x + 6, ly = ch - 8;
      if (!hits(lx - 3, ly - 12, lx + w + 3, ly + 3)) textWithHalo(ctx, txt, lx, ly);
    }
    const ky0 = Math.ceil((wy0 - t.y_m) / step), ky1 = Math.floor((wy1 - t.y_m) / step);
    for (let k = ky0; k <= ky1; k++) {
      if (k === 0) continue;
      const [, py] = this.toPx(0, t.y_m + k * step);
      const y = Math.round(py) + 0.5;
      gridLine(0, y, cw, y);
      const txt = label(k);
      const w = ctx.measureText(txt).width;
      const lx = 8, ly = y + 15;
      if (!hits(lx - 3, ly - 12, lx + w + 3, ly + 3)) textWithHalo(ctx, txt, lx, ly);
    }
  }

  _drawHires() {
    if (!this.hires) return;
    const ctx = this.ctx;
    const { cw, ch } = this;
    const b = this.hires.bounds;
    const [l, t] = this.toPx(b[0], b[3]);
    const [r, bt] = this.toPx(b[2], b[1]);
    if (r < 0 || l > cw || bt < 0 || t > ch) return; // tile entirely off screen
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(255,255,255,0.6)";
    ctx.strokeRect(Math.round(l) + 0.5, Math.round(t) + 0.5, Math.round(r - l), Math.round(bt - t));
    ctx.setLineDash([]);

    // Labels sit on one visible edge: "5 M DATA" just inside it, "20 M DATA" just outside it.
    const inTxt = labelFor(this.hires.label, "5 M DATA");
    const outTxt = labelFor(this.hires.coarseLabel, "20 M DATA");
    ctx.font = "600 10px Barlow, Arial, sans-serif";
    ctx.textBaseline = "middle";
    const rects = this._overlayRects();
    const fits = (x0, y0, x1, y1) => x0 >= 4 && y0 >= 4 && x1 <= cw - 4 && y1 <= ch - 4 &&
      !rects.some((q) => x0 < q.x1 && x1 > q.x0 && y0 < q.y1 && y1 > q.y0);
    const wIn = spacedWidth(ctx, inTxt), wOut = spacedWidth(ctx, outTxt), H = 10, g = 7;
    const wMax = Math.max(wIn, wOut);
    const segX = [Math.max(l, 0), Math.min(r, cw)], segY = [Math.max(t, 0), Math.min(bt, ch)];
    // candidate spots along each visible edge (near both ends, then the middle): [inside box, outside box]
    const along = (a0, a1, w) => [a0 + 12, a1 - 12 - w, (a0 + a1) / 2 - w / 2];
    const cands = [];
    if (t >= 0 && t <= ch) for (const x of along(segX[0], segX[1], wMax)) cands.push([[x, t + g, wIn], [x, t - g - H, wOut]]);
    if (bt >= 0 && bt <= ch) for (const x of along(segX[0], segX[1], wMax)) cands.push([[x, bt - g - H, wIn], [x, bt + g, wOut]]);
    if (l >= 0 && l <= cw) for (const y of along(segY[0], segY[1], H)) cands.push([[l + g, y, wIn], [l - g - wOut, y, wOut]]);
    if (r >= 0 && r <= cw) for (const y of along(segY[0], segY[1], H)) cands.push([[r - g - wIn, y, wIn], [r + g, y, wOut]]);
    for (const [a, o] of cands) {
      if (!fits(a[0], a[1], a[0] + a[2], a[1] + H)) continue;
      spacedLabel(ctx, inTxt, a[0], a[1] + H / 2);
      if (fits(o[0], o[1], o[0] + o[2], o[1] + H)) spacedLabel(ctx, outTxt, o[0], o[1] + H / 2);
      break;
    }
    ctx.restore();
  }

  /* ---------------- interaction ---------------- */

  _pick(px, py) {
    if (!this.points || !this.view) return null;
    const maxD = Math.max(9, (this._r || 5) * 1.8);
    let best = null, bestD = maxD * maxD;
    for (const p of this.points) {
      const [x, y] = this.toPx(p.x_m, p.y_m);
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bestD) { bestD = d; best = p; }
    }
    return best;
  }

  _showTip(p) {
    if (!p || !this.onTip) return this._hideTip();
    const pinned = this.pinnedId === p.id;
    this.tipEl.innerHTML = this.onTip(p) + (pinned
      ? '<button type="button" class="btn btn--sm tip-use">Set as target</button><button type="button" class="tip-close" aria-label="Close details">✕</button>'
      : "");
    this.tipEl.classList.toggle("is-pinned", pinned);
    this.tipEl.hidden = false;
    const [px, py] = this.toPx(p.x_m, p.y_m);
    const tw = this.tipEl.offsetWidth, th = this.tipEl.offsetHeight;
    let x = px + 16, y = py - th / 2;
    if (x + tw > this.cw - 8) x = px - tw - 16;
    x = Math.max(8, Math.min(this.cw - tw - 8, x));
    y = Math.max(8, Math.min(this.ch - th - 8, y));
    this.tipEl.style.left = `${x}px`;
    this.tipEl.style.top = `${y}px`;
    const close = this.tipEl.querySelector(".tip-close");
    if (close) close.addEventListener("click", () => { this.pinnedId = null; this._hideTip(); this.draw(); });
    const use = this.tipEl.querySelector(".tip-use");
    if (use) use.addEventListener("click", () => { this.pinnedId = null; this._hideTip(); this.draw(); this._pickTarget(p.x_m, p.y_m); });
  }

  _hideTip() { this.tipEl.hidden = true; this.tipEl.classList.remove("is-pinned"); }

  _pickTarget(x, y) {
    if (this.onPickTarget) this.onPickTarget(x, y);
  }

  _bindEvents() {
    const cv = this.canvas;
    let drag = null;

    cv.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, moved: false, id: e.pointerId };
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener("pointermove", (e) => {
      const rect = cv.getBoundingClientRect();
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (drag.moved || Math.hypot(dx, dy) > CLICK_SLOP_PX) {
          drag.moved = true;
          cv.style.cursor = "grabbing";
          this.pan(dx, dy);
          drag.x = e.clientX; drag.y = e.clientY;
          if (this.pinnedId != null) this._showTip(this.points.find((q) => q.id === this.pinnedId));
          return;
        }
      }
      if (this.pinnedId != null || e.pointerType === "touch") return;
      const p = this._pick(px, py);
      const id = p ? p.id : null;
      if (id !== this.hoverId) {
        this.hoverId = id;
        p ? this._showTip(p) : this._hideTip();
        this.draw();
      }
    });
    cv.addEventListener("pointerup", (e) => {
      cv.style.cursor = "";
      const wasDrag = drag && drag.moved;
      drag = null;
      if (wasDrag) return;
      if (!this.view) return;
      const rect = cv.getBoundingClientRect();
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      const p = this._pick(px, py);
      if (p) {
        this.pinnedId = this.pinnedId === p.id ? null : p.id;
        this.hoverId = p.id;
        this.pinnedId != null ? this._showTip(p) : this._hideTip();
      } else if (this.pinnedId != null) {
        // the first click away from a pinned point only closes its details
        this.pinnedId = null; this.hoverId = null; this._hideTip();
      } else {
        this.hoverId = null; this._hideTip();
        const [wx, wy] = this.toWorld(px, py);
        this._pickTarget(wx, wy);
      }
      this.draw();
    });
    cv.addEventListener("pointerleave", () => {
      if (this.pinnedId == null && this.hoverId != null) { this.hoverId = null; this._hideTip(); this.draw(); }
    });
    cv.addEventListener("wheel", (e) => {
      if (!this.view) return;
      e.preventDefault();
      const rect = cv.getBoundingClientRect();
      this.zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - rect.left, e.clientY - rect.top);
      if (this.pinnedId != null) this._showTip(this.points.find((q) => q.id === this.pinnedId));
    }, { passive: false });
    cv.addEventListener("keydown", (e) => {
      const step = 60;
      const k = e.key;
      if (k === "ArrowLeft") this.pan(step, 0);
      else if (k === "ArrowRight") this.pan(-step, 0);
      else if (k === "ArrowUp") this.pan(0, step);
      else if (k === "ArrowDown") this.pan(0, -step);
      else if (k === "+" || k === "=") this.zoom(1.25);
      else if (k === "-" || k === "_") this.zoom(1 / 1.25);
      else if (k === "0") this.resetView();
      else if (k === "Enter" && this.view) this._pickTarget(this.view.cx, this.view.cy);
      else if (k === "Escape") { this.pinnedId = null; this.hoverId = null; this._hideTip(); this.draw(); }
      else return;
      e.preventDefault();
      if (this.pinnedId != null) this._showTip(this.points.find((q) => q.id === this.pinnedId));
    });
  }
}

/* ---------------- marker shapes ---------------- */

/** Same filled shapes for every point, whatever DEM resolution it comes from (the badge and the tooltip say that). */
export function drawMarker(ctx, cls, x, y, r) {
  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  if (cls === "viable") {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = C.viable; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = "#000"; ctx.stroke();
  } else if (cls === "risky") {
    const s = r * 1.15;
    ctx.beginPath();
    ctx.moveTo(x, y - s);
    ctx.lineTo(x + s * 0.95, y + s * 0.7);
    ctx.lineTo(x - s * 0.95, y + s * 0.7);
    ctx.closePath();
    ctx.fillStyle = C.risky; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = "#000"; ctx.stroke();
  } else {
    const s = r * 0.8;
    ctx.beginPath();
    ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s);
    ctx.moveTo(x + s, y - s); ctx.lineTo(x - s, y + s);
    ctx.lineWidth = Math.max(3.2, r * 0.85); ctx.strokeStyle = "#000"; ctx.stroke();
    ctx.lineWidth = Math.max(1.6, r * 0.42); ctx.strokeStyle = C.not_viable; ctx.stroke();
  }
  ctx.restore();
}

/** Map pin whose tip touches (x, y). */
function drawPin(ctx, x, y) {
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.bezierCurveTo(x - 2, y - 6, x - 8, y - 11, x - 8, y - 17);
  ctx.arc(x, y - 17, 8, Math.PI, 0);
  ctx.bezierCurveTo(x + 8, y - 11, x + 2, y - 6, x, y);
  ctx.closePath();
  ctx.fillStyle = "#fff"; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = "#000"; ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y - 17, 3, 0, Math.PI * 2); ctx.fillStyle = "#000"; ctx.fill();
  ctx.restore();
}

function drawTarget(ctx, x, y) {
  ctx.save();
  ctx.lineCap = "butt";
  const arms = () => {
    ctx.beginPath();
    ctx.moveTo(x, y - 20); ctx.lineTo(x, y - 11);
    ctx.moveTo(x, y + 11); ctx.lineTo(x, y + 20);
    ctx.moveTo(x - 20, y); ctx.lineTo(x - 11, y);
    ctx.moveTo(x + 11, y); ctx.lineTo(x + 20, y);
  };
  ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.stroke();
  ctx.lineWidth = 1.8; ctx.strokeStyle = "#fff"; ctx.stroke();
  arms(); ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.stroke();
  arms(); ctx.lineWidth = 1.8; ctx.strokeStyle = "#fff"; ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
  ctx.restore();
}

function textWithHalo(ctx, txt, x, y) {
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0,0,0,0.85)";
  ctx.strokeText(txt, x, y);
  ctx.fillStyle = "#d4d4dc";
  ctx.fillText(txt, x, y);
}

const LABEL_TRACKING = 1.2; // px between letters of the small uppercase map labels

/** "LOLA 5 m/px" → "5 M DATA" (fallback when the API gives no label). */
function labelFor(label, fallback) {
  const m = /([\d.]+)\s*m\/px/i.exec(label || "");
  return m ? `${m[1]} M DATA` : fallback;
}

function spacedWidth(ctx, txt) {
  return ctx.measureText(txt).width + (txt.length - 1) * LABEL_TRACKING;
}

/** Small letter-spaced, low-contrast label with a dark halo, left-aligned at (x, y). */
function spacedLabel(ctx, txt, x, y) {
  const xs = [];
  let cx = x;
  for (const c of txt) { xs.push(cx); cx += ctx.measureText(c).width + LABEL_TRACKING; }
  const chars = [...txt];
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0,0,0,0.7)";
  chars.forEach((c, i) => ctx.strokeText(c, xs[i], y)); // halo first, so it never covers a letter
  ctx.fillStyle = "rgba(255,255,255,0.72)";
  chars.forEach((c, i) => ctx.fillText(c, xs[i], y));
}

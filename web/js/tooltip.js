// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// One floating tooltip for every element with [data-tip]; shown on hover and on keyboard focus.

export function initTooltips(tip) {
  let owner = null;

  const show = (el) => {
    const text = el.dataset.tip;
    if (!text) return;
    owner = el;
    tip.textContent = text;
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = r.left + r.width / 2 - tw / 2;
    let y = r.bottom + 8;
    if (y + th > window.innerHeight - 8) y = r.top - th - 8;
    x = Math.max(8, Math.min(window.innerWidth - tw - 8, x));
    tip.style.left = `${x}px`;
    tip.style.top = `${Math.max(8, y)}px`;
    if (!el.hasAttribute("aria-describedby")) el.setAttribute("aria-describedby", tip.id);
  };
  const hide = (el) => {
    if (el && owner !== el) return;
    owner = null;
    tip.hidden = true;
  };

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) show(el);
  });
  document.addEventListener("mouseout", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el && !el.contains(e.relatedTarget)) hide(el);
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) show(el);
  });
  document.addEventListener("focusout", (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) hide(el);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  window.addEventListener("scroll", () => hide(), { passive: true });
}

// Controller navigation for web pages shown in Batocera's built-in web view.
//
// The arrow keys (the d-pad) move a highlight between the things on the page
// that can be clicked, Enter (A) presses the highlighted one, Escape (B) leaves
// a text box. With nothing further in a direction the page scrolls instead.
// Whoever shows the page is told when a text box has the focus, through the
// "emubox" message handler ("editing" / "idle").
(function () {
  if (window.__emuboxNav) return;
  window.__emuboxNav = true;

  const CLICKABLE = 'a[href], button, input:not([type=hidden]), select, textarea, summary, label[for], ' +
    '[role=button], [role=link], [role=tab], [role=menuitem], [role=option], [role=checkbox], ' +
    '[role=radio], [role=switch], [onclick], [tabindex]:not([tabindex="-1"])';
  const NATIVE = /^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/;
  const DIRECTIONS = {ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0]};
  let current = null;

  const style = document.createElement('style');
  style.textContent = '.emubox-nav-focus { outline: 3px solid #c8f03c !important; outline-offset: 2px !important; ' +
    'box-shadow: 0 0 0 6px rgba(200, 240, 60, 0.35) !important; }';
  (document.head || document.documentElement).appendChild(style);

  function tell(what) {
    try { window.webkit.messageHandlers.emubox.postMessage(what); } catch (e) { /* not in our view */ }
  }

  function typing(el) {
    return !!el && (el.isContentEditable || el.tagName === 'TEXTAREA' ||
      (el.tagName === 'INPUT' && !/^(button|submit|reset|checkbox|radio|image|file|range|color)$/i.test(el.type)));
  }

  // The element's box, or null when it cannot be seen or used.
  function box(el) {
    if (el.disabled || el.getAttribute('aria-hidden') === 'true') return null;
    const r = el.getBoundingClientRect();
    if (r.width < 3 || r.height < 3) return null;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || s.pointerEvents === 'none' || +s.opacity === 0) return null;
    return r;
  }

  function onScreen(r) {
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  }

  // On screen, is it the thing you would actually hit there (not under a pop-up)?
  function reachable(el, r) {
    if (!onScreen(r)) return true;
    const x = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 1);
    const hit = document.elementFromPoint(x, y);
    return !hit || el.contains(hit) || hit.contains(el);
  }

  function candidates() {
    const found = [];
    for (const el of document.querySelectorAll(CLICKABLE)) {
      if (el === current) continue;
      const r = box(el);
      if (r && reachable(el, r)) found.push([el, r]);
    }
    return found;
  }

  function highlight(el) {
    if (current) current.classList.remove('emubox-nav-focus');
    current = el;
    if (!el) return;
    el.classList.add('emubox-nav-focus');
    if (document.activeElement && document.activeElement !== el) document.activeElement.blur();
    try { el.focus({preventScroll: true}); } catch (e) { /* not focusable: the highlight is enough */ }
    el.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const r = el.getBoundingClientRect();   // keep some of the page visible beyond it
    if (r.top < 60) scrollBy(0, r.top - 60); else if (r.bottom > innerHeight - 60) scrollBy(0, r.bottom - innerHeight + 60);
  }

  function move(dx, dy) {
    const all = candidates();
    let from = current && current.isConnected ? box(current) : null;
    if (from && !onScreen(from)) from = null;
    if (!from) {   // nothing highlighted here yet: start with the first thing on screen
      let first = null, best = Infinity;
      for (const [el, r] of all) {
        if (!onScreen(r) || r.top < 0) continue;
        const score = r.top * 4 + r.left;
        if (score < best) { best = score; first = el; }
      }
      if (first) highlight(first); else if (dy) scrollBy(0, dy * innerHeight * 0.6);
      return;
    }
    const reach = dy ? innerHeight * 0.9 : innerWidth;   // further than this: scroll, do not jump
    let next = null, best = Infinity;
    for (const [el, r] of all) {
      const gap = dx > 0 ? r.left - from.right : dx < 0 ? from.left - r.right : dy > 0 ? r.top - from.bottom : from.top - r.bottom;
      const centre = dx ? (r.left + r.width / 2 - from.left - from.width / 2) * dx
                        : (r.top + r.height / 2 - from.top - from.height / 2) * dy;
      // How far off to the side: nothing when the two overlap on the other axis.
      const side = dx ? Math.max(0, r.top - from.bottom, from.top - r.bottom)
                      : Math.max(0, r.left - from.right, from.left - r.right);
      // It has to lie beyond where we are; a little overlap is fine for things in the same row or column.
      const overlap = side ? 3 : Math.min(dx ? from.width : from.height, dx ? r.width : r.height) / 2;
      if (centre <= 2 || gap < -overlap || gap > reach) continue;
      // Left and right keep to the row; up and down take the nearest thing roughly above or below.
      const score = Math.max(gap, 0) + side * (dx ? 4 : 1) + Math.abs(dx ? r.top - from.top : r.left - from.left) * 0.1;
      if (score < best) { best = score; next = el; }
    }
    if (next) highlight(next); else if (dy) scrollBy({top: dy * innerHeight * 0.6, behavior: 'smooth'});
  }

  addEventListener('keydown', function (event) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const active = document.activeElement;
    const direction = DIRECTIONS[event.key];
    if (direction) {
      if (active && active.tagName === 'SELECT') return;
      if (typing(active) && (direction[0] || active.tagName !== 'INPUT')) return;   // the caret's keys
      event.preventDefault();
      event.stopImmediatePropagation();
      move(direction[0], direction[1]);
    } else if (event.key === 'Enter' && current && current.isConnected && !typing(active) &&
               (active !== current || !NATIVE.test(current.tagName))) {
      event.preventDefault();
      event.stopImmediatePropagation();
      current.click();
    } else if (event.key === 'Escape' && typing(active)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      active.blur();
    }
  }, true);

  addEventListener('focusin', function (event) {
    tell(typing(event.target) ? 'editing' : 'idle');
    const el = event.target.closest && event.target.closest(CLICKABLE);
    if (el && el !== current) {   // focused some other way (a click, the page itself): follow it
      if (current) current.classList.remove('emubox-nav-focus');
      current = el;
      el.classList.add('emubox-nav-focus');
    }
  }, true);
  addEventListener('focusout', function () { tell('idle'); }, true);
})();

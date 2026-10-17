/* 交互反馈：按下涟漪（鼠标 / 触摸共用 Pointer 事件）+ 触摸轻振动 */
(function () {
  const mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const reduced = function () { return mq && mq.matches; };

  /* 可产生涟漪的元素 */
  const SEL = [
    'button', '.chip', '.nav-item', '.pg-btn', '.row-more', '.row-ico', '.side-btn',
    '.win-btn', '.link-more', '.check-row', '.vtool', '.ai-tab', '.model-tab', '.detail-tab'
  ].join(',');
  const NO_RIPPLE = '.no-fx';

  function addRipple(el, x, y) {
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.width > 900) return; // 超大容器不加
    if (getComputedStyle(el).position === 'static') el.classList.add('fx-ripple-host');
    const size = Math.max(rect.width, rect.height) * 2.2;
    const span = document.createElement('span');
    span.className = 'fx-ripple';
    span.style.width = span.style.height = size + 'px';
    span.style.left = (x - rect.left - size / 2) + 'px';
    span.style.top = (y - rect.top - size / 2) + 'px';
    el.appendChild(span);
    window.setTimeout(function () { span.remove(); }, 620);
  }

  document.addEventListener('pointerdown', function (e) {
    if (e.button !== undefined && e.button !== 0) return; // 仅左键 / 触摸
    const el = e.target.closest(SEL);
    if (!el || el.disabled || el.classList.contains(NO_RIPPLE) || el.closest(NO_RIPPLE)) return;
    if (reduced()) return;
    addRipple(el, e.clientX, e.clientY);
    /* 触摸设备：轻微振动反馈（不支持的设备自动忽略） */
    if (e.pointerType === 'touch' && navigator.vibrate) navigator.vibrate(8);
  }, { passive: true });

  /* 卡片类元素按下时轻微下沉（不做涟漪，避免大范围重绘） */
  document.addEventListener('pointerdown', function (e) {
    const card = e.target.closest('.stat-card, .mcp-stat, .tips-card, .chip, .letter-avatar');
    if (!card || reduced()) return;
    card.style.transform = 'scale(.985)';
    const up = function () {
      card.style.transform = '';
      document.removeEventListener('pointerup', up);
      document.removeEventListener('pointercancel', up);
    };
    document.addEventListener('pointerup', up);
    document.addEventListener('pointercancel', up);
  }, { passive: true });
})();

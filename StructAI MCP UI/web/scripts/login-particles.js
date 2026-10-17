/* 登录页左侧粒子背景（P183）
   - 粒子缓慢漂移 + 近邻连线；光标附近粒子被推开并连向光标
   - DPR 感知、容器尺寸变化自适应、页面隐藏时暂停
   - `prefers-reduced-motion` ⇒ 静态星点（不跑动画）
   - 零依赖，只操作 canvas */
(function () {
  const DENSITY = 1 / 4200;      // 每平方 CSS 像素的粒子数（约翻倍）
  const MAX_PARTICLES = 280;
  const MIN_PARTICLES = 56;
  const LINK_DISTANCE = 160;      // 粒子互联距离
  const CURSOR_RADIUS = 190;      // 光标影响半径
  const CURSOR_PUSH = 0.85;       // 推开强度
  const SPEED = 0.62;             // 基础漂移速度（每帧，约为原来的 4 倍）
  const DAMPING = 0.94;           // 只衰减「光标冲量」，不衰减基础漂移
  const DOT_MIN = 1.4;
  const DOT_MAX = 3.8;

  function create(canvas, host) {
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return { destroy: function () {} };

    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 0;
    let height = 0;
    let dpr = 1;
    let particles = [];
    let frame = 0;
    let running = true;
    const pointer = { x: -9999, y: -9999, active: false };

    function resize() {
      /* ⚠️ 用 offsetWidth/offsetHeight（**布局**尺寸），不用 getBoundingClientRect：
         外层 `.app` 有 transform:scale(--ui-zoom)，getBoundingClientRect 返回的是
         **视觉**尺寸（已乘 zoom）⇒ canvas 会只铺满 80%。 */
      width = Math.max(1, host.offsetWidth);
      height = Math.max(1, host.offsetHeight);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      /* ⚠️ **不写** inline style 宽高：CSS 的 `width:100%;height:100%` 已经在
         父容器（含 transform:scale）里解析正确；只设**背板**像素尺寸。 */
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function seed() {
      const target = Math.max(
        MIN_PARTICLES,
        Math.min(MAX_PARTICLES, Math.round(width * height * DENSITY))
      );
      particles = [];
      for (let i = 0; i < target; i += 1) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * SPEED,   // 基础漂移（恒定）
          vy: (Math.random() - 0.5) * SPEED,
          ix: 0,                                // 光标冲量（衰减）
          iy: 0,
          r: DOT_MIN + Math.random() * (DOT_MAX - DOT_MIN),
          a: 0.25 + Math.random() * 0.45
        });
      }
    }

    function step() {
      if (!running) return;
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < particles.length; i += 1) {
        const p = particles[i];

        if (!reduce) {
          /* 光标推开：写入**冲量**分量（基础漂移不受影响） */
          if (pointer.active) {
            const dx = p.x - pointer.x;
            const dy = p.y - pointer.y;
            const dist2 = dx * dx + dy * dy;
            if (dist2 < CURSOR_RADIUS * CURSOR_RADIUS && dist2 > 0.01) {
              const dist = Math.sqrt(dist2);
              const force = (1 - dist / CURSOR_RADIUS) * CURSOR_PUSH;
              p.ix += (dx / dist) * force;
              p.iy += (dy / dist) * force;
            }
          }

          /* 积分：恒定漂移 + 衰减冲量 */
          p.x += p.vx + p.ix;
          p.y += p.vy + p.iy;
          p.ix *= DAMPING;
          p.iy *= DAMPING;
          if (Math.abs(p.ix) < 0.01) p.ix = 0;
          if (Math.abs(p.iy) < 0.01) p.iy = 0;

          /* 环绕边界 */
          if (p.x < -8) p.x = width + 8;
          if (p.x > width + 8) p.x = -8;
          if (p.y < -8) p.y = height + 8;
          if (p.y > height + 8) p.y = -8;
        }

        /* 粒子本体 */
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(180, 214, 255, ' + p.a + ')';
        ctx.fill();
      }

      /* 近邻连线 */
      for (let i = 0; i < particles.length; i += 1) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j += 1) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist2 = dx * dx + dy * dy;
          if (dist2 > LINK_DISTANCE * LINK_DISTANCE) continue;
          const alpha = (1 - Math.sqrt(dist2) / LINK_DISTANCE) * 0.34;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = 'rgba(140, 190, 255, ' + alpha.toFixed(3) + ')';
          ctx.lineWidth = 1.1;
          ctx.stroke();
        }
      }

      /* 光标连线（更亮） */
      if (pointer.active) {
        for (let i = 0; i < particles.length; i += 1) {
          const p = particles[i];
          const dx = p.x - pointer.x;
          const dy = p.y - pointer.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > CURSOR_RADIUS) continue;
          const alpha = (1 - dist / CURSOR_RADIUS) * 0.60;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(pointer.x, pointer.y);
          ctx.strokeStyle = 'rgba(120, 185, 255, ' + alpha.toFixed(3) + ')';
          ctx.lineWidth = 1.4;
          ctx.stroke();
        }
        /* 光标光晕 */
        const glow = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 62);
        glow.addColorStop(0, 'rgba(96, 170, 255, 0.30)');
        glow.addColorStop(1, 'rgba(96, 170, 255, 0)');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(pointer.x, pointer.y, 62, 0, Math.PI * 2);
        ctx.fill();
      }

      frame = window.requestAnimationFrame(step);
    }

    function onMove(event) {
      const rect = host.getBoundingClientRect();
      /* clientX 是**视觉**坐标；换算回布局坐标要除以 zoom（= 视觉宽 / 布局宽）。 */
      const scale = rect.width > 0 ? rect.width / Math.max(1, host.offsetWidth) : 1;
      pointer.x = (event.clientX - rect.left) / scale;
      pointer.y = (event.clientY - rect.top) / scale;
      pointer.active = pointer.x >= 0 && pointer.y >= 0 && pointer.x <= width && pointer.y <= height;
    }

    function onLeave() {
      pointer.active = false;
    }

    function onVisibility() {
      if (document.hidden) {
        running = false;
        window.cancelAnimationFrame(frame);
      } else if (!running) {
        running = true;
        frame = window.requestAnimationFrame(step);
      }
    }

    const observer = 'ResizeObserver' in window
      ? new ResizeObserver(function () { resize(); })
      : null;

    resize();
    /* ⚠️ 首帧时父容器可能尚未完成布局（实测 canvas 尺寸偏小）⇒ 下一帧再量一次 */
    window.requestAnimationFrame(function () { resize(); });
    if (observer) observer.observe(host);
    window.addEventListener('resize', resize);
    host.addEventListener('pointermove', onMove);
    host.addEventListener('pointerleave', onLeave);
    document.addEventListener('visibilitychange', onVisibility);
    frame = window.requestAnimationFrame(step);

    return {
      destroy: function () {
        running = false;
        window.cancelAnimationFrame(frame);
        window.removeEventListener('resize', resize);
        host.removeEventListener('pointermove', onMove);
        host.removeEventListener('pointerleave', onLeave);
        document.removeEventListener('visibilitychange', onVisibility);
        if (observer) observer.disconnect();
        ctx.clearRect(0, 0, width, height);
      }
    };
  }

  window.LoginParticles = { create: create };
})();

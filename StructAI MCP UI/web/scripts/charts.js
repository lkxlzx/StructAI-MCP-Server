/* 折线图（纯 SVG 手绘，按容器实际像素绘制，随窗口尺寸重绘） */
(function () {
  function smoothPath(pts) {
    if (!pts.length) return '';
    if (pts.length === 1) return 'M' + pts[0].x + ' ' + pts[0].y;
    let d = 'M' + pts[0].x.toFixed(1) + ' ' + pts[0].y.toFixed(1);
    const t = 0.2;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || pts[i + 1];
      const c1x = p1.x + (p2.x - p0.x) * t, c1y = p1.y + (p2.y - p0.y) * t;
      const c2x = p2.x - (p3.x - p1.x) * t, c2y = p2.y - (p3.y - p1.y) * t;
      d += 'C' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) +
        ' ' + p2.x.toFixed(1) + ' ' + p2.y.toFixed(1);
    }
    return d;
  }

  function line(container, cfg) {
    function draw() {
      const w = container.clientWidth, h = container.clientHeight;
      if (w < 60 || h < 60) return;
      const padL = 44, padR = 10, padT = 4, padB = 26;
      const cw = w - padL - padR, ch = h - padT - padB;
      const maxV = Math.max.apply(null, cfg.yTicks) || 1;
      const n = cfg.xLabels.length;
      const xAt = function (i) { return padL + (n === 1 ? cw / 2 : cw * i / (n - 1)); };
      const yAt = function (v) { return padT + ch - (v / maxV) * ch; };
      let s = '';
      cfg.yTicks.forEach(function (tk) {
        const y = yAt(tk).toFixed(1);
        s += '<line x1="' + padL + '" y1="' + y + '" x2="' + (w - padR) + '" y2="' + y +
          '" stroke="#EDF1F7" stroke-width="1"/>';
        s += '<text x="' + (padL - 14) + '" y="' + (Number(y) + 5).toFixed(1) +
          '" text-anchor="end">' + tk + '</text>';
      });
      cfg.xLabels.forEach(function (lb, i) {
        s += '<text x="' + xAt(i).toFixed(1) + '" y="' + (padT + ch + 22).toFixed(1) +
          '" text-anchor="middle">' + lb + '</text>';
      });
      cfg.series.forEach(function (se) {
        const pts = se.data.map(function (v, i) { return { x: xAt(i), y: yAt(v) }; });
        s += '<path d="' + smoothPath(pts) + '" fill="none" stroke="' + se.color +
          '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
      });

      container.innerHTML = '<svg class="chart-svg" width="' + w + '" height="' + h +
        '" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' + s + '</svg>';
    }

    draw();
    if (window.ResizeObserver) {
      if (container.__chartRO) container.__chartRO.disconnect();
      container.__chartRO = new ResizeObserver(draw);
      container.__chartRO.observe(container);
    } else {
      window.addEventListener('resize', draw);
    }
  }

  window.Charts = { line: line };
})();

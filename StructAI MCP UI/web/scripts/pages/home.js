/* 首页 */
(function () {
  /* 横幅右侧桥梁插画（与稿一致：淡蓝、渐隐到白） */
  const ART =
    '<svg viewBox="0 0 900 108" preserveAspectRatio="xMaxYMid slice">' +
    '<defs>' +
    '<linearGradient id="bFade" x1="0" y1="0" x2="1" y2="0">' +
    '<stop offset="0" stop-color="#FFFFFF"/><stop offset=".38" stop-color="#FFFFFF" stop-opacity=".86"/>' +
    '<stop offset=".62" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>' +
    '<linearGradient id="bTower" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="#A8C8EC"/><stop offset="1" stop-color="#8FB2DC"/></linearGradient>' +
    '<linearGradient id="bWater" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="#CFE3FB"/><stop offset="1" stop-color="#E9F2FD"/></linearGradient>' +
    '</defs>' +
    '<g opacity=".95">' +
    '<rect x="360" y="84" width="540" height="24" fill="url(#bWater)"/>' +
    '<rect x="404" y="30" width="7" height="56" rx="3" fill="url(#bTower)"/>' +
    '<rect x="452" y="30" width="7" height="56" rx="3" fill="url(#bTower)"/>' +
    '<rect x="600" y="20" width="8" height="66" rx="4" fill="url(#bTower)"/>' +
    '<rect x="656" y="20" width="8" height="66" rx="4" fill="url(#bTower)"/>' +
    '<rect x="384" y="82" width="500" height="5" rx="2.5" fill="#9FC3E7"/>' +
    '<g stroke="#A8C8EC" stroke-width="1.3" opacity=".85">' +
    '<path d="M407 34 300 82M407 34 360 82M407 34 430 82M407 34 470 82M407 34 520 82M407 34 570 82M407 34 630 82"/>' +
    '<path d="M455 34 500 82M455 34 540 82M455 34 590 82M455 34 650 82M455 34 720 82M455 34 790 82"/>' +
    '<path d="M604 24 520 82M604 24 560 82M604 24 640 82M604 24 700 82M604 24 760 82M604 24 830 82"/>' +
    '<path d="M660 24 700 82M660 24 750 82M660 24 810 82M660 24 870 82"/>' +
    '</g>' +
    '<g stroke="#BBD5F0" stroke-width="1.2" opacity=".7">' +
    '<path d="M360 92h460M360 98h460"/>' +
    '</g>' +
    '</g>' +
    '<rect x="0" y="0" width="900" height="108" fill="url(#bFade)"/>' +
    '</svg>';

  function render(shell, d) {
    const stats = d.stats.map(function (s) { return window.UI.statCard(s); }).join('');

    const legend = d.chart.series.map(function (se) {
      return '<span class="legend-item"><span class="dot" style="background:' + se.color + '"></span>' +
        window.UI.esc(se.name) + '</span>';
    }).join('');

    const events = d.events.items.map(function (e) { return window.UI.eventRow(e); }).join('');

    return '' +
      '<section class="banner">' +
        '<div class="banner-art">' + ART + '</div>' +
        '<span class="banner-accent"></span>' +
        '<div class="banner-main">' +
          '<h1 class="banner-title">' + window.UI.esc(d.banner.title) + '</h1>' +
          '<p class="banner-sub">' + window.UI.esc(d.banner.sub) + '</p>' +
        '</div>' +
        '<div class="banner-aside">' +
          '<div class="banner-aside-1">' + window.UI.esc(d.banner.aside1) + '</div>' +
          '<div class="banner-aside-2">' + window.UI.esc(d.banner.aside2) + '</div>' +
        '</div>' +
      '</section>' +

      '<section class="stat-row">' + stats + '</section>' +

      '<div class="split">' +
        '<div class="col-main">' +

          '<section class="card chart-card">' +
            '<div class="card-head">' +
              '<h2 class="card-title">' + window.UI.esc(d.chart.title) + '</h2>' +
              '<span class="select-like">' +
                '<select id="chartRange" aria-label="统计区间">' +
                  '<option>最近 7 天</option><option>最近 30 天</option><option>今日</option>' +
                '</select>' +
                '<span class="chev" data-icon="chevD"></span>' +
              '</span>' +
            '</div>' +
            '<div class="chart-body">' +
              '<div class="legend chart-legend">' + legend + '</div>' +
              '<div class="chart-canvas" id="chartCanvas"></div>' +
            '</div>' +
          '</section>' +

          '<section class="card table-card">' +
            window.UI.cardHead(d.tasks.title, window.UI.moreLink('查看更多')) +
            '<div class="table-wrap">' + window.UI.taskTable(d.tasks) + '</div>' +
          '</section>' +

        '</div>' +
        '<div class="col-side">' +

          '<section class="card events-card">' +
            window.UI.cardHead(d.events.title, window.UI.moreLink('查看更多')) +
            '<ul class="events-list">' + events + '</ul>' +
          '</section>' +

          '<section class="tips-card">' +
            '<span class="tips-icon" data-icon="bulb"></span>' +
            '<div><h3 class="tips-title">' + window.UI.esc(d.tips.title) + '</h3>' +
            '<p class="tips-text">' + window.UI.esc(d.tips.text) + '</p></div>' +
          '</section>' +

        '</div>' +
      '</div>';
  }

  function mount(root, shell, d) {
    window.Icons.mount(root);
    const canvas = root.querySelector('#chartCanvas');
    if (canvas) window.Charts.line(canvas, d.chart);
    const sel = root.querySelector('#chartRange');
    if (sel) sel.addEventListener('change', function () {
      window.Toast && window.Toast.show('已切换统计区间：' + sel.value);
    });
  }

  window.PageHome = { render: render, mount: mount };
})();

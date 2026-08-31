/* 銀座やしろ - 共通スクリプト */
(function () {
  // ヘッダーのスクロール演出
  const header = document.getElementById('siteHeader');
  const onScroll = () => {
    if (window.scrollY > 40) header.classList.add('scrolled');
    else header.classList.remove('scrolled');
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // モバイルナビ
  const toggle = document.getElementById('navToggle');
  const nav = document.getElementById('mainNav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.querySelectorAll('a').forEach(a =>
      a.addEventListener('click', () => {
        nav.classList.remove('open');
        toggle.classList.remove('open');
      })
    );
  }

  // スクロールフェードイン（中身の要素にのみ適用し、セクション枠には掛けない）
  const targets = document.querySelectorAll(
    '.section-head, .order-intro-text, .concept-text, .photo-slot, .menu-card, .staff-card, .live-box, .access-info, .access-map, .system-table-wrap, .first-visit-card, .digest-box'
  );
  targets.forEach(t => t.classList.add('fade-in'));

  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  targets.forEach(t => io.observe(t));

  // 画面内の要素は初回描画で即表示（撮影ツール・低速環境でも真っ黒にしない）
  const revealInView = () => targets.forEach(t => {
    const r = t.getBoundingClientRect();
    if (r.top < window.innerHeight * 1.2 && r.bottom > 0) t.classList.add('visible');
  });
  revealInView();
  window.addEventListener('scroll', revealInView, { passive: true });
  // 最終保険：どんな環境でも必ず全表示（隠れたまま残ることを防ぐ）
  setTimeout(() => targets.forEach(t => t.classList.add('visible')), 2500);
})();

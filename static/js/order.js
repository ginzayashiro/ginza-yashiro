/* 銀座やしろ - 遠隔オーダー（カート＋注文） */
(function () {
  const cart = new Map(); // id -> {id,name,price,qty}

  const cartItemsEl = document.getElementById('cartItems');
  const cartTotalEl = document.getElementById('cartTotal');
  const submitBtn = document.getElementById('submitBtn');
  const form = document.getElementById('orderForm');

  const yen = n => '¥' + n.toLocaleString('ja-JP');

  function toast(msg, isError) {
    let el = document.querySelector('.toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), 2400);
  }

  function render() {
    if (cart.size === 0) {
      cartItemsEl.innerHTML = '<p class="cart-empty">カートは空です。メニューからお選びください。</p>';
      cartTotalEl.textContent = yen(0);
      return;
    }
    let html = '';
    let total = 0;
    cart.forEach(it => {
      total += it.price * it.qty;
      html += `
        <div class="cart-item" data-id="${it.id}">
          <span class="cart-item-name">${it.name}</span>
          <span class="cart-item-qty">
            <button type="button" class="qty-btn" data-act="dec">−</button>
            <span>${it.qty}</span>
            <button type="button" class="qty-btn" data-act="inc">＋</button>
          </span>
          <span class="cart-item-price">${yen(it.price * it.qty)}</span>
        </div>`;
    });
    cartItemsEl.innerHTML = html;
    cartTotalEl.textContent = yen(total);
  }

  // カートに追加
  document.querySelectorAll('.btn-add').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const existing = cart.get(id);
      if (existing) existing.qty = Math.min(99, existing.qty + 1);
      else cart.set(id, { id, name: btn.dataset.name, price: parseInt(btn.dataset.price, 10), qty: 1 });
      btn.classList.add('added');
      btn.textContent = '追加しました ✓';
      setTimeout(() => { btn.classList.remove('added'); btn.textContent = 'カートに追加'; }, 1400);
      render();
      toast('カートに追加しました');
    });
  });

  // 数量変更
  cartItemsEl.addEventListener('click', e => {
    const btn = e.target.closest('.qty-btn');
    if (!btn) return;
    const id = btn.closest('.cart-item').dataset.id;
    const it = cart.get(id);
    if (!it) return;
    if (btn.dataset.act === 'inc') it.qty = Math.min(99, it.qty + 1);
    else it.qty -= 1;
    if (it.qty <= 0) cart.delete(id);
    render();
  });

  // カテゴリフィルタ
  const filterWrap = document.getElementById('categoryFilter');
  const cards = document.querySelectorAll('.menu-card');
  const cats = new Set();
  cards.forEach(c => cats.add(c.dataset.category));
  cats.forEach(cat => {
    const b = document.createElement('button');
    b.className = 'cat-btn';
    b.dataset.cat = cat;
    b.textContent = cat;
    filterWrap.appendChild(b);
  });
  filterWrap.addEventListener('click', e => {
    const btn = e.target.closest('.cat-btn');
    if (!btn) return;
    filterWrap.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const cat = btn.dataset.cat;
    cards.forEach(c => {
      c.style.display = (cat === 'all' || c.dataset.category === cat) ? '' : 'none';
    });
  });

  // 開栓タイミングの日時指定トグル
  const openAtField = document.getElementById('openAtField');
  form.querySelectorAll('input[name="open_timing"]').forEach(r => {
    r.addEventListener('change', () => {
      openAtField.style.display = (form.open_timing.value === 'scheduled') ? '' : 'none';
    });
  });

  // 注文送信
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (cart.size === 0) {
      toast('メニューを1つ以上お選びください。', true);
      return;
    }
    const fd = new FormData(form);
    const payload = {
      customer_name: (fd.get('customer_name') || '').trim(),
      staff: fd.get('staff') || '',
      message: (fd.get('message') || '').trim(),
      open_timing: fd.get('open_timing') || 'now',
      open_at: fd.get('open_at') || '',
      items: Array.from(cart.values()).map(it => ({ id: it.id, qty: it.qty }))
    };
    if (!payload.customer_name) {
      toast('お名前を入力してください。', true);
      return;
    }
    if (payload.open_timing === 'scheduled' && !payload.open_at) {
      toast('開栓希望日時を指定してください。', true);
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = '送信中…';
    try {
      const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '送信に失敗しました。');
      if (data.checkout_url) {
        window.location.href = data.checkout_url; // 決済ページへ（将来の自動連携用）
      } else {
        window.location.href = data.success_url;
      }
    } catch (err) {
      toast(err.message || '通信エラーが発生しました。', true);
      submitBtn.disabled = false;
      submitBtn.textContent = '注文を確定する';
    }
  });

  render();
})();

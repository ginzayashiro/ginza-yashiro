/* 銀座やしろ - 受注管理（リアルタイム） */
(function () {
  const listEl = document.getElementById('orderList');
  const connDot = document.getElementById('connStatus');
  const connLabel = document.getElementById('connLabel');
  const soundToggle = document.getElementById('soundToggle');
  const sound = document.getElementById('notifySound');

  let soundOn = true;
  const orders = new Map(); // id -> order

  const STATUS_LABELS = {
    new: '新規',
    preparing: '準備中',
    opened: '開栓済み',
    done: '完了',
    cancelled: 'キャンセル'
  };
  const PAYMENT_LABELS = {
    awaiting_link: '決済リンク未送付',
    link_sent: 'リンク送付済み',
    paid: '入金確認済み',
    cancelled: '決済取消'
  };
  const yen = n => '¥' + n.toLocaleString('ja-JP');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  function setConn(on) {
    connDot.className = 'dot ' + (on ? 'online' : 'offline');
    connLabel.textContent = on ? 'リアルタイム接続中' : '切断（再接続します）';
  }

  function render() {
    const arr = Array.from(orders.values())
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    if (arr.length === 0) {
      listEl.innerHTML = '<p class="empty">まだ注文はありません。新しい注文が入ると自動で表示されます。</p>';
      return;
    }
    listEl.innerHTML = arr.map(o => `
      <article class="order-card" data-id="${esc(o.id)}">
        <div class="order-top">
          <span class="badge ${esc(o.status)}">${STATUS_LABELS[o.status] || o.status}</span>
          <div>
            <span class="order-id">#${esc(o.id)}</span>　
            <span class="order-time">${esc(o.created_at)}</span>
          </div>
        </div>
        <p class="order-name">${esc(o.customer_name)} 様</p>
        <p class="order-staff">指名：${esc(o.staff || '指名なし')}</p>
        <p class="order-timing">開栓：<strong>${o.open_timing === 'scheduled' ? '日時指定（' + esc(o.open_at) + '）' : 'すぐに開栓'}</strong></p>
        <p class="order-payment">💳 決済：<span class="badge pay-${esc(o.payment_status)}">${PAYMENT_LABELS[o.payment_status] || o.payment_status}</span></p>
        <ul class="order-items">
          ${o.items.map(it => `<li><span>${esc(it.name)} × ${it.qty}</span><span>${yen(it.price * it.qty)}</span></li>`).join('')}
        </ul>
        <p class="order-total">合計 ${yen(o.total)}</p>
        ${o.message ? `<div class="order-message">💌 ${esc(o.message)}</div>` : ''}
        <div class="order-actions">
          ${Object.keys(PAYMENT_LABELS).map(s =>
            `<button class="status-btn pay-btn ${o.payment_status === s ? 'active' : ''}" data-pay="${s}">${PAYMENT_LABELS[s]}</button>`
          ).join('')}
        </div>
        <div class="order-actions">
          ${Object.keys(STATUS_LABELS).map(s =>
            `<button class="status-btn ${o.status === s ? 'active' : ''}" data-status="${s}">${STATUS_LABELS[s]}</button>`
          ).join('')}
        </div>
      </article>
    `).join('');
  }

  async function loadInitial() {
    try {
      const res = await fetch('/api/admin/orders?key=' + encodeURIComponent(ADMIN_KEY));
      const data = await res.json();
      data.forEach(o => orders.set(o.id, o));
      render();
    } catch (e) {
      console.error(e);
    }
  }

  function connect() {
    const es = new EventSource('/api/admin/stream?key=' + encodeURIComponent(ADMIN_KEY));
    es.onopen = () => setConn(true);
    es.onerror = () => { setConn(false); };
    es.onmessage = e => {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }
      if (evt.type === 'order') {
        const isNew = !orders.has(evt.order.id);
        orders.set(evt.order.id, evt.order);
        render();
        if (isNew) {
          const card = listEl.querySelector(`[data-id="${evt.order.id}"]`);
          if (card) card.classList.add('new-flash');
          if (soundOn) { sound.currentTime = 0; sound.play().catch(() => {}); }
          // タブのタイトルで知らせる
          document.title = '🔔 新着注文！ | 銀座やしろ 受注管理';
          setTimeout(() => { document.title = '受注管理 | 銀座やしろ'; }, 6000);
        }
      } else if (evt.type === 'status') {
        const o = orders.get(evt.order_id);
        if (o) { o.status = evt.status; render(); }
      } else if (evt.type === 'payment') {
        const o = orders.get(evt.order_id);
        if (o) { o.payment_status = evt.payment_status; render(); }
      }
    };
  }

  // ステータス変更（開栓ステータス / 入金ステータス）
  listEl.addEventListener('click', async e => {
    const btn = e.target.closest('.status-btn');
    if (!btn) return;
    const id = btn.closest('.order-card').dataset.id;
    const isPay = !!btn.dataset.pay;
    const url = isPay
      ? `/api/admin/orders/${id}/payment?key=` + encodeURIComponent(ADMIN_KEY)
      : `/api/admin/orders/${id}/status?key=` + encodeURIComponent(ADMIN_KEY);
    const body = isPay ? { payment_status: btn.dataset.pay } : { status: btn.dataset.status };
    try {
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const o = orders.get(id);
      if (o) {
        if (isPay) o.payment_status = btn.dataset.pay;
        else o.status = btn.dataset.status;
        render();
      }
    } catch (err) {
      alert('更新に失敗しました');
    }
  });

  soundToggle.addEventListener('click', () => {
    soundOn = !soundOn;
    soundToggle.textContent = soundOn ? '🔔 通知音ON' : '🔕 通知音OFF';
  });

  loadInitial();
  connect();
})();

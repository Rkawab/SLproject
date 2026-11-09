(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const csrf = () => $('[name=csrfmiddlewaretoken]')?.value || '';

  function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  async function post(url, data) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf()
      },
      body: JSON.stringify(data)
    });
    let result;
    try {
      result = await response.json();
    } catch {
      result = {};
    }
    if (!response.ok) {
      const error = new Error(result.error || '送信できませんでした。');
      error.status = response.status;
      throw error;
    }
    return result;
  }
  let toastTimer;

  function toast(message, undo) {
    const el = $('#toast');
    $('span', el).textContent = message;
    const button = $('button', el);
    button.hidden = !undo;
    button.onclick = () => {
      el.hidden = true;
      undo?.();
    };
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, undo ? 3000 : 5000);
  }
  const sheet = $('#sheet');
  $('[data-close-sheet]')?.addEventListener('click', () => sheet.close());
  sheet?.addEventListener('click', e => {
    if (e.target === sheet && e.clientY < sheet.getBoundingClientRect().top) sheet.close();
  });

  function openSheet(title) {
    $('#sheet-title').textContent = title;
    $('#sheet-body').replaceChildren();
    if (!sheet.open) sheet.showModal();
    return $('#sheet-body');
  }

  function field(label, value, type = 'input') {
    const wrap = node('label', label);
    const input = node(type);
    input.value = value || '';
    wrap.append(input);
    return {
      wrap,
      input
    };
  }

  function action(label, callback, className = 'btn btn-primary') {
    const button = node('button', label, className);
    button.type = 'button';
    button.addEventListener('click', callback);
    return button;
  }

  function longPress(el, callback) {
    let timer, fired = false,
      startX, startY;
    el.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      fired = false;
      startX = e.clientX;
      startY = e.clientY;
      timer = setTimeout(() => {
        fired = true;
        callback();
      }, 550);
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(name => el.addEventListener(name, () => clearTimeout(timer)));
    el.addEventListener('pointermove', e => {
      if (Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) > 12) clearTimeout(timer);
    });
    el.addEventListener('click', e => {
      if (fired) {
        e.stopImmediatePropagation();
        e.preventDefault();
        fired = false;
      }
    }, true);
    el.addEventListener('contextmenu', e => e.preventDefault());
  }
  let selectedStore = '';
  try {
    selectedStore = localStorage.getItem('shopping-store') || '';
  } catch {
    /* private mode */
  }
  const list = $('#shopping-list');
  if (list) {
    let entries = JSON.parse($('#initial-entries').textContent),
      flushing = false,
      fetching = false,
      mutationRevision = 0,
      poll;
    const queueKey = `shopping-checks-${document.body.dataset.userId}`;
    let queue = [];
    try {
      queue = JSON.parse(localStorage.getItem(queueKey) || '[]');
      if (!Array.isArray(queue)) queue = [];
      queue = queue.filter(op => Number.isInteger(op.id) && typeof op.checked === 'boolean');
    } catch {
      queue = [];
    }

    function persist() {
      try {
        localStorage.setItem(queueKey, JSON.stringify(queue));
      } catch {
        /* unavailable */
      }
    }

    function applyPending() {
      for (const op of queue) {
        const entry = entries.find(e => e.id === op.id);
        if (entry) entry.is_checked = op.checked;
      }
    }

    function render(highlights = new Set()) {
      applyPending();
      const visible = entries.filter(e => !selectedStore || !e.store_id || String(e.store_id) === selectedStore);
      const unchecked = visible.filter(e => !e.is_checked),
        checked = visible.filter(e => e.is_checked);
      $('#remaining').textContent = unchecked.length;
      $('#total').textContent = visible.length;
      $('#checked-count').textContent = checked.length;
      $('#progress').max = Math.max(1, visible.length);
      $('#progress').value = checked.length;
      const target = $('#unchecked-entries');
      target.replaceChildren();
      const groups = new Map();
      unchecked.sort((a, b) => Number(a.is_fallback) - Number(b.is_fallback) || a.section_order - b.section_order).forEach(entry => {
        if (!groups.has(entry.section_id)) {
          const section = node('section', undefined, 'entry-section');
          section.append(node('h2', entry.section));
          groups.set(entry.section_id, section);
          target.append(section);
        }
        groups.get(entry.section_id).append(row(entry, highlights.has(entry.id)));
      });
      $('#checked-entries').replaceChildren(...checked.map(entry => row(entry, highlights.has(entry.id))));
      $('#checked-group').hidden = !checked.length;
      $('#empty-message').hidden = unchecked.length > 0;
      $('#empty-message').textContent = visible.length ? '全部買えました。おつかれさま！' : 'リストは空です。＋追加から買う物を選びましょう。';
      $('#complete-button').disabled = !checked.length || queue.length > 0;
      $('#complete-button').classList.toggle('btn-primary', !unchecked.length && checked.length > 0);
      $('#complete-store').value = selectedStore;
      $$('.store-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.store === selectedStore);
        tab.setAttribute('aria-pressed', String(tab.dataset.store === selectedStore));
      });
      $('#sync-status').textContent = queue.length ? `${queue.length}件を送信待ち` : 'ふたりの共有リスト';
    }

    function row(entry, highlight) {
      const container = node('div', undefined, `entry-row${entry.is_checked?' checked':''}${highlight?' highlight':''}`);
      const button = node('button', undefined, 'entry-check');
      button.type = 'button';
      button.setAttribute('aria-pressed', String(entry.is_checked));
      button.append(node('span', entry.is_checked ? '✓' : '', 'check-circle'));
      const text = node('span', undefined, 'entry-text');
      text.append(node('strong', entry.name));
      if (entry.quantity) text.append(node('span', entry.quantity, 'entry-quantity'));
      if (entry.note) text.append(node('small', entry.note));
      button.append(text);
      longPress(button, () => edit(entry));
      button.addEventListener('click', () => check(entry, !entry.is_checked, true, container));
      const menu = action('⋯', () => edit(entry), 'row-menu');
      menu.setAttribute('aria-label', `${entry.name}を編集`);
      container.append(button, menu);
      return container;
    }

    function check(entry, checked, undo = true, container = null) {
      mutationRevision++;
      const before = entry.is_checked;
      entry.is_checked = checked;
      queue = queue.filter(op => op.id !== entry.id);
      queue.push({
        id: entry.id,
        checked
      });
      persist();
      if (container) {
        // 先にその行をチェック表示にし、移動するまで指の下に300ms残す。
        container.classList.toggle('checked', checked);
        $('.entry-check', container).setAttribute('aria-pressed', String(checked));
        $('.check-circle', container).textContent = checked ? '✓' : '';
        const visible = entries.filter(e => !selectedStore || !e.store_id || String(e.store_id) === selectedStore);
        $('#remaining').textContent = visible.filter(e => !e.is_checked).length;
        $('#progress').value = visible.filter(e => e.is_checked).length;
        $('#sync-status').textContent = `${queue.length}件を送信待ち`;
        $('#complete-button').disabled = true;
        setTimeout(() => {
          render();
          flush();
        }, 300);
      } else {
        render();
        flush();
      }
      if (undo) toast(checked ? `${entry.name}を購入済みにしました` : `${entry.name}を未購入に戻しました`, () => check(entry, before, false));
    }
    async function flush() {
      if (flushing || !queue.length) return;
      flushing = true;
      try {
        while (queue.length) {
          const op = queue[0],
            entry = entries.find(e => e.id === op.id);
          if (!entry) {
            queue.shift();
            persist();
            continue;
          }
          try {
            const result = await post(entry.toggle_url, {
              checked: op.checked
            });
            if (queue[0] === op) queue.shift();
            const index = entries.findIndex(e => e.id === op.id);
            if (index >= 0) entries[index] = result.entry;
            persist();
            render();
          } catch (error) {
            if (error.status >= 400 && error.status < 500 && error.status !== 401) {
              queue = queue.filter(x => x.id !== op.id);
              persist();
              toast('変更を送信できませんでした。リストを再取得します。');
              await refresh();
            } else {
              toast(error.status === 401 ? 'ログインし直すと送信を再開できます。' : '通信待ちです。接続が戻ったら再送します。');
              break;
            }
          }
        }
      } finally {
        flushing = false;
        render();
      }
    }
    async function refresh() {
      if (fetching || document.visibilityState === 'hidden') return;
      fetching = true;
      const revision = mutationRevision;
      try {
        const response = await fetch(list.dataset.entriesUrl, {
          credentials: 'same-origin'
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        // 取得を始めた後の手元の操作を、古い応答で巻き戻さない。
        if (revision !== mutationRevision) return;
        const known = new Set(entries.map(e => e.id));
        entries = data.entries;
        render(new Set(entries.filter(e => !known.has(e.id) && e.added_by !== Number(document.body.dataset.userId)).map(e => e.id)));
      } catch {
        $('#sync-status').textContent = '通信を確認しています';
      } finally {
        fetching = false;
      }
    }

    function edit(entry) {
      const body = openSheet(entry.name),
        quantity = field('数量', entry.quantity),
        note = field('メモ', entry.note),
        store = field('店', '', 'select');
      store.input.replaceChildren(...Array.from($('#store-options').options).map(o => o.cloneNode(true)));
      store.input.value = entry.store_id || '';
      body.append(quantity.wrap, note.wrap, store.wrap, action('保存', async () => {
        try {
          const result = await post(entry.update_url, {
            quantity: quantity.input.value,
            note: note.input.value,
            store_id: store.input.value
          });
          mutationRevision++;
          entries[entries.findIndex(e => e.id === entry.id)] = result.entry;
          render();
          sheet.close();
        } catch (error) {
          toast(error.message);
        }
      }), action('リストから外す', async () => {
        try {
          await post(entry.delete_url, {});
          mutationRevision++;
          entries = entries.filter(e => e.id !== entry.id);
          queue = queue.filter(op => op.id !== entry.id);
          persist();
          render();
          sheet.close();
        } catch (error) {
          toast(error.message);
        }
      }, 'btn btn-outline-danger'));
    }
    if (!$$('.store-tab').some(tab => tab.dataset.store === selectedStore)) selectedStore = '';
    $$('.store-tab').forEach(tab => tab.addEventListener('click', () => {
      selectedStore = tab.dataset.store;
      try {
        localStorage.setItem('shopping-store', selectedStore);
      } catch {}
      render();
    }));
    $('#complete-form').addEventListener('submit', e => {
      if (queue.length || !confirm('表示中の店の購入済み品目を片付けますか？未購入の品目は残ります。')) e.preventDefault();
    });

    function schedule() {
      clearInterval(poll);
      if (document.visibilityState !== 'hidden') {
        refresh().then(flush);
        poll = setInterval(() => refresh().then(flush), 10000);
      }
    }
    document.addEventListener('visibilitychange', schedule);
    window.addEventListener('online', () => refresh().then(flush));
    applyPending();
    render();
    schedule();
  }

  const addPage = $('#add-page');
  if (addPage) {
    const current = new Map(JSON.parse($('#initial-entries').textContent).map(entry => [entry.item_id, entry]));
    const sections = JSON.parse($('#section-data').textContent),
      busy = new Set();
    let added = 0,
      suggestTimer, suggestVersion = 0;
    const input = $('#manual-name');

    function paint() {
      $$('.item-chip').forEach(chip => {
        const id = Number(chip.dataset.itemId);
        chip.classList.toggle('selected', current.has(id));
        chip.setAttribute('aria-pressed', String(current.has(id)));
        chip.disabled = busy.has(id);
      });
      $('#added-count').textContent = `${added}件追加済`;
    }

    function ensureChip(item) {
      if (item.is_hidden) return;
      const section = $(`#section-${item.section_id}`);
      if (!section) return;
      if (!$$('.item-chip', section).some(c => Number(c.dataset.itemId) === item.id)) {
        const chip = node('button', item.name, 'item-chip');
        chip.type = 'button';
        chip.dataset.itemId = item.id;
        $('.chips', section).append(chip);
        bindChip(chip);
      }
      section.hidden = false;
      const jump = $(`[data-section-jump="${item.section_id}"]`);
      if (jump) jump.hidden = false;
    }

    function resultAdded(result, manual = true) {
      current.set(result.item.id, result.entry);
      ensureChip(result.item);
      paint();
      if (result.status === 'already_listed' && manual) {
        duplicateSheet(result);
        return;
      }
      if (result.status !== 'already_listed') added++;
      paint();
      toast(result.status === 'already_listed' ? 'すでにリストにあります' : `${result.item.name}を追加しました`);
      input.value = '';
      $('#suggestions').hidden = true;
      sheet.close();
    }
    async function send(data, manual = true) {
      try {
        const result = await post(addPage.dataset.addUrl, data);
        if (result.status === 'maybe' || result.status === 'new') matchSheet(result);
        else resultAdded(result, manual);
      } catch (error) {
        toast(error.message);
      }
    }

    function duplicateSheet(result) {
      const body = openSheet(`${result.item.name}はリストにあります`);
      const quantity = field('数量', result.requested.quantity || result.entry.quantity),
        note = field('メモ', result.requested.note || result.entry.note);
      body.append(quantity.wrap, note.wrap, action('数量・メモを更新', async () => {
        try {
          const update = await post(result.entry.update_url, {
            quantity: quantity.input.value,
            note: note.input.value
          });
          current.set(result.item.id, update.entry);
          sheet.close();
          toast('数量・メモを更新しました');
          input.value = '';
        } catch (error) {
          toast(error.message);
        }
      }), action('そのまま', () => sheet.close(), 'btn btn-outline-primary'));
    }

    function matchSheet(result) {
      const body = openSheet(result.status === 'maybe' ? 'もしかして？' : `新しい品目「${result.name}」を登録`);
      const quantity = field('数量', result.quantity),
        note = field('メモ', result.note);
      body.append(quantity.wrap, note.wrap);
      const payload = () => ({
        name: result.name,
        quantity: quantity.input.value,
        note: note.input.value,
        store_id: selectedStore
      });
      const error = node('p', '', 'sheet-error');
      error.setAttribute('role', 'alert');
      body.append(error);
      let saving = false;
      async function register(extra) {
        if (saving) return;
        saving = true;
        try {
          const response = await post(addPage.dataset.itemsUrl, {
            ...payload(),
            ...extra
          });
          resultAdded(response);
        } catch (e) {
          error.textContent = e.message;
        } finally {
          saving = false;
        }
      }
      if (result.candidates.length) {
        const choices = node('div', undefined, 'sheet-actions');
        result.candidates.forEach(item => {
          choices.append(action(`${item.name}を追加`, () => send({
            item_id: item.id,
            quantity: quantity.input.value,
            note: note.input.value,
            store_id: selectedStore
          })), action(`${item.name}の別名にして追加`, () => register({
            alias_item_id: item.id
          }), 'btn btn-outline-primary'));
        });
        body.append(choices, action('新しい品目として登録', () => {
          result.status = 'new';
          result.candidates = [];
          matchSheet({
            ...result,
            quantity: quantity.input.value,
            note: note.input.value
          });
        }, 'btn btn-outline-primary'));
      } else {
        const choices = node('div', undefined, 'section-choices');
        sections.forEach(section => {
          const button = action(section.name, () => register({
            section_id: section.id
          }), 'section-choice');
          button.append(node('small', section.description));
          choices.append(button);
        });
        body.append(node('p', 'ジャンルを選んで追加します。', 'muted'), choices, action('ジャンルを選ばず追加（その他）', () => register({}), 'btn btn-outline-primary'));
      }
    }

    function bindChip(chip) {
      const id = Number(chip.dataset.itemId),
        name = chip.textContent;
      longPress(chip, () => {
        const entry = current.get(id);
        const body = openSheet(`${name}の数量・メモ`),
          quantity = field('数量', entry?.quantity),
          note = field('メモ', entry?.note);
        body.append(quantity.wrap, note.wrap, action(entry ? '更新' : '追加', async () => {
          if (entry) {
            try {
              const result = await post(entry.update_url, {
                quantity: quantity.input.value,
                note: note.input.value
              });
              current.set(id, result.entry);
              sheet.close();
              toast('更新しました');
            } catch (error) {
              toast(error.message);
            }
          } else await send({
            item_id: id,
            quantity: quantity.input.value,
            note: note.input.value,
            store_id: selectedStore
          });
        }));
      });
      chip.addEventListener('click', async () => {
        if (busy.has(id)) return;
        busy.add(id);
        paint();
        try {
          const entry = current.get(id);
          if (entry) {
            await post(entry.delete_url, {});
            current.delete(id);
            toast(`${name}をリストから外しました`);
          } else await send({
            item_id: id,
            store_id: selectedStore
          }, false);
        } catch (error) {
          toast(error.message);
        } finally {
          busy.delete(id);
          paint();
        }
      });
    }
    $$('.item-chip').forEach(bindChip);
    paint();
    $('#manual-form').addEventListener('submit', async e => {
      e.preventDefault();
      if (!input.value.trim()) return;
      const button = $('button', e.currentTarget);
      if (button.disabled) return;
      button.disabled = true;
      await send({
        raw: input.value,
        store_id: selectedStore
      });
      button.disabled = false;
    });
    input.addEventListener('input', () => {
      clearTimeout(suggestTimer);
      const version = ++suggestVersion;
      if (!input.value.trim()) {
        $('#suggestions').hidden = true;
        return;
      }
      suggestTimer = setTimeout(async () => {
        try {
          const url = new URL(addPage.dataset.suggestUrl, location.origin);
          url.searchParams.set('q', input.value);
          const response = await fetch(url);
          if (!response.ok) return;
          const data = await response.json();
          if (version !== suggestVersion) return;
          const target = $('#suggestions');
          target.replaceChildren(...data.items.map(item => action(item.name + (item.alias ? `（${item.alias}）` : ''), () => send({
            item_id: item.id,
            raw: input.value,
            store_id: selectedStore
          }), '')));
          target.hidden = !data.items.length;
        } catch {
          /* 次の入力で再検索 */
        }
      }, 180);
    });
  }

  $$('form[data-confirm]').forEach(form => form.addEventListener('submit', e => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  }));
  $('#selection-mode')?.addEventListener('click', e => {
    const selected = e.currentTarget.getAttribute('aria-pressed') !== 'true';
    e.currentTarget.setAttribute('aria-pressed', String(selected));
    e.currentTarget.textContent = selected ? '選択を終了' : '選択';
    $('#move-tools').hidden = !selected;
    $$('.item-select').forEach(input => {
      input.hidden = !selected;
      if (!selected) input.checked = false;
    });
  });
  if ($('#preview-form')) {
    const updateCount = () => {
      const count = $$('#preview-form input[type=checkbox]:checked').length;
      $('#import-confirm').textContent = `${count}件を追加`;
      $('#import-confirm').disabled = count === 0;
    };
    $$('#preview-form input[type=checkbox]').forEach(input => input.addEventListener('change', updateCount));
    updateCount();
    $('#preview-form').addEventListener('submit', () => {
      $('#import-confirm').disabled = true;
    });
  }
})();

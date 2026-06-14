/* Canonical three-card triage helpers — window.ThreeCardTriage */
(function (global) {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function recommendedSlot(item) {
    return typeof item.recommendedSlot === 'number' ? item.recommendedSlot : 0;
  }

  function defaultPick(item) {
    var rec = recommendedSlot(item);
    var proposals = item.proposals || ['', '', ''];
    var slot = rec;
    if (!proposals[slot]) {
      slot = proposals.findIndex(function (p) { return !!p; });
      if (slot < 0) slot = rec;
    }
    var text = (proposals[slot] || '').trim();
    return { text: text, slot: text ? slot : null, source: slot === rec ? 'recommended' : 'card' };
  }

  function pickLabel(pick, item, labels) {
    labels = labels || {};
    if (pick.source === 'custom' || pick.slot == null) return labels.custom || 'Custom action';
    if (pick.slot === recommendedSlot(item)) return labels.recommended || ('Option ' + (pick.slot + 1) + ' · Recommended');
    return (labels.option || 'Option') + ' ' + (pick.slot + 1);
  }

  function cardApproveLabel(slot, item, labels) {
    labels = labels || {};
    if (slot === recommendedSlot(item)) return labels.approveRecommended || '✓ Approve recommended';
    return (labels.approveOption || '✓ Approve option') + ' ' + (slot + 1);
  }

  function renderProposalCard(item, slot, pick, opts) {
    opts = opts || {};
    var idKey = opts.idAttr || 'data-triage-id';
    var proposals = item.proposals || ['', '', ''];
    var text = proposals[slot] || '';
    var selected = pick && pick.slot === slot && text && pick.text === text;
    var rec = recommendedSlot(item);
    var isRec = slot === rec && !!text;
    var label = 'Option ' + (slot + 1);
    var badge = isRec ? '<span class="fb-proposal-badge">★ Recommended</span>' : '';
    var id = esc(item.id);
    if (!text) {
      return '<div class="fb-proposal-card empty" ' + idKey + '="' + id + '" data-slot="' + slot + '">' +
        '<div class="fb-proposal-head"><span class="fb-proposal-label">' + label + '</span>' + badge + '</div>' +
        '<div class="fb-proposal-text" style="color:var(--triage-faint,var(--faint));font-style:italic;">Dismissed — reroll to draw a new card</div>' +
        '<div class="fb-proposal-actions"><button type="button" class="triage-btn" data-triage-reroll="' + id + '" data-slot="' + slot + '">↻ Reroll</button></div></div>';
    }
    var cls = 'fb-proposal-card' + (selected ? ' on' : '') + (isRec ? ' recommended' : '');
    return '<div class="' + cls + '" data-triage-pick="' + id + '" data-slot="' + slot + '">' +
      '<div class="fb-proposal-head"><span class="fb-proposal-label">' + label + '</span>' + badge + '</div>' +
      '<div class="fb-proposal-text">' + esc(text) + '</div>' +
      '<div class="fb-proposal-actions">' +
        '<button type="button" class="triage-btn triage-btn-go fb-card-approve" data-triage-accept="' + id + '" data-slot="' + slot + '">' +
          esc(cardApproveLabel(slot, item, opts.labels)) + '</button>' +
        '<button type="button" class="triage-btn" data-triage-reroll="' + id + '" data-slot="' + slot + '">↻ Reroll</button>' +
        '<button type="button" class="triage-btn triage-btn-no" data-triage-dismiss="' + id + '" data-slot="' + slot + '">✕ Dismiss</button>' +
        '<button type="button" class="triage-btn" data-triage-edit="' + id + '" data-slot="' + slot + '">✎ Edit</button>' +
      '</div></div>';
  }

  function renderAcceptPreview(item, pick, opts) {
    opts = opts || {};
    var preview = pick && pick.text
      ? esc(pick.text)
      : '<span style="color:var(--triage-faint,var(--faint));font-style:italic;">Pick a card or write a custom action below</span>';
    return '<div class="fb-accept-preview" id="triage-preview-' + esc(item.id) + '">' +
      '<div class="label">' + esc(opts.previewLabel || 'Action preview') + '</div>' +
      '<div class="text">' + preview + '</div>' +
      '<div class="meta">' + esc(pickLabel(pick, item, opts.labels)) + '</div></div>';
  }

  function bindContainer(container, config) {
    if (!container || container._triageBound) return;
    container._triageBound = true;
    var picks = config.picks || {};
    var getItem = config.getItem;
    var patchItem = config.patchItem;
    var apiPost = config.apiPost;
    var onToast = config.onToast || function () {};
    var labels = config.labels || {};
    var paths = Object.assign({
      reroll: '/api/feedback/proposals/reroll',
      update: '/api/feedback/proposals/update',
      accept: '/api/feedback/proposals/accept',
      action: '/api/feedback/action',
    }, config.paths || {});

    function resolvePick(item) {
      return picks[item.id] || defaultPick(item);
    }

    function toast(msg, err) { onToast(msg, !!err); }

    function doAccept(id, solution, acceptedSlot) {
      var item = getItem(id);
      if (!item) return Promise.resolve();
      solution = (solution || '').trim();
      if (!solution) { toast('Pick a card or write a custom action.', true); return Promise.resolve(); }
      var noteEl = document.getElementById('triage-note-' + id);
      var note = noteEl ? (noteEl.value || '').trim() : '';
      if (!global.confirm('Approve this action?\n\n' + solution.slice(0, 500))) return Promise.resolve();
      return apiPost(paths.accept, {
        id: id,
        solution: solution,
        acceptedSlot: acceptedSlot,
        reviewNote: note,
        note: note,
        status: config.acceptStatus || 'accepted',
      }).then(function (res) {
        delete picks[id];
        if (patchItem) patchItem(res.item || res);
        toast(config.acceptToast || 'Approved and filed away.');
      }).catch(function (err) { toast(err.message || String(err), true); });
    }

    container.addEventListener('click', function (e) {
      var t = e.target;
      if (!(t instanceof HTMLElement)) return;
      if (t.closest('button')) e.stopPropagation();

      if (t.dataset.triageAccept != null) {
        var idA = t.dataset.triageAccept;
        var slotA = parseInt(t.dataset.slot, 10);
        var itemA = getItem(idA);
        if (!itemA) return;
        var textA = ((itemA.proposals || [])[slotA] || '').trim();
        if (!textA) return;
        picks[idA] = { text: textA, slot: slotA, source: slotA === recommendedSlot(itemA) ? 'recommended' : 'card' };
        doAccept(idA, textA, slotA);
        return;
      }

      if (t.dataset.triageAcceptCustom != null) {
        var idCu = t.dataset.triageAcceptCustom;
        var itemCu = getItem(idCu);
        var customEl = document.getElementById('triage-custom-' + idCu);
        var pickCu = picks[idCu] || (itemCu ? defaultPick(itemCu) : { text: '', slot: null, source: 'custom' });
        var solution = ((customEl && customEl.value) || pickCu.text || '').trim();
        if (!solution) { toast('Pick a card or write a custom action.', true); return; }
        var acceptedSlot = pickCu.source === 'custom' ? null : pickCu.slot;
        if (itemCu) {
          var proposalsCu = itemCu.proposals || [];
          for (var ci = 0; ci < 3; ci++) {
            if (proposalsCu[ci] && proposalsCu[ci].trim() === solution) {
              acceptedSlot = ci;
              break;
            }
          }
        }
        doAccept(idCu, solution, acceptedSlot);
        return;
      }

      var pickEl = t.closest('[data-triage-pick]');
      if (pickEl) {
        var idP = pickEl.dataset.triagePick;
        var slotP = parseInt(pickEl.dataset.slot, 10);
        var itemP = getItem(idP);
        if (!itemP || !(itemP.proposals || [])[slotP]) return;
        picks[idP] = {
          text: itemP.proposals[slotP],
          slot: slotP,
          source: slotP === recommendedSlot(itemP) ? 'recommended' : 'card',
        };
        var ta = document.getElementById('triage-custom-' + idP);
        if (ta) ta.value = itemP.proposals[slotP];
        if (config.rerender) config.rerender();
        return;
      }

      if (t.dataset.triageReroll != null) {
        apiPost(paths.reroll, { id: t.dataset.triageReroll, slot: t.dataset.slot })
          .then(function (res) { if (patchItem) patchItem(res.item || res); toast('Rerolled card.'); })
          .catch(function (err) { toast(err.message || String(err), true); });
        return;
      }

      if (t.dataset.triageRerollAll != null) {
        apiPost(paths.reroll, { id: t.dataset.triageRerollAll, slot: 'all' })
          .then(function (res) {
            delete picks[res.item ? res.item.id : t.dataset.triageRerollAll];
            if (patchItem) patchItem(res.item || res);
            toast('Rerolled all three cards.');
          })
          .catch(function (err) { toast(err.message || String(err), true); });
        return;
      }

      if (t.dataset.triageDismiss != null) {
        apiPost(paths.update, { id: t.dataset.triageDismiss, slot: parseInt(t.dataset.slot, 10), text: '' })
          .then(function (res) { if (patchItem) patchItem(res.item || res); })
          .catch(function (err) { toast(err.message || String(err), true); });
        return;
      }

      if (t.dataset.triageEdit != null) {
        var idE = t.dataset.triageEdit;
        var slotE = parseInt(t.dataset.slot, 10);
        var itemE = getItem(idE);
        var cur = itemE && itemE.proposals ? itemE.proposals[slotE] : '';
        var next = global.prompt('Edit option ' + (slotE + 1) + ':', cur || '');
        if (next == null) return;
        apiPost(paths.update, { id: idE, slot: slotE, text: next.trim() })
          .then(function (res) {
            picks[idE] = { text: next.trim(), slot: slotE, source: 'card' };
            if (patchItem) patchItem(res.item || res);
          })
          .catch(function (err) { toast(err.message || String(err), true); });
        return;
      }

      if (t.dataset.triageStatus != null) {
        apiPost(paths.action, { id: t.dataset.triageStatus, status: t.dataset.status })
          .then(function (res) { if (patchItem) patchItem(res.item || res); toast('Status updated.'); })
          .catch(function (err) { toast(err.message || String(err), true); });
      }
    });

    container.addEventListener('input', function (e) {
      var t = e.target;
      if (!t.classList || !t.classList.contains('fb-custom-solution')) return;
      var id = t.id.replace('triage-custom-', '');
      var item = getItem(id);
      if (!item) return;
      var value = t.value;
      var trimmed = value.trim();
      var slot = null;
      var source = 'custom';
      var proposals = item.proposals || [];
      for (var i = 0; i < 3; i++) {
        if (proposals[i] && proposals[i].trim() === trimmed) {
          slot = i;
          source = i === recommendedSlot(item) ? 'recommended' : 'card';
          break;
        }
      }
      picks[id] = { text: value, slot: slot, source: source };
      var preview = document.getElementById('triage-preview-' + id);
      if (preview) {
        preview.querySelector('.text').innerHTML = trimmed
          ? esc(trimmed)
          : '<span style="color:var(--triage-faint,var(--faint));font-style:italic;">Pick a card or write a custom action below</span>';
        preview.querySelector('.meta').textContent = pickLabel(picks[id], item, labels);
      }
      container.querySelectorAll('[data-triage-pick="' + id + '"]').forEach(function (card) {
        var s = parseInt(card.dataset.slot, 10);
        var on = slot === s && trimmed === (proposals[s] || '').trim();
        card.classList.toggle('on', on);
      });
    });

    return {
      picks: picks,
      resolvePick: resolvePick,
      doAccept: doAccept,
    };
  }

  global.ThreeCardTriage = {
    esc: esc,
    recommendedSlot: recommendedSlot,
    defaultPick: defaultPick,
    pickLabel: pickLabel,
    cardApproveLabel: cardApproveLabel,
    renderProposalCard: renderProposalCard,
    renderAcceptPreview: renderAcceptPreview,
    bindContainer: bindContainer,
  };
})(typeof window !== 'undefined' ? window : global);

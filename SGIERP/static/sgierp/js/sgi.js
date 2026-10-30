/* ============================================================
   SGIERP — Main JavaScript
   ============================================================ */

// ---- Page Loader ----
function showPageLoader() {
  const loader = document.getElementById('pageLoader');
  if (loader) loader.classList.add('active');
}

function hidePageLoader() {
  const loader = document.getElementById('pageLoader');
  if (loader) loader.classList.remove('active');
}

// Show loader on all link clicks (except for same-page anchors)
document.addEventListener('DOMContentLoaded', function () {
  // Hide loader on page load
  hidePageLoader();

  const imagePreview = document.getElementById('imagePreview');
  const previewImage = document.getElementById('imagePreviewContent');
  let imageZoom = 1;
  let imageBaseWidth = 0;
  const fitPreviewImage = () => {
    if (!previewImage?.naturalWidth || !previewImage?.naturalHeight) return;
    const fitScale = Math.min((window.innerWidth * 0.92) / previewImage.naturalWidth,
      (window.innerHeight * 0.78) / previewImage.naturalHeight, 1);
    imageBaseWidth = previewImage.naturalWidth * fitScale;
    applyImageZoom();
  };
  const applyImageZoom = () => {
    if (previewImage && imageBaseWidth) previewImage.style.width = `${imageBaseWidth * imageZoom}px`;
  };
  const setImageZoom = (zoom) => {
    imageZoom = Math.max(0.5, Math.min(4, zoom));
    applyImageZoom();
  };
  previewImage?.addEventListener('load', fitPreviewImage);
  document.getElementById('imageZoomIn')?.addEventListener('click', () => setImageZoom(imageZoom + 0.25));
  document.getElementById('imageZoomOut')?.addEventListener('click', () => setImageZoom(imageZoom - 0.25));
  document.getElementById('imageZoomReset')?.addEventListener('click', () => setImageZoom(1));
  const closeImagePreview = () => {
    imagePreview?.classList.remove('active');
    imagePreview?.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('image-preview-open');
    if (previewImage) previewImage.src = '';
    setImageZoom(1);
  };
  document.addEventListener('click', function (event) {
    const thumbnail = event.target.closest('.item-image-thumb');
    if (thumbnail && imagePreview && previewImage) {
      event.preventDefault();
      imageBaseWidth = 0;
      previewImage.src = thumbnail.currentSrc || thumbnail.src;
      previewImage.alt = thumbnail.alt || 'Enlarged image';
      if (previewImage.complete) fitPreviewImage();
      setImageZoom(1);
      imagePreview.classList.add('active');
      imagePreview.setAttribute('aria-hidden', 'false');
      document.body.classList.add('image-preview-open');
      return;
    }
    if (event.target === imagePreview || event.target.closest('#imagePreviewClose')) closeImagePreview();
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeImagePreview();
  });

  // Show loader when clicking links
  document.querySelectorAll('a[href]').forEach(link => {
    link.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      // Skip if it's a same-page anchor, mailto, tel, or has data-confirm
      if (href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:') ||
          this.hasAttribute('download') || this.hasAttribute('data-confirm') || this.classList.contains('no-loader')) {
        return;
      }
      showPageLoader();
    });
  });

  // Show loader on form submissions
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
      showPageLoader();
    });
  });
});

// Pages restored with the browser back/forward cache do not fire DOMContentLoaded.
window.addEventListener('pageshow', hidePageLoader);
window.addEventListener('popstate', hidePageLoader);

// ---- Sidebar Toggle ----
document.addEventListener('DOMContentLoaded', function () {

  const sidebar = document.getElementById('sgiSidebar');
  const main = document.getElementById('sgiMain');
  const toggleBtn = document.getElementById('sidebarToggle');
  const overlay = document.getElementById('sidebarOverlay');

  const isMobile = () => window.innerWidth < 993;

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      if (isMobile()) {
        sidebar.classList.toggle('mobile-open');
        overlay.classList.toggle('active');
      } else {
        sidebar.classList.toggle('collapsed');
        main.classList.toggle('sidebar-collapsed');
        localStorage.setItem('sgiSidebarCollapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
      }
    });
  }

  if (overlay) {
    overlay.addEventListener('click', function () {
      sidebar.classList.remove('mobile-open');
      overlay.classList.remove('active');
    });
  }

  // Restore sidebar state on desktop
  if (!isMobile() && localStorage.getItem('sgiSidebarCollapsed') === '1') {
    sidebar?.classList.add('collapsed');
    main?.classList.add('sidebar-collapsed');
  }

  // ---- Alert dismiss ----
  document.querySelectorAll('.alert-close').forEach(btn => {
    btn.addEventListener('click', function () {
      this.closest('.sgi-alert')?.remove();
    });
  });

  // Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.sgi-alert:not(.sgi-alert-error)').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.5s';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 500);
    }, 5000);
  });

  // ---- Dropdown menus ----
  document.querySelectorAll('[data-dropdown]').forEach(trigger => {
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      const menu = document.getElementById(this.dataset.dropdown);
      if (menu) menu.classList.toggle('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.sgi-dropdown-menu.open').forEach(m => m.classList.remove('open'));
  });

  // ---- Password show/hide ----
  document.querySelectorAll('[data-show-password]').forEach(btn => {
    btn.addEventListener('click', function () {
      const inputId = this.dataset.showPassword;
      const input = document.getElementById(inputId);
      if (input) {
        if (input.type === 'password') {
          input.type = 'text';
          this.innerHTML = '<i class="bi bi-eye-slash"></i>';
        } else {
          input.type = 'password';
          this.innerHTML = '<i class="bi bi-eye"></i>';
        }
      }
    });
  });

  // ---- Confirm dialogs ----
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', function (e) {
      if (!confirm(this.dataset.confirm || 'Are you sure?')) {
        e.preventDefault();
      }
    });
  });

  // ---- Duration counters ----
  document.querySelectorAll('[data-started-at]').forEach(el => {
    const startedAt = new Date(el.dataset.startedAt);
    if (isNaN(startedAt)) return;

    function update() {
      const diff = Math.floor((Date.now() - startedAt) / 1000);
      const h = Math.floor(diff / 3600);
      const m = Math.floor((diff % 3600) / 60);
      const s = diff % 60;
      el.textContent = h > 0
        ? `${h}h ${m}m`
        : m > 0
        ? `${m}m ${s}s`
        : `${s}s`;
    }
    update();
    setInterval(update, 1000);
  });

  // ---- BOM Editor ----
  initBomEditor();

  // ---- Dispatch machine count change ----
  const machineCountInput = document.getElementById('machineCount');
  if (machineCountInput) {
    machineCountInput.addEventListener('change', function() {
      const form = this.closest('form');
      if (form) {
        const url = new URL(window.location.href);
        const machineId = document.getElementById('machineSelect')?.value;
        if (machineId) {
          url.searchParams.set('machine', machineId);
          url.searchParams.set('count', this.value);
          window.location.href = url.toString();
        }
      }
    });
  }

  const machineSelect = document.getElementById('machineSelect');
  if (machineSelect) {
    machineSelect.addEventListener('change', function() {
      const url = new URL(window.location.href);
      url.searchParams.set('machine', this.value);
      url.searchParams.set('count', document.getElementById('machineCount')?.value || 1);
      window.location.href = url.toString();
    });
  }

});


// ---- BOM Editor ----
function initBomEditor() {
  const bomContainer = document.getElementById('bomTableBody');
  const addBomBtn = document.getElementById('addBomRow');
  const bomDataInput = document.getElementById('bomData');
  const bomItemsData = document.getElementById('bomItemsData');
  const bomPagination = document.getElementById('bomPagination');
  const openBulkImportBtn = document.getElementById('openBulkImportBom');
  const bulkImportBtn = document.getElementById('bulkImportBom');
  const bulkImportDialog = document.getElementById('bulkImportDialog');
  const closeBulkImportBtn = document.getElementById('closeBulkImportDialog');
  const bulkPrefixInput = document.getElementById('bulkItemPrefix');
  const bulkQuantityInput = document.getElementById('bulkItemQuantity');
  const bulkStatus = document.getElementById('bulkImportStatus');
  const loadingOverlay = document.getElementById('machineLoadingOverlay');
  const loadingMessage = document.getElementById('machineLoadingMessage');
  const machineForm = document.getElementById('machineForm');

  if (!bomContainer || !addBomBtn || !bomDataInput) return;

  function setMachineBusy(message, isBusy) {
    if (!loadingOverlay) return;
    loadingMessage.textContent = message;
    loadingOverlay.style.display = isBusy ? 'flex' : 'none';
    loadingOverlay.setAttribute('aria-hidden', isBusy ? 'false' : 'true');
  }

  let items = [];
  try { items = JSON.parse(bomItemsData?.textContent || '[]'); } catch(e) {}
  const itemsById = new Map(items.map(item => [String(item.id), {
    ...item, id: String(item.id), label: `${item.code} — ${item.name}`,
  }]));

  let bomRows = [];
  try { bomRows = JSON.parse(bomDataInput.value || '[]'); } catch(e) {}

  function captureVisibleBomEdits() {
    bomContainer.querySelectorAll('.bom-item-select').forEach(input => {
      const row = bomRows[Number(input.dataset.idx)];
      if (!row) return;
      const currentSelection = itemsById.get(String(row.item_id));
      const selected = currentSelection?.label === input.value
        ? currentSelection
        : [...itemsById.values()].find(item => item.label === input.value);
      if (selected) {
        row.item_id = selected.id;
        row.item_label = selected.label;
        row.item_code = selected.code;
        row.item_name = selected.name;
        row.item_image = selected.image || '';
      } else {
        row.item_id = '';
        row.item_label = input.value;
        row.item_code = '';
        row.item_name = '';
        row.item_image = '';
      }
    });
    bomContainer.querySelectorAll('.bom-qty-input').forEach(input => {
      const row = bomRows[Number(input.dataset.idx)];
      if (row) row.quantity = parseFloat(input.value) || 0;
    });
    syncBomData();
  }

  machineForm?.addEventListener('submit', function() {
    captureVisibleBomEdits();
    setMachineBusy('Saving machine and BOM…', true);
  });
  const defaultPageSize = bomPagination?.dataset.defaultPerPage || '20';
  let bomPageSize = defaultPageSize === 'all' ? Infinity : (parseInt(defaultPageSize, 10) || 20);
  let bomCurrentPage = 1;

  function updateBomPagination() {
    if (!bomPagination) return;
    const total = bomRows.length;
    if (!total) {
      bomPagination.innerHTML = '';
      return;
    }
    const totalPages = bomPageSize === Infinity ? 1 : Math.ceil(total / bomPageSize);
    bomCurrentPage = Math.min(Math.max(1, bomCurrentPage), totalPages);
    const start = bomPageSize === Infinity ? 1 : ((bomCurrentPage - 1) * bomPageSize + 1);
    const end = bomPageSize === Infinity ? total : Math.min(bomCurrentPage * bomPageSize, total);
    bomPagination.innerHTML = '';

    const container = document.createElement('div');
    container.className = 'pagination-container';
    const info = document.createElement('div');
    info.className = 'pagination-info';
    info.textContent = `Showing ${start}-${end} of ${total}`;
    container.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'pagination-controls';
    const nav = document.createElement('div');
    nav.className = 'pagination-nav';
    const previous = document.createElement('button');
    previous.type = 'button';
    previous.className = `pagination-btn pagination-btn-large${bomCurrentPage === 1 ? ' disabled' : ''}`;
    previous.innerHTML = '<i class="bi bi-chevron-left"></i>';
    previous.disabled = bomCurrentPage === 1;
    previous.title = 'Previous Page';
    previous.addEventListener('click', () => { captureVisibleBomEdits(); bomCurrentPage--; renderRows(); });
    nav.appendChild(previous);

    const ranges = document.createElement('div');
    ranges.className = 'pagination-ranges';
    for (let page = Math.max(1, bomCurrentPage - 2); page <= Math.min(totalPages, bomCurrentPage + 2); page++) {
      const pageButton = document.createElement('button');
      pageButton.type = 'button';
      pageButton.className = `pagination-range${page === bomCurrentPage ? ' active' : ''}`;
      pageButton.textContent = page;
      pageButton.addEventListener('click', () => { captureVisibleBomEdits(); bomCurrentPage = page; renderRows(); });
      ranges.appendChild(pageButton);
    }
    nav.appendChild(ranges);

    const next = document.createElement('button');
    next.type = 'button';
    next.className = `pagination-btn pagination-btn-large${bomCurrentPage === totalPages ? ' disabled' : ''}`;
    next.innerHTML = '<i class="bi bi-chevron-right"></i>';
    next.disabled = bomCurrentPage === totalPages;
    next.title = 'Next Page';
    next.addEventListener('click', () => { captureVisibleBomEdits(); bomCurrentPage++; renderRows(); });
    nav.appendChild(next);
    controls.appendChild(nav);

    const dropdown = document.createElement('div');
    dropdown.className = 'pagination-dropdown';
    const select = document.createElement('select');
    select.className = 'sgi-select pagination-select';
    select.setAttribute('aria-label', 'Rows per page');
    [['20', '20'], ['50', '50'], ['100', '100'], ['500', '500'], ['all', 'All']].forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      option.selected = (value === 'all' && bomPageSize === Infinity) || Number(value) === bomPageSize;
      select.appendChild(option);
    });
    select.addEventListener('change', function() {
      captureVisibleBomEdits();
      bomPageSize = this.value === 'all' ? Infinity : Number(this.value);
      bomCurrentPage = 1;
      renderRows();
    });
    dropdown.append(select, Object.assign(document.createElement('span'), { className: 'pagination-label', textContent: 'rows' }));
    controls.appendChild(dropdown);
    container.appendChild(controls);
    bomPagination.appendChild(container);
  }

  function renderRows(showLoading = true) {
    const render = () => {
    bomContainer.innerHTML = '';
    updateBomPagination();
    if (bomRows.length === 0) {
      bomContainer.innerHTML = '<tr><td colspan="4" class="text-muted" style="padding:20px;text-align:center;">No components added yet. Click "Add Component".</td></tr>';
      return;
    }
    const pageStart = bomPageSize === Infinity ? 0 : (bomCurrentPage - 1) * bomPageSize;
    const pageEnd = bomPageSize === Infinity ? bomRows.length : Math.min(pageStart + bomPageSize, bomRows.length);
    bomRows.slice(pageStart, pageEnd).forEach((row, pageIdx) => {
      const idx = pageStart + pageIdx;
      const tr = document.createElement('tr');
      const selected = row.item_label || (row.item_code ? `${row.item_code} — ${row.item_name || ''}` : '');
      tr.innerHTML = `
        <td style="padding:8px 12px;">${idx + 1}</td>
        <td style="padding:8px 12px;">
          <div class="bom-autocomplete">
            <div style="display:flex;align-items:center;gap:8px;">
              <img class="bom-selected-image" alt="" loading="lazy" decoding="async"
                style="width:42px;height:42px;object-fit:cover;border-radius:5px;border:1px solid var(--sgi-border);${row.item_image ? '' : 'display:none;'}">
              <input type="text" class="sgi-input bom-item-select" data-idx="${idx}"
                value="${selected.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')}"
                placeholder="Search item code or name" autocomplete="off" style="width:100%;">
            </div>
            <div class="bom-suggestions" role="listbox"></div>
          </div>
        </td>
        <td style="padding:8px 12px;">
          <input type="number" class="sgi-input bom-qty-input" data-idx="${idx}"
            value="${row.quantity || ''}" min="0.01" step="0.01" style="width:100px;">
        </td>
        <td style="padding:8px 12px;">
          <button type="button" class="bom-row-remove" data-idx="${idx}" title="Remove">
            <i class="bi bi-trash3"></i>
          </button>
        </td>
      `;
      const selectedImage = tr.querySelector('.bom-selected-image');
      if (row.item_image) selectedImage.src = row.item_image;
      bomContainer.appendChild(tr);
    });

    // Bind events
    bomContainer.querySelectorAll('.bom-item-select').forEach(input => {
      const suggestions = input.closest('.bom-autocomplete').querySelector('.bom-suggestions');
      let searchRevision = 0;
      const showSuggestions = (query = '') => {
        const revision = ++searchRevision;
        suggestions.innerHTML = '<div style="padding:10px 12px;color:var(--sgi-text-muted);"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Searching items…</div>';
        suggestions.classList.add('show');
        suggestions.setAttribute('aria-busy', 'true');
        window.requestAnimationFrame(() => {
        if (revision !== searchRevision) return;
        const normalizedQuery = query.trim().toLowerCase();
        const currentIndex = +input.dataset.idx;
        const selectedElsewhere = new Set(
          bomRows
            .filter((row, index) => index !== currentIndex && row.item_id)
            .map(row => String(row.item_id))
        );
        const matches = items.filter(item =>
          !selectedElsewhere.has(String(item.id)) && (
            item.code.toLowerCase().includes(normalizedQuery) ||
            item.name.toLowerCase().includes(normalizedQuery)
          )
        ).slice(0, 50);
        suggestions.replaceChildren();
        matches.forEach(item => {
          const option = document.createElement('div');
          option.className = 'bom-suggestion';
          option.setAttribute('role', 'option');
          option.dataset.itemId = item.id;
          const code = document.createElement('div');
          code.className = 'bom-suggestion-code';
          code.textContent = item.code;
          const name = document.createElement('div');
          name.className = 'bom-suggestion-name';
          name.textContent = item.name;
          option.append(code, name);
          suggestions.appendChild(option);
        });
        suggestions.classList.toggle('show', matches.length > 0);
        suggestions.setAttribute('aria-busy', 'false');
        });
      };
      input.addEventListener('input', function() {
        const idx = +this.dataset.idx;
        bomRows[idx].item_id = '';
        bomRows[idx].item_label = this.value;
        bomRows[idx].item_code = '';
        bomRows[idx].item_name = '';
        bomRows[idx].item_image = '';
        const selectedImage = this.parentElement.querySelector('.bom-selected-image');
        selectedImage.removeAttribute('src');
        selectedImage.style.display = 'none';
        syncBomData();
        showSuggestions(this.value);
      });
      input.addEventListener('focus', function() {
        showSuggestions(this.value);
      });
      suggestions.addEventListener('mousedown', function(event) {
        const option = event.target.closest('.bom-suggestion');
        if (!option) return;
        event.preventDefault();
        const idx = +input.dataset.idx;
        const item = itemsById.get(option.dataset.itemId);
        if (!item) return;
        input.value = item.label;
        bomRows[idx].item_id = item.id;
        bomRows[idx].item_label = item.label;
        bomRows[idx].item_code = item.code;
        bomRows[idx].item_name = item.name;
        bomRows[idx].item_image = item.image || '';
        const selectedImage = input.parentElement.querySelector('.bom-selected-image');
        if (item.image) {
          selectedImage.src = item.image;
          selectedImage.style.display = '';
        } else {
          selectedImage.removeAttribute('src');
          selectedImage.style.display = 'none';
        }
        suggestions.classList.remove('show');
        syncBomData();
      });
    });
    bomContainer.querySelectorAll('.bom-qty-input').forEach(inp => {
      inp.addEventListener('input', function() {
        const idx = +this.dataset.idx;
        bomRows[idx].quantity = parseFloat(this.value) || 0;
        syncBomData();
      });
    });
    bomContainer.querySelectorAll('.bom-row-remove').forEach(btn => {
      btn.addEventListener('click', function() {
        const idx = +this.dataset.idx;
        captureVisibleBomEdits();
        bomRows.splice(idx, 1);
        renderRows();
        syncBomData();
      });
    });
    };

    if (showLoading) {
      bomContainer.innerHTML = '<tr><td colspan="4" role="status" style="padding:20px;text-align:center;color:var(--sgi-text-muted);"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Loading BOM items…</td></tr>';
      window.requestAnimationFrame(render);
    } else {
      render();
    }
  }

  document.addEventListener('click', function(event) {
    if (!event.target.closest('.bom-autocomplete')) {
      bomContainer.querySelectorAll('.bom-suggestions').forEach(list => list.classList.remove('show'));
    }
  });

  function syncBomData() {
    bomDataInput.value = JSON.stringify(bomRows);
  }

  addBomBtn.addEventListener('click', function() {
    captureVisibleBomEdits();
    bomRows.push({ item_id: '', item_code: '', item_name: '', quantity: 1 });
    bomCurrentPage = bomPageSize === Infinity ? 1 : Math.ceil(bomRows.length / bomPageSize);
    renderRows();
    syncBomData();
  });

  openBulkImportBtn?.addEventListener('click', function() {
    if (bulkStatus) bulkStatus.textContent = '';
    bulkImportDialog?.showModal();
    bulkPrefixInput?.focus();
  });
  closeBulkImportBtn?.addEventListener('click', function() {
    bulkImportDialog?.close();
  });

  bulkImportBtn?.addEventListener('click', function() {
    const prefix = bulkPrefixInput?.value.trim() || '';
    const quantity = Number(bulkQuantityInput?.value);
    if (!prefix) {
      bulkStatus.textContent = 'Enter an item code prefix first.';
      bulkPrefixInput?.focus();
      return;
    }
    if (!Number.isFinite(quantity) || quantity <= 0) {
      bulkStatus.textContent = 'Enter a default quantity greater than zero.';
      bulkQuantityInput?.focus();
      return;
    }

    setMachineBusy('Adding matching BOM items…', true);
    window.requestAnimationFrame(() => {
      captureVisibleBomEdits();
      const existingIds = new Set(bomRows.map(row => String(row.item_id)).filter(Boolean));
      const matches = items.filter(item => item.code.startsWith(prefix)).map(item => itemsById.get(String(item.id)));
      const newItems = matches.filter(item => !existingIds.has(String(item.id)));
      newItems.forEach(item => bomRows.push({
        item_id: item.id,
        item_code: item.code,
        item_name: item.name,
        item_image: item.image || '',
        item_label: item.label,
        quantity,
      }));
      if (newItems.length) {
        bomCurrentPage = bomPageSize === Infinity ? 1 : Math.ceil(bomRows.length / bomPageSize);
      }

      bulkStatus.textContent = matches.length === 0
        ? `No active items found with code prefix “${prefix}”.`
        : `${newItems.length} item${newItems.length === 1 ? '' : 's'} added${matches.length > newItems.length ? `; ${matches.length - newItems.length} already in the BOM skipped` : ''}.`;
      renderRows(true);
      syncBomData();
      setMachineBusy('', false);
      if (matches.length > 0) bulkImportDialog?.close();
    });
  });

  renderRows();
  syncBomData();
}


// ---- Item search for stock move ----
function filterBatchSelector(value) {
  const rows = document.querySelectorAll('.batch-option-row');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(value.toLowerCase()) ? '' : 'none';
  });
}

// ---- Export Table to Excel (CSV) ----
function exportTableToExcel(tableId, filename) {
  const table = document.getElementById(tableId);
  if (!table) return;

  let csv = [];
  const rows = table.querySelectorAll('tr');

  for (let i = 0; i < rows.length; i++) {
    const row = [], cols = rows[i].querySelectorAll('td, th');

    for (let j = 0; j < cols.length; j++) {
      let data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').replace(/"/g, '""');
      data = '"' + data + '"';
      row.push(data);
    }
    csv.push(row.join(','));
  }

  const csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
  const downloadLink = document.createElement('a');
  downloadLink.download = filename + '.csv';
  downloadLink.href = window.URL.createObjectURL(csvFile);
  downloadLink.style.display = 'none';
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
}

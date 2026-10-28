/* ============================================================
   SGIERP — Main JavaScript
   ============================================================ */

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
  const allItemsData = document.getElementById('allItemsData');

  if (!bomContainer || !addBomBtn || !bomDataInput) return;

  let items = [];
  try { items = JSON.parse(allItemsData?.textContent || '[]'); } catch(e) {}

  let bomRows = [];
  try { bomRows = JSON.parse(bomDataInput.value || '[]'); } catch(e) {}

  function renderRows() {
    bomContainer.innerHTML = '';
    if (bomRows.length === 0) {
      bomContainer.innerHTML = '<tr><td colspan="4" class="text-muted" style="padding:20px;text-align:center;">No components added yet. Click "Add Component".</td></tr>';
      return;
    }
    bomRows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      const itemOptions = items.map(it =>
        `<option value="${it.id}" ${it.id == row.item_id ? 'selected' : ''}>${it.code} - ${it.name}</option>`
      ).join('');
      tr.innerHTML = `
        <td style="padding:8px 12px;">${idx + 1}</td>
        <td style="padding:8px 12px;">
          <select class="sgi-select bom-item-select" data-idx="${idx}" style="width:100%;">
            <option value="">-- Select Item --</option>
            ${itemOptions}
          </select>
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
      bomContainer.appendChild(tr);
    });

    // Bind events
    bomContainer.querySelectorAll('.bom-item-select').forEach(sel => {
      sel.addEventListener('change', function() {
        const idx = +this.dataset.idx;
        const selected = items.find(it => it.id == this.value);
        bomRows[idx].item_id = this.value;
        bomRows[idx].item_code = selected?.code || '';
        bomRows[idx].item_name = selected?.name || '';
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
        bomRows.splice(idx, 1);
        renderRows();
        syncBomData();
      });
    });
  }

  function syncBomData() {
    bomDataInput.value = JSON.stringify(bomRows);
  }

  addBomBtn.addEventListener('click', function() {
    bomRows.push({ item_id: '', item_code: '', item_name: '', quantity: 1 });
    renderRows();
    syncBomData();
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

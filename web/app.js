/**
 * Pizza Radar Lisboa — Lógica da Interface Web
 *
 * Invariantes de Engenharia:
 * 1. Zero IA em runtime (100% determinístico e previsível).
 * 2. 4 rankings explicáveis e separados.
 * 3. Transparência na incerteza (loja ou canal desconhecido comunicado com honestidade).
 * 4. Sem checkout, sem recolha de moradas nem pagamentos.
 */

(function () {
  'use strict';

  // Estado da Aplicação
  const state = {
    allGroups: [],
    stats: null,
    activeRanking: 'LOWEST_ABSOLUTE_PRICE',
    filterVendor: 'ALL',
    filterChannel: 'ALL',
    filterDay: 'ALL',
    filterComparableOnly: false,
    searchQuery: '',
  };

  // Explicações dos Rankings
  const RANKING_EXPLANATIONS = {
    LOWEST_ABSOLUTE_PRICE: {
      title: 'Menor Preço Absoluto',
      text: 'Apresenta primeiro as opções com o desembolso mais baixo em euros (€), permitindo poupar no valor total a pagar.',
    },
    HIGHEST_DISCOUNT: {
      title: 'Maior Desconto Comprovado',
      text: 'Ordena pela maior percentagem de desconto comprovada face ao preço original de tabela. Ofertas sem preço de tabela de referência surgem no final.',
    },
    BEST_UNIT_PRICE: {
      title: 'Melhor Preço / Pizza',
      text: 'Calcula o custo por unidade inteira. Exclui estritamente ofertas onde a contagem de pizzas não é declarada ou comprovada pelo operador.',
    },
    RECENTLY_OBSERVED: {
      title: 'Recém Observadas',
      text: 'Ordena pelas campanhas mais recentemente verificadas e confirmadas ativas pelos coletores periódicos.',
    },
  };

  // Nomes amigáveis dos canais
  const CHANNEL_LABELS = {
    DELIVERY: '🛵 Entrega',
    TAKE_AWAY: '🥡 Take Away',
    DINE_IN: '🍽️ No Restaurante',
  };

  // Nomes amigáveis das marcas
  const VENDOR_LABELS = {
    DOMINOS: "Domino's",
    PAPA_JOHNS: "Papa John's",
    PIZZA_HUT: 'Pizza Hut',
    TELEPIZZA: 'Telepizza',
  };

  // Elementos DOM
  const elements = {
    promosGrid: document.getElementById('promos-grid'),
    emptyState: document.getElementById('empty-state'),
    resultsCount: document.getElementById('results-count'),
    btnResetFilters: document.getElementById('btn-reset-filters'),
    btnClearEmpty: document.getElementById('btn-clear-empty'),
    rankingTabs: document.querySelectorAll('.ranking-tab'),
    rankingExplanation: document.getElementById('explanation-text'),
    vendorChips: document.querySelectorAll('#vendor-chips .chip'),
    channelChips: document.querySelectorAll('#channel-chips .chip'),
    selectDay: document.getElementById('select-day'),
    searchInput: document.getElementById('search-input'),
    toggleComparable: document.getElementById('toggle-comparable'),
    statTotalPromos: document.getElementById('stat-total-promos'),
    statMinPrice: document.getElementById('stat-min-price'),
    statUnitPrice: document.getElementById('stat-unit-price'),
    statLocation: document.getElementById('stat-location'),
    dataModeBanner: document.getElementById('data-mode-banner'),
    dataModeText: document.getElementById('data-mode-text'),
    statusText: document.getElementById('status-text'),
  };

  // Inicialização
  async function init() {
    setupEventListeners();
    await loadData();
  }

  // Carregar dados de snapshot
  async function loadData() {
    try {
      elements.resultsCount.textContent = 'A carregar promoções públicas...';
      const response = await fetch('data/promotions.json');
      if (!response.ok) {
        throw new Error(`Falha HTTP ao carregar snapshot: ${response.status}`);
      }
      const data = await response.json();
      state.allGroups = data.groups || [];
      state.stats = data.stats || {};
      state.dataMode = data.data_mode || 'demo';

      handleDataMode(state.dataMode);
      updateMetricsBanner(data);
      applyFiltersAndRender();
    } catch (err) {
      console.error('Erro ao carregar promotions.json:', err);
      elements.promosGrid.innerHTML = `
        <div class="empty-state" role="alert" style="grid-column: 1 / -1;">
          <div class="empty-icon">⚠️</div>
          <h3 class="empty-title">Erro ao carregar promoções</h3>
          <p class="empty-message">Não foi possível carregar os dados das promoções. Verifica a ligação ou tenta novamente mais tarde.</p>
        </div>
      `;
      elements.resultsCount.textContent = 'Erro ao carregar dados.';
    }
  }

  // Tratamento do Modo de Dados (Demo vs Live)
  function handleDataMode(mode) {
    const isLive = mode === 'live';
    if (elements.dataModeBanner) {
      if (!isLive) {
        elements.dataModeBanner.style.display = 'flex';
        if (elements.dataModeText) {
          elements.dataModeText.textContent = 'Dados de demonstração — atualização automática ainda não ativa';
        }
      } else {
        elements.dataModeBanner.style.display = 'none';
      }
    }

    if (elements.statusText) {
      if (isLive) {
        elements.statusText.textContent = '4 marcas monitorizadas • Atualizado 2x ao dia';
      } else {
        elements.statusText.textContent = '4 marcas monitorizadas • Modo de demonstração';
      }
    }
  }

  // Atualizar Banner de Métricas Rápidas
  function updateMetricsBanner(data) {
    if (elements.statTotalPromos) {
      elements.statTotalPromos.textContent = state.allGroups.length;
    }
    if (elements.statLocation && data.location_scope) {
      elements.statLocation.textContent = data.location_scope;
    }
    if (elements.statMinPrice && state.stats && state.stats.min_price_cents !== null && state.stats.min_price_cents !== undefined) {
      elements.statMinPrice.textContent = formatEuros(state.stats.min_price_cents / 100);
    }
    if (elements.statUnitPrice && state.stats && state.stats.cheapest_pizza_cents !== null && state.stats.cheapest_pizza_cents !== undefined) {
      elements.statUnitPrice.textContent = formatEuros(state.stats.cheapest_pizza_cents / 100) + ' / pizza';
    }
  }

  // Configurar Ouvintes de Eventos
  function setupEventListeners() {
    // Tabs de Ranking
    elements.rankingTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        elements.rankingTabs.forEach((t) => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        state.activeRanking = tab.dataset.ranking;
        updateRankingExplanation();
        applyFiltersAndRender();
      });
    });

    // Chips de Fornecedor
    elements.vendorChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.vendorChips.forEach((c) => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        state.filterVendor = chip.dataset.vendor;
        applyFiltersAndRender();
      });
    });

    // Chips de Canal
    elements.channelChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.channelChips.forEach((c) => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        state.filterChannel = chip.dataset.channel;
        applyFiltersAndRender();
      });
    });

    // Dropdown Dia da Semana
    if (elements.selectDay) {
      elements.selectDay.addEventListener('change', (e) => {
        state.filterDay = e.target.value;
        applyFiltersAndRender();
      });
    }

    // Toggle Apenas Comparáveis
    if (elements.toggleComparable) {
      elements.toggleComparable.addEventListener('change', (e) => {
        state.filterComparableOnly = e.target.checked;
        applyFiltersAndRender();
      });
    }

    // Campo de Pesquisa com debounce simples
    if (elements.searchInput) {
      let debounceTimeout = null;
      elements.searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          state.searchQuery = e.target.value.trim().toLowerCase();
          applyFiltersAndRender();
        }, 150);
      });
    }

    // Botões de Limpeza de Filtros
    if (elements.btnResetFilters) {
      elements.btnResetFilters.addEventListener('click', resetFilters);
    }
    if (elements.btnClearEmpty) {
      elements.btnClearEmpty.addEventListener('click', resetFilters);
    }
  }

  // Atualizar Explicação do Ranking Ativo
  function updateRankingExplanation() {
    const info = RANKING_EXPLANATIONS[state.activeRanking];
    if (info && elements.rankingExplanation) {
      elements.rankingExplanation.innerHTML = `<strong>${info.title}:</strong> ${info.text}`;
    }
  }

  // Limpar Todos os Filtros
  function resetFilters() {
    state.filterVendor = 'ALL';
    state.filterChannel = 'ALL';
    state.filterDay = 'ALL';
    state.filterComparableOnly = false;
    state.searchQuery = '';

    elements.vendorChips.forEach((c) => {
      c.classList.toggle('active', c.dataset.vendor === 'ALL');
      c.setAttribute('aria-pressed', c.dataset.vendor === 'ALL' ? 'true' : 'false');
    });
    elements.channelChips.forEach((c) => {
      c.classList.toggle('active', c.dataset.channel === 'ALL');
      c.setAttribute('aria-pressed', c.dataset.channel === 'ALL' ? 'true' : 'false');
    });
    if (elements.selectDay) elements.selectDay.value = 'ALL';
    if (elements.searchInput) elements.searchInput.value = '';
    if (elements.toggleComparable) elements.toggleComparable.checked = false;

    applyFiltersAndRender();
  }

  // Aplicar Filtros e Ordenação
  function applyFiltersAndRender() {
    let filtered = [...state.allGroups];

    // 1. Filtro por Fornecedor
    if (state.filterVendor !== 'ALL') {
      filtered = filtered.filter((g) => g.vendor === state.filterVendor);
    }

    // 2. Filtro por Canal de Atendimento
    if (state.filterChannel !== 'ALL') {
      filtered = filtered.filter((g) => g.dispatch_methods && g.dispatch_methods.includes(state.filterChannel));
    }

    // 3. Filtro por Dia da Semana
    if (state.filterDay !== 'ALL') {
      filtered = filtered.filter((g) => {
        // Se a promoção não tem dias especificados, é válida todos os dias
        if (!g.days_of_week || g.days_of_week.length === 0) return true;
        return g.days_of_week.includes(state.filterDay);
      });
    }

    // 4. Filtro por Comparabilidade Unitária
    if (state.filterComparableOnly) {
      filtered = filtered.filter((g) => g.is_comparable_for_unit_price === true);
    }

    // 5. Pesquisa de Texto Livre
    if (state.searchQuery) {
      const q = state.searchQuery;
      filtered = filtered.filter((g) => {
        const titleMatch = (g.title || '').toLowerCase().includes(q);
        const descMatch = (g.description || '').toLowerCase().includes(q);
        const vendorMatch = (VENDOR_LABELS[g.vendor] || '').toLowerCase().includes(q);
        return titleMatch || descMatch || vendorMatch;
      });
    }

    // 6. Ordenação Determinística Conforme o Ranking Ativo
    filtered = sortGroupsByRanking(filtered, state.activeRanking);

    // 7. Renderização no DOM
    renderGrid(filtered);
    updateStatusBar(filtered.length);
  }

  // Algoritmos Determinísticos de Ordenação
  function sortGroupsByRanking(groups, ranking) {
    const list = [...groups];

    switch (ranking) {
      case 'LOWEST_ABSOLUTE_PRICE':
        return list.sort((a, b) => {
          const pA = a.min_price_cents !== null && a.min_price_cents !== undefined ? a.min_price_cents : 9999999;
          const pB = b.min_price_cents !== null && b.min_price_cents !== undefined ? b.min_price_cents : 9999999;
          if (pA !== pB) return pA - pB;
          return a.persistent_id.localeCompare(b.persistent_id);
        });

      case 'HIGHEST_DISCOUNT':
        return list.sort((a, b) => {
          const dA = a.max_discount_percentage !== null && a.max_discount_percentage !== undefined ? a.max_discount_percentage : -1;
          const dB = b.max_discount_percentage !== null && b.max_discount_percentage !== undefined ? b.max_discount_percentage : -1;
          if (dB !== dA) return dB - dA;
          // Desempate por menor preço
          const pA = a.min_price_cents || 9999999;
          const pB = b.min_price_cents || 9999999;
          if (pA !== pB) return pA - pB;
          return a.persistent_id.localeCompare(b.persistent_id);
        });

      case 'BEST_UNIT_PRICE':
        // Apenas itens comparáveis entram no topo; não comparáveis são excluídos do ranking unitário
        const comparableOnly = list.filter((g) => g.is_comparable_for_unit_price && g.min_price_per_pizza_cents !== null);
        return comparableOnly.sort((a, b) => {
          const uA = a.min_price_per_pizza_cents || 9999999;
          const uB = b.min_price_per_pizza_cents || 9999999;
          if (uA !== uB) return uA - uB;
          return a.persistent_id.localeCompare(b.persistent_id);
        });

      case 'RECENTLY_OBSERVED':
        return list.sort((a, b) => {
          const tA = a.most_recent_observed_at ? new Date(a.most_recent_observed_at).getTime() : 0;
          const tB = b.most_recent_observed_at ? new Date(b.most_recent_observed_at).getTime() : 0;
          if (tB !== tA) return tB - tA;
          return a.persistent_id.localeCompare(b.persistent_id);
        });

      default:
        return list;
    }
  }

  // Renderizar Cartões no DOM
  function renderGrid(groups) {
    if (!elements.promosGrid) return;

    if (groups.length === 0) {
      elements.promosGrid.style.display = 'none';
      if (elements.emptyState) elements.emptyState.style.display = 'flex';
      return;
    }

    elements.promosGrid.style.display = 'grid';
    if (elements.emptyState) elements.emptyState.style.display = 'none';

    elements.promosGrid.innerHTML = groups.map((g) => buildCardHTML(g)).join('');
  }

  // Construir HTML de um Cartão Promocional
  function buildCardHTML(group) {
    const vendorLabel = VENDOR_LABELS[group.vendor] || group.vendor;
    const channels = (group.dispatch_methods || [])
      .map((c) => CHANNEL_LABELS[c] || c)
      .join(' • ');

    // Preço e Desconto
    const displayPrice = group.display_price_label || 'Preço sob consulta';

    // Preço Original e Poupança
    let originalPriceHTML = '';
    let discountTagHTML = '';
    if (group.variants && group.variants.length > 0) {
      const bestDiscountVariant = group.variants.find((v) => v.computed_discount_percentage > 0);
      if (bestDiscountVariant && bestDiscountVariant.original_price_euros) {
        originalPriceHTML = `<span class="price-original">${formatEuros(bestDiscountVariant.original_price_euros)}</span>`;
        discountTagHTML = `<span class="discount-tag">-${Math.round(bestDiscountVariant.computed_discount_percentage)}%</span>`;
      }
    }

    // Preço por Pizza / Composição
    let unitPriceBadgeHTML = '';
    if (group.is_comparable_for_unit_price && group.min_price_per_pizza_euros) {
      const pizzaCountLabel = group.pizza_count ? `${group.pizza_count} pizzas` : 'Por pizza';
      unitPriceBadgeHTML = `
        <div class="unit-price-badge">
          <span>🍕</span>
          <span>${formatEuros(group.min_price_per_pizza_euros)} / pizza (${pizzaCountLabel})</span>
        </div>
      `;
    }

    // Âmbito Geográfico de Lojas
    let storeScopeHTML = '';
    if (group.store_scope === 'SPECIFIC_STORES' && group.all_store_names && group.all_store_names.length > 0) {
      storeScopeHTML = `
        <div class="meta-item">
          <span class="meta-icon" aria-hidden="true">📍</span>
          <span>Lojas em Lisboa: <strong>${escapeHTML(group.all_store_names.join(', '))}</strong></span>
        </div>
      `;
    } else if (group.store_scope === 'NATIONAL') {
      storeScopeHTML = `
        <div class="meta-item">
          <span class="meta-icon" aria-hidden="true">🇵🇹</span>
          <span>Válido em todas as lojas aderentes</span>
        </div>
      `;
    } else {
      // Incerteza comunicada com honestidade e transparência
      storeScopeHTML = `
        <div class="meta-item meta-unknown">
          <span class="meta-icon" aria-hidden="true">⚠️</span>
          <span>Lojas participantes não discriminadas no catálogo online oficial</span>
        </div>
      `;
    }

    // Frescura / Data de Observação
    const freshnessText = formatObservationDate(group.most_recent_observed_at);

    // CTA Oficial
    const sourceUrl = group.source_url || '#';

    return `
      <article class="promo-card" id="card-${escapeHTML(group.persistent_id)}">
        <header class="card-header">
          <span class="vendor-badge vendor-${escapeHTML(group.vendor)}">${escapeHTML(vendorLabel)}</span>
          <span class="dispatch-badge">${escapeHTML(channels)}</span>
        </header>

        <div class="card-body">
          <h3 class="card-title">${escapeHTML(group.title)}</h3>
          ${group.description ? `<p class="card-description">${escapeHTML(group.description)}</p>` : ''}

          <div class="pricing-block">
            <div class="price-main-row">
              <span class="price-value">${escapeHTML(displayPrice)}</span>
              ${originalPriceHTML}
              ${discountTagHTML}
            </div>
            ${unitPriceBadgeHTML}
          </div>

          <div class="card-meta">
            ${storeScopeHTML}
            <div class="meta-item">
              <span class="meta-icon" aria-hidden="true">🕒</span>
              <span>${freshnessText}</span>
            </div>
          </div>
        </div>

        <footer class="card-footer">
          <a href="${escapeHTML(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="btn-official">
            Ver oferta no site oficial
          </a>
        </footer>
      </article>
    `;
  }

  // Atualizar Barra de Estado
  function updateStatusBar(count) {
    const isFiltered = state.filterVendor !== 'ALL' ||
                       state.filterChannel !== 'ALL' ||
                       state.filterDay !== 'ALL' ||
                       state.filterComparableOnly ||
                       Boolean(state.searchQuery);

    if (count === 1) {
      elements.resultsCount.textContent = 'A apresentar 1 promoção encontrada';
    } else {
      elements.resultsCount.textContent = `A apresentar ${count} promoções encontradas`;
    }

    if (elements.btnResetFilters) {
      elements.btnResetFilters.style.display = isFiltered ? 'inline' : 'none';
    }
  }

  // Utilitários de Formatação
  function formatEuros(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return '—';
    return Number(amount).toFixed(2).replace('.', ',') + ' €';
  }

  function formatObservationDate(isoDateStr) {
    if (!isoDateStr) return 'Observação recente';
    try {
      const date = new Date(isoDateStr);
      return `Observado em ${date.toLocaleDateString('pt-PT')} às ${date.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      return 'Observação confirmada';
    }
  }

  function escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Arranque
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

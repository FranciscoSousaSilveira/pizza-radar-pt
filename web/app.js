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
    vendorStatus: {},
    activeRanking: 'LOWEST_ABSOLUTE_PRICE',
    filterProduct: 'ALL',
    filterVendor: 'ALL',
    filterChannel: 'ALL',
    filterDay: 'ALL',
    filterComparableOnly: false,
    filterOnlyOpenBrands: false,
    searchQuery: '',
    // Estado de Lojas de Lisboa
    stores: [],
    filterStoreBrand: 'ALL',
    filterStoreStatus: 'ALL', // 'ALL' ou 'OPEN'
    filterStoreService: 'ALL', // 'ALL', 'DELIVERY', 'TAKE_AWAY'
    storesSearchQuery: '',
    currentMobileView: 'promos', // 'promos' ou 'stores'
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
      text: 'Calcula o custo por unidade inteira de pizza (estritamente para pizzas e menus comparáveis). Exclui categoricamente complementos e sobremesas.',
    },
    RECENTLY_OBSERVED: {
      title: 'Recém Observadas',
      text: 'Ordena pelas campanhas mais recentemente verificadas e confirmadas ativas pelos coletores periódicos.',
    },
  };

  // Nomes amigáveis dos canais
  const CHANNEL_LABELS = {
    DELIVERY: 'Entrega',
    TAKE_AWAY: 'Take Away',
    DINE_IN: 'No Restaurante',
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
    productChips: document.querySelectorAll('#product-chips .chip'),
    vendorChips: document.querySelectorAll('#vendor-chips .chip'),
    channelChips: document.querySelectorAll('#channel-chips .chip'),
    filterOpenNowPromos: document.getElementById('filter-open-now-promos'),
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
    sourcesSummary: document.getElementById('sources-summary-text'),
    sourcesGrid: document.getElementById('sources-grid'),
    btnClearSearch: document.getElementById('btn-clear-search'),
    btnBackToTop: document.getElementById('btn-back-to-top'),
    // Elementos de Lojas de Lisboa
    radarSection: document.getElementById('radar-section'),
    storesSection: document.getElementById('stores-section'),
    btnViewPromos: document.getElementById('btn-view-promos'),
    btnViewStores: document.getElementById('btn-view-stores'),
    headerStoresCount: document.getElementById('header-stores-count'),
    storesGrid: document.getElementById('stores-grid'),
    storesEmptyState: document.getElementById('stores-empty-state'),
    storesResultsCount: document.getElementById('stores-results-count'),
    lisbonClockBadge: document.getElementById('lisbon-clock-badge'),
    storesSearchInput: document.getElementById('stores-search-input'),
    btnClearStoresSearch: document.getElementById('btn-clear-stores-search'),
    btnClearStoresEmpty: document.getElementById('btn-clear-stores-empty'),
    storeBrandChips: document.querySelectorAll('.chip-store-brand'),
    storeStatusChips: document.querySelectorAll('.chip-status'),
    storeServiceChips: document.querySelectorAll('.chip-service'),
    countStoresOpenNow: document.getElementById('count-stores-open-now'),
    countBrandAll: document.getElementById('count-brand-all'),
    countBrandDominos: document.getElementById('count-brand-dominos'),
    countBrandPapajohns: document.getElementById('count-brand-papajohns'),
    countBrandPizzahut: document.getElementById('count-brand-pizzahut'),
    countBrandTelepizza: document.getElementById('count-brand-telepizza'),
    navLinkPromos: document.getElementById('nav-link-promos'),
    navLinkStores: document.getElementById('nav-link-stores'),
  };

  // Inicialização
  async function init() {
    setupEventListeners();
    setupStoresEventListeners();
    await Promise.all([loadData(), loadStoresData()]);
    startLiveClock();
  }

  // Unifica grupos promocionais que partilham a mesma marca, título e preço em canais complementares
  function deduplicateVisualGroups(groups) {
    const unified = [];
    const seenMap = new Map();

    for (const group of groups) {
      const normTitle = (group.title || '').trim().toLowerCase();
      const priceKey = group.min_price_cents !== null && group.min_price_cents !== undefined ? group.min_price_cents : group.display_price_label;
      const key = `${group.vendor}|${normTitle}|${priceKey}|${group.offer_type}`;

      if (seenMap.has(key)) {
        const existing = seenMap.get(key);
        // Fundir métodos de atendimento (ex.: ['DELIVERY'] + ['TAKE_AWAY'])
        if (group.dispatch_methods) {
          for (const dm of group.dispatch_methods) {
            if (!existing.dispatch_methods.includes(dm)) {
              existing.dispatch_methods.push(dm);
            }
          }
        }
        // Fundir variantes de loja caso existam
        if (group.variants && existing.variants) {
          for (const v of group.variants) {
            if (!existing.variants.some((ev) => ev.variant_id === v.variant_id)) {
              existing.variants.push(v);
            }
          }
        }
      } else {
        const cloned = {
          ...group,
          dispatch_methods: [...(group.dispatch_methods || [])]
        };
        seenMap.set(key, cloned);
        unified.push(cloned);
      }
    }
    return unified;
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
      state.allGroups = deduplicateVisualGroups(data.groups || []);
      state.stats = data.stats || {};
      state.vendorStatus = data.vendor_status || {};
      state.dataMode = data.data_mode || 'demo';

      handleDataMode(state.dataMode, data);
      renderSourcesStatus(data);
      updateMetricsBanner(data);
      updateChipCounts(data);
      applyFiltersAndRender();
    } catch (err) {
      console.error('Erro ao carregar promotions.json:', err);
      elements.promosGrid.innerHTML = `
        <div class="empty-state" role="alert" style="grid-column: 1 / -1;">
          <h3 class="empty-title">Erro ao carregar promoções</h3>
          <p class="empty-message">Não foi possível carregar os dados das promoções. Verifica a ligação ou tenta novamente mais tarde.</p>
        </div>
      `;
      elements.resultsCount.textContent = 'Erro ao carregar dados.';
    }
  }

  // Tratamento do Modo de Dados (Demo vs Live) e Transparência
  function handleDataMode(mode, data) {
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
        const updated = data && data.vendors_updated_count !== undefined ? data.vendors_updated_count : 1;
        const total = (data && data.total_vendors_configured) || 4;
        elements.statusText.textContent = `${updated} de ${total} marcas atualizadas nesta recolha`;
      } else {
        elements.statusText.textContent = '4 marcas monitorizadas • Modo de demonstração';
      }
    }
  }

  // Renderizar Painel de Transparência de Fontes por Marca
  function renderSourcesStatus(data) {
    if (!elements.sourcesGrid) return;
    const statusMap = data.vendor_status || {};
    const knownVendors = ['DOMINOS', 'PAPA_JOHNS', 'PIZZA_HUT', 'TELEPIZZA'];
    const updatedCount = data.vendors_updated_count !== undefined ? data.vendors_updated_count : 0;
    const totalCount = data.total_vendors_configured || 4;

    if (elements.sourcesSummary) {
      if (data.data_mode === 'demo') {
        elements.sourcesSummary.textContent = 'Dados de demonstração local';
      } else {
        elements.sourcesSummary.textContent = `${updatedCount} de ${totalCount} marcas atualizadas nesta recolha`;
      }
    }

    elements.sourcesGrid.innerHTML = knownVendors.map((v) => {
      const info = statusMap[v] || { status: 'PENDING', message: 'A aguardar recolha' };
      const statusClass = `status-${(info.status || 'pending').toLowerCase()}`;
      const label = VENDOR_LABELS[v] || v;
      let coverageBadge = '';
      if (info.coverage_level === 'FEATURED') {
        const note = info.coverage_note || (v === 'TELEPIZZA' ? 'Telepizza Portugal — confirmar disponibilidade na loja/morada' : 'Campanhas principais publicadas no site oficial');
        coverageBadge = ` <span class="badge-coverage badge-coverage-featured" style="background:#e0f2fe;color:#0369a1;padding:2px 6px;border-radius:4px;font-size:0.75rem;font-weight:600;" title="${escapeHTML(note)}">Destaques</span>`;
      } else if (info.coverage_level === 'LIMITED') {
        coverageBadge = ' <span class="badge-coverage badge-coverage-limited" style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-size:0.75rem;font-weight:600;" title="Amostra limitada de ofertas">Limitada</span>';
      }
      return `
        <div class="source-item ${statusClass}" title="${escapeHTML(info.message || '')}">
          <span class="source-status-dot" aria-hidden="true"></span>
          <span class="source-name">${escapeHTML(label)}${coverageBadge}</span>
          <span class="source-desc">${escapeHTML(info.message || '')}</span>
        </div>
      `;
    }).join('');
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

  // Atualizar Contadores Dinâmicos nos Chips (Operate + Read)
  function updateChipCounts(data) {
    const groups = state.allGroups || data.groups || [];
    const total = groups.length;

    // Contadores por Tipo de Produto
    const pizzaCount = groups.filter((g) => g.offer_type === 'PIZZA').length;
    const menuCount = groups.filter((g) => g.offer_type === 'BUNDLE_WITH_PIZZA').length;
    const nonPizzaCount = groups.filter((g) => g.offer_type === 'NON_PIZZA').length;

    elements.productChips.forEach((chip) => {
      const type = chip.dataset.product;
      if (type === 'ALL') chip.textContent = `Todas as Ofertas (${total})`;
      else if (type === 'PIZZA') chip.textContent = `Pizzas (${pizzaCount})`;
      else if (type === 'BUNDLE_WITH_PIZZA') chip.textContent = `Menus (${menuCount})`;
      else if (type === 'NON_PIZZA') chip.textContent = `Acompanhamentos (${nonPizzaCount})`;
    });

    // Contadores por Marca
    const vendorCounts = {
      ALL: total,
      DOMINOS: groups.filter((g) => g.vendor === 'DOMINOS').length,
      PAPA_JOHNS: groups.filter((g) => g.vendor === 'PAPA_JOHNS').length,
      PIZZA_HUT: groups.filter((g) => g.vendor === 'PIZZA_HUT').length,
      TELEPIZZA: groups.filter((g) => g.vendor === 'TELEPIZZA').length,
    };

    elements.vendorChips.forEach((chip) => {
      const v = chip.dataset.vendor;
      const count = vendorCounts[v] !== undefined ? vendorCounts[v] : 0;
      const label = v === 'ALL' ? 'Todas' : (VENDOR_LABELS[v] || v);
      chip.textContent = `${label} (${count})`;
    });

    // Contadores por Canal
    elements.channelChips.forEach((chip) => {
      const ch = chip.dataset.channel;
      if (ch === 'ALL') {
        chip.textContent = `Todos (${total})`;
      } else {
        const count = groups.filter((g) => g.dispatch_methods && g.dispatch_methods.includes(ch)).length;
        const label = CHANNEL_LABELS[ch] || ch;
        chip.textContent = `${label} (${count})`;
      }
    });
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

    // Chips de Tipo de Produto (Pizzas vs Complementos)
    elements.productChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.productChips.forEach((c) => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        state.filterProduct = chip.dataset.product;
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

    // Filtro Lojas Abertas Agora nas Promoções
    if (elements.filterOpenNowPromos) {
      elements.filterOpenNowPromos.addEventListener('click', () => {
        state.filterOnlyOpenBrands = !state.filterOnlyOpenBrands;
        elements.filterOpenNowPromos.classList.toggle('active', state.filterOnlyOpenBrands);
        elements.filterOpenNowPromos.setAttribute('aria-pressed', state.filterOnlyOpenBrands ? 'true' : 'false');
        applyFiltersAndRender();
      });
    }

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

    // Campo de Pesquisa com debounce simples e botão limpar
    if (elements.searchInput) {
      let debounceTimeout = null;
      elements.searchInput.addEventListener('input', (e) => {
        const val = e.target.value;
        if (elements.btnClearSearch) {
          elements.btnClearSearch.style.display = val.length > 0 ? 'flex' : 'none';
        }
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          state.searchQuery = val.trim().toLowerCase();
          applyFiltersAndRender();
        }, 150);
      });
    }

    // Botão Limpar Pesquisa
    if (elements.btnClearSearch) {
      elements.btnClearSearch.addEventListener('click', () => {
        if (elements.searchInput) {
          elements.searchInput.value = '';
          elements.searchInput.focus();
        }
        state.searchQuery = '';
        elements.btnClearSearch.style.display = 'none';
        applyFiltersAndRender();
      });
    }

    // Botão Flutuante Voltar ao Topo
    if (elements.btnBackToTop) {
      elements.btnBackToTop.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      window.addEventListener('scroll', () => {
        if (window.scrollY > 350) {
          elements.btnBackToTop.style.display = 'flex';
        } else {
          elements.btnBackToTop.style.display = 'none';
        }
      }, { passive: true });
    }

    // Delegação de Eventos nos Cartões (Partilha e Expansão de Descrição)
    if (elements.promosGrid) {
      elements.promosGrid.addEventListener('click', async (e) => {
        // Toggle de Descrição Expandida ("Ver mais / Ver menos")
        const toggleBtn = e.target.closest('.btn-toggle-desc');
        if (toggleBtn) {
          const targetId = toggleBtn.dataset.target;
          const descEl = document.getElementById(targetId);
          if (descEl) {
            const isExpanded = descEl.classList.toggle('is-expanded');
            toggleBtn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
            const labelSpan = toggleBtn.querySelector('.toggle-label');
            if (labelSpan) {
              labelSpan.textContent = isExpanded ? 'Ver menos' : 'Ver mais';
            }
          }
          return;
        }

        // Partilha / Cópia de Hiperligação (Nativo em mobile, clipboard em desktop)
        const shareBtn = e.target.closest('.btn-share-promo');
        if (!shareBtn) return;
        const urlToCopy = shareBtn.dataset.url || window.location.href;
        const cardTitle = shareBtn.closest('.promo-card')?.querySelector('.card-title')?.textContent?.trim() || 'Pizza Radar PT';

        if (navigator.share) {
          try {
            await navigator.share({
              title: cardTitle,
              text: `${cardTitle} — Pizza Radar Lisboa`,
              url: urlToCopy,
            });
            return;
          } catch (err) {
            if (err && err.name === 'AbortError') return; // Cancelado pelo utilizador
          }
        }

        try {
          await navigator.clipboard.writeText(urlToCopy);
          const iconSpan = shareBtn.querySelector('span');
          if (iconSpan) {
            const originalText = iconSpan.textContent;
            iconSpan.textContent = '✓';
            iconSpan.style.color = '#15803D';
            shareBtn.title = 'Hiperligação copiada!';
            setTimeout(() => {
              iconSpan.textContent = originalText;
              iconSpan.style.color = '';
              shareBtn.title = 'Copiar hiperligação desta oferta';
            }, 1800);
          }
        } catch {
          // Fallback gracioso caso clipboard API esteja indisponível
        }
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
    state.filterProduct = 'ALL';
    state.filterVendor = 'ALL';
    state.filterChannel = 'ALL';
    state.filterDay = 'ALL';
    state.filterComparableOnly = false;
    state.filterOnlyOpenBrands = false;
    state.searchQuery = '';

    elements.productChips.forEach((c) => {
      c.classList.toggle('active', c.dataset.product === 'ALL');
      c.setAttribute('aria-pressed', c.dataset.product === 'ALL' ? 'true' : 'false');
    });
    elements.vendorChips.forEach((c) => {
      c.classList.toggle('active', c.dataset.vendor === 'ALL');
      c.setAttribute('aria-pressed', c.dataset.vendor === 'ALL' ? 'true' : 'false');
    });
    elements.channelChips.forEach((c) => {
      c.classList.toggle('active', c.dataset.channel === 'ALL');
      c.setAttribute('aria-pressed', c.dataset.channel === 'ALL' ? 'true' : 'false');
    });
    if (elements.filterOpenNowPromos) {
      elements.filterOpenNowPromos.classList.remove('active');
      elements.filterOpenNowPromos.setAttribute('aria-pressed', 'false');
    }
    if (elements.selectDay) elements.selectDay.value = 'ALL';
    if (elements.searchInput) elements.searchInput.value = '';
    if (elements.toggleComparable) elements.toggleComparable.checked = false;

    applyFiltersAndRender();
  }

  // Aplicar Filtros e Ordenação
  function applyFiltersAndRender() {
    let filtered = [...state.allGroups];

    // 0. Filtro por Tipo de Produto
    if (state.filterProduct === 'PIZZA') {
      filtered = filtered.filter((g) => g.offer_type === 'PIZZA');
    } else if (state.filterProduct === 'BUNDLE_WITH_PIZZA') {
      filtered = filtered.filter((g) => g.offer_type === 'BUNDLE_WITH_PIZZA');
    } else if (state.filterProduct === 'NON_PIZZA') {
      filtered = filtered.filter((g) => g.offer_type === 'NON_PIZZA');
    }

    // 1. Filtro por Fornecedor
    if (state.filterVendor !== 'ALL') {
      filtered = filtered.filter((g) => g.vendor === state.filterVendor);
    }

    // 1.1 Filtro por Marcas com Lojas Abertas Agora em Lisboa
    if (state.filterOnlyOpenBrands) {
      filtered = filtered.filter((g) => isBrandOpenNow(g.vendor));
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
        // Apenas ofertas de pizza comparáveis entram no ranking unitário (exclui categoricamente complementos)
        const comparableOnly = list.filter((g) =>
          (g.offer_type === 'PIZZA' || g.offer_type === 'BUNDLE_WITH_PIZZA') &&
          g.is_comparable_for_unit_price &&
          g.min_price_per_pizza_cents !== null
        );
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

    // Badges de Tipo e Preservação
    let offerTypeBadgeHTML = '';
    if (group.offer_type === 'PIZZA') {
      offerTypeBadgeHTML = '<span class="badge-offer-type type-pizza">Pizza</span>';
    } else if (group.offer_type === 'BUNDLE_WITH_PIZZA') {
      offerTypeBadgeHTML = '<span class="badge-offer-type type-bundle">Menu</span>';
    } else if (group.offer_type === 'NON_PIZZA') {
      offerTypeBadgeHTML = '<span class="badge-offer-type type-non-pizza">Acompanhamento</span>';
    }

    const vStatus = state.vendorStatus && state.vendorStatus[group.vendor];
    let preservedBadgeHTML = '';
    if (vStatus && (vStatus.status === 'STALE' || vStatus.status === 'PRESERVED')) {
      preservedBadgeHTML = '<span class="badge-preserved" title="Oferta preservada da recolha anterior">Preservada</span>';
    }

    // Badges de Canal de Atendimento no Cartão
    let channelBadgeHTML = '';
    const hasDelivery = (group.dispatch_methods || []).includes('DELIVERY');
    const hasTakeAway = (group.dispatch_methods || []).includes('TAKE_AWAY');
    if (hasDelivery && hasTakeAway) {
      channelBadgeHTML = '<span class="badge-channel badge-channel-both" title="Disponível para entrega e take away">🛵 Entrega & 🥡 Take Away</span>';
    } else if (hasDelivery) {
      channelBadgeHTML = '<span class="badge-channel badge-channel-delivery" title="Exclusivo entrega ao domicílio">🛵 Entrega</span>';
    } else if (hasTakeAway) {
      channelBadgeHTML = '<span class="badge-channel badge-channel-takeaway" title="Exclusivo levantamento em loja">🥡 Take Away</span>';
    }

    // Descrição e Botão Ver mais / Ver menos
    let descriptionHTML = '';
    if (group.description) {
      const descId = `desc-${escapeHTML(group.persistent_id)}`;
      const isLong = group.description.length > 70;
      descriptionHTML = `
        <div class="description-wrap">
          <p class="card-description" id="${descId}">${escapeHTML(group.description)}</p>
          ${isLong ? `
            <button type="button" class="btn-toggle-desc" aria-expanded="false" aria-controls="${descId}" data-target="${descId}">
              <span class="toggle-label">Ver mais</span>
              <svg viewBox="0 0 20 20" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M5 7.5l5 5 5-5"></path>
              </svg>
            </button>
          ` : ''}
        </div>
      `;
    }

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
    } else if (group.max_discount_percentage) {
      discountTagHTML = `<span class="discount-tag">-${Math.round(group.max_discount_percentage)}%</span>`;
    }

    // Preço por Pizza / Composição
    let unitPriceBadgeHTML = '';
    if (group.is_comparable_for_unit_price && group.min_price_per_pizza_euros) {
      const pizzaCountLabel = group.pizza_count ? `${group.pizza_count} pizzas` : 'Por pizza';
      unitPriceBadgeHTML = `
        <div class="unit-price-badge">
          <span>${formatEuros(group.min_price_per_pizza_euros)} / pizza <small>(${pizzaCountLabel})</small></span>
        </div>
      `;
    }

    // Âmbito Geográfico de Lojas
    let storeScopeHTML = '';
    if (group.store_scope === 'SPECIFIC_STORES' && group.all_store_names && group.all_store_names.length > 0) {
      storeScopeHTML = `
        <div class="meta-item">
          <span>Lojas em Lisboa: <strong>${escapeHTML(group.all_store_names.join(', '))}</strong></span>
        </div>
      `;
    } else if (group.store_scope === 'NATIONAL') {
      storeScopeHTML = `
        <div class="meta-item">
          <span>Válido em todas as lojas aderentes</span>
        </div>
      `;
    } else {
      const unknownText = group.vendor === 'TELEPIZZA'
        ? 'Telepizza Portugal — confirmar na loja/morada'
        : 'Lojas aderentes sob consulta no catálogo oficial';
      storeScopeHTML = `
        <div class="meta-item meta-unknown">
          <span>${escapeHTML(unknownText)}</span>
        </div>
      `;
    }

    // Frescura / Data de Observação
    const freshnessText = formatObservationDate(group.most_recent_observed_at);

    // CTA Oficial
    const sourceUrl = resolveDirectPromoUrl(group);

    // Super Desconto (destaque para economias >= 40%)
    let superDiscountHTML = '';
    if (group.max_discount_percentage && group.max_discount_percentage >= 40) {
      superDiscountHTML = `<span class="badge-super-discount" title="Desconto igual ou superior a 40%">Destaque</span>`;
    }

    // Imagem Oficial ou Fallback com Identidade da Marca
    let mediaHTML = '';
    if (group.image_url) {
      mediaHTML = `
        <div class="card-media card-image-wrap">
          <img src="${escapeHTML(group.image_url)}" alt="${escapeHTML(group.title)}" class="card-image" loading="lazy" decoding="async" onerror="this.onerror=null; this.parentElement.classList.add('has-fallback-active');">
          <div class="card-fallback-banner vendor-bg-${escapeHTML(group.vendor)}">
            <span class="fallback-brand">${escapeHTML(vendorLabel)}</span>
            <span class="fallback-sub">Oferta Oficial</span>
          </div>
          <div class="card-media-overlay"></div>
          <div class="floating-badge-top-left">
            <span class="vendor-badge vendor-${escapeHTML(group.vendor)}">${escapeHTML(vendorLabel)}</span>
          </div>
          ${discountTagHTML ? `<div class="floating-badge-top-right">${discountTagHTML}</div>` : ''}
          <div class="floating-badge-bottom-right">
            <span class="dispatch-badge">${escapeHTML(channels)}</span>
          </div>
        </div>
      `;
    } else {
      mediaHTML = `
        <div class="card-media card-image-wrap has-fallback-active">
          <div class="card-fallback-banner vendor-bg-${escapeHTML(group.vendor)}">
            <span class="fallback-brand">${escapeHTML(vendorLabel)}</span>
            <span class="fallback-sub">Oferta Oficial</span>
          </div>
          <div class="card-media-overlay"></div>
          <div class="floating-badge-top-left">
            <span class="vendor-badge vendor-${escapeHTML(group.vendor)}">${escapeHTML(vendorLabel)}</span>
          </div>
          ${discountTagHTML ? `<div class="floating-badge-top-right">${discountTagHTML}</div>` : ''}
          <div class="floating-badge-bottom-right">
            <span class="dispatch-badge">${escapeHTML(channels)}</span>
          </div>
        </div>
      `;
    }

    const brandIsOpen = isBrandOpenNow(group.vendor);
    const storeStatusBadgeHTML = brandIsOpen
      ? `<span class="badge-brand-status badge-brand-open" title="Lojas desta marca em Lisboa abertas agora"><span class="status-dot-small dot-open" aria-hidden="true"></span> Aberta agora</span>`
      : `<span class="badge-brand-status badge-brand-closed" title="Lojas desta marca em Lisboa fechadas neste momento"><span class="status-dot-small dot-closed" aria-hidden="true"></span> Fechada agora</span>`;

    return `
      <article class="promo-card" id="card-${escapeHTML(group.persistent_id)}">
        ${mediaHTML}

        <div class="card-body">
          <div class="card-tags-row">
            ${offerTypeBadgeHTML}
            ${storeStatusBadgeHTML}
            ${channelBadgeHTML}
            ${superDiscountHTML}
            ${preservedBadgeHTML}
          </div>

          <h3 class="card-title">${escapeHTML(group.title)}</h3>
          ${descriptionHTML}

          <div class="pricing-block">
            <div class="price-main-row">
              <span class="price-value">${escapeHTML(displayPrice)}</span>
              ${originalPriceHTML}
            </div>
            ${unitPriceBadgeHTML}
          </div>

          <div class="card-meta">
            ${storeScopeHTML}
            <div class="meta-item">
              <span>${freshnessText}</span>
            </div>
          </div>
        </div>

        <footer class="card-footer">
          <div class="card-actions">
            <a href="${escapeHTML(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="btn-official">
              <span>Ver no site oficial</span>
              <span aria-hidden="true" class="btn-icon-external">↗</span>
            </a>
            <button type="button" class="btn-share-promo" title="Copiar hiperligação desta oferta" aria-label="Copiar hiperligação da oferta ${escapeHTML(group.title)}" data-url="${escapeHTML(sourceUrl)}">
              <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M8.5 11.5l3-3m-1-4l2.5-2.5a3.536 3.536 0 115 5L15.5 9.5m-5 1l-2.5 2.5a3.536 3.536 0 11-5-5L5.5 5.5"></path>
              </svg>
            </button>
          </div>
        </footer>
      </article>
    `;
  }

  // Atualizar Barra de Estado
  function updateStatusBar(count) {
    const isFiltered = state.filterProduct !== 'ALL' ||
                       state.filterVendor !== 'ALL' ||
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

  function resolveDirectPromoUrl(group) {
    if (!group) return '#';
    let url = group.source_url || '#';

    // Telepizza: navegar diretamente para a âncora do cartão/modal #offerDetails_{id}
    if (group.vendor === 'TELEPIZZA') {
      if (!url.includes('#offerDetails_') && Array.isArray(group.variants) && group.variants.length > 0) {
        const vId = group.variants[0].variant_id || '';
        const match = vId.match(/^tp_(.+?)_(delivery|takeaway)$/);
        const promoId = match ? match[1] : '';
        if (promoId) {
          return `https://www.telepizza.pt/promocoes#offerDetails_${encodeURIComponent(promoId)}`;
        }
      }
      return url.includes('promocoes') ? url : 'https://www.telepizza.pt/promocoes';
    }

    // Domino's: encaminhar diretamente para o carrossel de promoções #content-for-scroll
    if (group.vendor === 'DOMINOS') {
      if (url === 'https://www.dominospizza.pt/' || url === 'https://www.dominospizza.pt' || !url.includes('#')) {
        return 'https://www.dominospizza.pt/#content-for-scroll';
      }
      return url;
    }

    // Papa John's: mapear slugs oficiais conhecidas
    if (group.vendor === 'PAPA_JOHNS') {
      const lower = (group.title || '').toLowerCase();
      if (lower.includes('papa day') || lower.includes('papa às 3') || lower.includes('papa as 3')) {
        return 'https://www.papajohns.pt/promocoes/papa-as-3as/';
      }
      if (lower.includes('super john')) {
        return 'https://www.papajohns.pt/promocoes/super-john/';
      }
      if (lower.includes('trio bestial')) {
        return 'https://www.papajohns.pt/promocoes/trio-bestial/';
      }
      if (lower.includes('duo bestial')) {
        return 'https://www.papajohns.pt/promocoes/duo-bestial/';
      }
      if (lower.includes('papito')) {
        return 'https://www.papajohns.pt/promocoes/o-papito-menu-individual/';
      }
    }

    return url;
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

  // =========================================================================
  // Módulo de Lojas de Lisboa (33 Lojas Oficiais • Horários em Tempo Real)
  // =========================================================================

  // Converte data atual para data e hora oficial de Lisboa (UTC+0 / UTC+1 DST)
  function getLisbonNow() {
    const now = new Date();
    // Utiliza Intl para obter componentes no fuso horário Europe/Lisbon determinístico
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Europe/Lisbon',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      second: 'numeric',
      hour12: false,
    });
    const parts = formatter.formatToParts(now);
    const dateObj = {};
    for (const p of parts) {
      if (p.type !== 'literal') {
        dateObj[p.type] = parseInt(p.value, 10);
      }
    }
    // Determinar dia da semana em Lisboa
    const lisbonDate = new Date(Date.UTC(dateObj.year, dateObj.month - 1, dateObj.day, dateObj.hour, dateObj.minute, dateObj.second));
    const dayOfWeek = lisbonDate.getUTCDay(); // 0 = Domingo, 1 = Segunda, ..., 6 = Sábado
    const currentMinutes = dateObj.hour * 60 + dateObj.minute;

    return {
      now,
      hours: dateObj.hour,
      minutes: dateObj.minute,
      currentMinutes,
      dayOfWeek,
      formattedTime: `${String(dateObj.hour).padStart(2, '0')}:${String(dateObj.minute).padStart(2, '0')}`,
    };
  }

  function parseHHMMToMinutes(hhmm) {
    if (!hhmm) return 0;
    const [h, m] = hhmm.split(':').map((v) => parseInt(v, 10));
    return h * 60 + m;
  }

  // Calcula determinística do estado de uma loja (is_open, closing_soon, status_code, label)
  function getStoreStatus(store, lisbonTime) {
    if (!store || !store.schedule) {
      return {
        isOpen: false,
        closingSoon: false,
        statusCode: 'UNKNOWN',
        label: 'Horário sob consulta',
        closeTime: null,
      };
    }

    const { currentMinutes, dayOfWeek } = lisbonTime || getLisbonNow();
    const prevDay = (dayOfWeek + 6) % 7;
    const prevSched = store.schedule[String(prevDay)];

    // 1. Verificar se a loja ainda está aberta de turno que cruzou a meia-noite (ex.: 11:30 às 01:00)
    if (prevSched) {
      const prevOpenMin = parseHHMMToMinutes(prevSched.open);
      const prevCloseMin = parseHHMMToMinutes(prevSched.close);
      if (prevCloseMin < prevOpenMin) {
        if (currentMinutes < prevCloseMin) {
          const minsLeft = prevCloseMin - currentMinutes;
          const closingSoon = minsLeft <= 30;
          return {
            isOpen: true,
            closingSoon,
            statusCode: closingSoon ? 'CLOSING_SOON' : 'OPEN',
            closeTime: prevSched.close,
            label: closingSoon ? `Fecha em breve às ${prevSched.close}` : `Aberta agora • Fecha às ${prevSched.close}`,
          };
        }
      }
    }

    // 2. Verificar horário do dia de hoje
    const todaySched = store.schedule[String(dayOfWeek)];
    if (!todaySched) {
      return {
        isOpen: false,
        closingSoon: false,
        statusCode: 'CLOSED',
        label: 'Fechada hoje',
        closeTime: null,
      };
    }

    const todayOpenMin = parseHHMMToMinutes(todaySched.open);
    const todayCloseMin = parseHHMMToMinutes(todaySched.close);

    // Caso A: Fecho no próprio dia (ex.: 10:00 às 23:00)
    if (todayCloseMin >= todayOpenMin) {
      if (currentMinutes >= todayOpenMin && currentMinutes < todayCloseMin) {
        const minsLeft = todayCloseMin - currentMinutes;
        const closingSoon = minsLeft <= 30;
        return {
          isOpen: true,
          closingSoon,
          statusCode: closingSoon ? 'CLOSING_SOON' : 'OPEN',
          closeTime: todaySched.close,
          label: closingSoon ? `Fecha em breve às ${todaySched.close}` : `Aberta agora • Fecha às ${todaySched.close}`,
        };
      } else if (currentMinutes < todayOpenMin) {
        return {
          isOpen: false,
          closingSoon: false,
          statusCode: 'CLOSED',
          closeTime: null,
          label: `Fechada • Abre hoje às ${todaySched.open}`,
        };
      } else {
        const nextDay = (dayOfWeek + 1) % 7;
        const nextSched = store.schedule[String(nextDay)];
        const nextOpen = nextSched ? nextSched.open : '11:30';
        return {
          isOpen: false,
          closingSoon: false,
          statusCode: 'CLOSED',
          closeTime: null,
          label: `Fechada • Abre amanhã às ${nextOpen}`,
        };
      }
    }

    // Caso B: Fecho após a meia-noite (ex.: 11:30 às 00:30 ou 01:00)
    if (currentMinutes >= todayOpenMin) {
      const minsLeft = (1440 - currentMinutes) + todayCloseMin;
      const closingSoon = minsLeft <= 30;
      return {
        isOpen: true,
        closingSoon,
        statusCode: closingSoon ? 'CLOSING_SOON' : 'OPEN',
        closeTime: todaySched.close,
        label: closingSoon ? `Fecha em breve às ${todaySched.close}` : `Aberta agora • Fecha às ${todaySched.close}`,
      };
    } else {
      return {
        isOpen: false,
        closingSoon: false,
        statusCode: 'CLOSED',
        closeTime: null,
        label: `Fechada • Abre hoje às ${todaySched.open}`,
      };
    }
  }

  // Verifica se uma marca tem pelo menos 1 loja aberta agora em Lisboa
  function isBrandOpenNow(brand) {
    if (!state.stores || state.stores.length === 0) return true; // fallback neutro
    const lisbonTime = getLisbonNow();
    return state.stores.some((s) => s.brand === brand && getStoreStatus(s, lisbonTime).isOpen);
  }

  // Carregar dados de lojas de Lisboa
  async function loadStoresData() {
    try {
      const response = await fetch('data/stores.json');
      if (!response.ok) {
        throw new Error(`Falha HTTP ao carregar stores.json: ${response.status}`);
      }
      state.stores = await response.json();
      updateStoresHeaderCounts();
      applyStoresFiltersAndRender();
    } catch (err) {
      console.warn('Não foi possível carregar stores.json:', err);
      if (elements.storesGrid) {
        elements.storesGrid.innerHTML = `
          <div class="empty-state" role="alert" style="grid-column: 1 / -1;">
            <h3 class="empty-title">Horários Temporariamente Indisponíveis</h3>
            <p class="empty-message">Os horários das lojas estão a ser sincronizados. Tenta atualizar a página dentro de momentos.</p>
          </div>
        `;
      }
    }
  }

  // Atualizar contadores e relógio de Lisboa
  function updateStoresHeaderCounts() {
    const lisbonTime = getLisbonNow();
    let openCount = 0;
    const brandCounts = {
      ALL: state.stores.length,
      DOMINOS: 0,
      PAPA_JOHNS: 0,
      PIZZA_HUT: 0,
      TELEPIZZA: 0,
    };

    for (const store of state.stores) {
      if (brandCounts[store.brand] !== undefined) {
        brandCounts[store.brand]++;
      }
      const st = getStoreStatus(store, lisbonTime);
      if (st.isOpen) openCount++;
    }

    if (elements.headerStoresCount) {
      elements.headerStoresCount.textContent = `${openCount}/${state.stores.length} abertas`;
    }
    if (elements.countStoresOpenNow) {
      elements.countStoresOpenNow.textContent = String(openCount);
    }
    if (elements.countBrandAll) elements.countBrandAll.textContent = String(brandCounts.ALL);
    if (elements.countBrandDominos) elements.countBrandDominos.textContent = String(brandCounts.DOMINOS);
    if (elements.countBrandPapajohns) elements.countBrandPapajohns.textContent = String(brandCounts.PAPA_JOHNS);
    if (elements.countBrandPizzahut) elements.countBrandPizzahut.textContent = String(brandCounts.PIZZA_HUT);
    if (elements.countBrandTelepizza) elements.countBrandTelepizza.textContent = String(brandCounts.TELEPIZZA);

    if (elements.lisbonClockBadge) {
      elements.lisbonClockBadge.textContent = `🕒 Hora de Lisboa: ${lisbonTime.formattedTime}`;
    }
  }

  // Filtrar e Renderizar Lojas
  function applyStoresFiltersAndRender() {
    if (!state.stores || state.stores.length === 0) return;
    const lisbonTime = getLisbonNow();

    let filtered = [...state.stores];

    // 1. Filtro por Marca
    if (state.filterStoreBrand !== 'ALL') {
      filtered = filtered.filter((s) => s.brand === state.filterStoreBrand);
    }

    // 2. Filtro por Estado (Apenas Abertas)
    if (state.filterStoreStatus === 'OPEN') {
      filtered = filtered.filter((s) => getStoreStatus(s, lisbonTime).isOpen);
    }

    // 3. Filtro por Serviço (DELIVERY, TAKE_AWAY)
    if (state.filterStoreService !== 'ALL') {
      filtered = filtered.filter((s) => s.services && s.services.includes(state.filterStoreService));
    }

    // 4. Pesquisa por Texto (Bairro, Morada, Nome)
    if (state.storesSearchQuery) {
      const q = state.storesSearchQuery;
      filtered = filtered.filter((s) => {
        const nameMatch = (s.name || '').toLowerCase().includes(q);
        const neighMatch = (s.neighborhood || '').toLowerCase().includes(q);
        const addrMatch = (s.address || '').toLowerCase().includes(q);
        const brandMatch = (VENDOR_LABELS[s.brand] || '').toLowerCase().includes(q);
        return nameMatch || neighMatch || addrMatch || brandMatch;
      });
    }

    // Ordenar: primeiro abertas (OPEN / CLOSING_SOON), depois fechadas, desempate por marca e nome
    filtered.sort((a, b) => {
      const stA = getStoreStatus(a, lisbonTime);
      const stB = getStoreStatus(b, lisbonTime);
      if (stA.isOpen !== stB.isOpen) {
        return stA.isOpen ? -1 : 1;
      }
      if (a.brand !== b.brand) {
        return a.brand.localeCompare(b.brand);
      }
      return a.name.localeCompare(b.name);
    });

    renderStoresGrid(filtered, lisbonTime);
    updateStoresStatusBar(filtered.length);
  }

  // Renderizar Grelha de Lojas
  function renderStoresGrid(storesList, lisbonTime) {
    if (!elements.storesGrid) return;

    if (storesList.length === 0) {
      elements.storesGrid.style.display = 'none';
      if (elements.storesEmptyState) elements.storesEmptyState.style.display = 'flex';
      return;
    }

    elements.storesGrid.style.display = 'grid';
    if (elements.storesEmptyState) elements.storesEmptyState.style.display = 'none';

    elements.storesGrid.innerHTML = storesList.map((s) => buildStoreCardHTML(s, lisbonTime)).join('');
  }

  // Constrói HTML do Cartão de Loja
  function buildStoreCardHTML(store, lisbonTime) {
    const status = getStoreStatus(store, lisbonTime);
    const vendorLabel = VENDOR_LABELS[store.brand] || store.brand;

    let badgeClass = 'status-badge-closed';
    let dotClass = 'dot-closed';
    if (status.statusCode === 'OPEN') {
      badgeClass = 'status-badge-open';
      dotClass = 'dot-open';
    } else if (status.statusCode === 'CLOSING_SOON') {
      badgeClass = 'status-badge-closing-soon';
      dotClass = 'dot-closing-soon';
    }

    const servicesBadgesHTML = (store.services || []).map((srv) => {
      if (srv === 'DELIVERY') return '<span class="store-service-pill">🛵 Entrega</span>';
      if (srv === 'TAKE_AWAY') return '<span class="store-service-pill">🥡 Take Away</span>';
      if (srv === 'DINE_IN') return '<span class="store-service-pill">🍽️ Sala</span>';
      return `<span class="store-service-pill">${escapeHTML(srv)}</span>`;
    }).join(' ');

    const phoneHTML = store.phone
      ? `<a href="tel:${escapeHTML(store.phone.replace(/\s+/g, ''))}" class="store-phone-link" title="Ligar para ${escapeHTML(store.name)}">
           <svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 4a1 1 0 011-1h3a1 1 0 011 1v2a1 1 0 01-1 1H6a11 11 0 005 5v-1a1 1 0 011-1h2a1 1 0 011 1v3a1 1 0 01-1 1h-1C7.82 17 3 12.18 3 7V4z"></path></svg>
           <span>${escapeHTML(store.phone)}</span>
         </a>`
      : '';

    return `
      <article class="store-card store-card-${escapeHTML(store.brand.toLowerCase())}" id="store-${escapeHTML(store.id)}">
        <header class="store-card-header">
          <div class="store-brand-badge store-brand-${escapeHTML(store.brand)}">
            ${escapeHTML(vendorLabel)}
          </div>
          <div class="store-status-badge ${badgeClass}">
            <span class="status-dot-small ${dotClass}" aria-hidden="true"></span>
            <span>${escapeHTML(status.label)}</span>
          </div>
        </header>

        <div class="store-card-body">
          <h3 class="store-name">${escapeHTML(store.name)}</h3>
          <div class="store-neighborhood">📍 ${escapeHTML(store.neighborhood)}</div>
          <p class="store-address">${escapeHTML(store.address)}</p>

          <div class="store-services-row">
            ${servicesBadgesHTML}
          </div>
        </div>

        <footer class="store-card-footer">
          ${phoneHTML}
          <a href="${escapeHTML(store.official_url)}" target="_blank" rel="noopener noreferrer" class="btn-store-order">
            <span>Pedir Online</span>
            <span aria-hidden="true">↗</span>
          </a>
        </footer>
      </article>
    `;
  }

  function updateStoresStatusBar(count) {
    if (!elements.storesResultsCount) return;
    if (count === 1) {
      elements.storesResultsCount.textContent = '1 loja encontrada em Lisboa';
    } else {
      elements.storesResultsCount.textContent = `${count} lojas encontradas em Lisboa`;
    }
  }

  // Ouvintes de Eventos para a Secção de Lojas e Alternância Mobile
  function setupStoresEventListeners() {
    // 1. Mobile Nav Switcher (Abas de topo em telemóvel)
    if (elements.btnViewPromos && elements.btnViewStores) {
      elements.btnViewPromos.addEventListener('click', () => switchMobileView('promos'));
      elements.btnViewStores.addEventListener('click', () => switchMobileView('stores'));
    }

    if (elements.navLinkPromos) {
      elements.navLinkPromos.addEventListener('click', (e) => {
        if (window.innerWidth <= 640) {
          e.preventDefault();
          switchMobileView('promos');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });
    }

    if (elements.navLinkStores) {
      elements.navLinkStores.addEventListener('click', (e) => {
        if (window.innerWidth <= 640) {
          e.preventDefault();
          switchMobileView('stores');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });
    }

    // 2. Chips de Marca de Loja
    elements.storeBrandChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.storeBrandChips.forEach((c) => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        state.filterStoreBrand = chip.dataset.storeBrand;
        applyStoresFiltersAndRender();
      });
    });

    // 3. Chips de Estado (Todas vs Apenas Abertas)
    elements.storeStatusChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.storeStatusChips.forEach((c) => {
          c.classList.remove('active');
        });
        chip.classList.add('active');
        state.filterStoreStatus = chip.dataset.storeStatus;
        applyStoresFiltersAndRender();
      });
    });

    // 4. Chips de Serviço (Todos, Entrega, Take Away)
    elements.storeServiceChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.storeServiceChips.forEach((c) => {
          c.classList.remove('active');
        });
        chip.classList.add('active');
        state.filterStoreService = chip.dataset.storeService;
        applyStoresFiltersAndRender();
      });
    });

    // 5. Pesquisa de Lojas
    if (elements.storesSearchInput) {
      let storeDebounceTimeout = null;
      elements.storesSearchInput.addEventListener('input', (e) => {
        const val = e.target.value;
        if (elements.btnClearStoresSearch) {
          elements.btnClearStoresSearch.style.display = val.length > 0 ? 'flex' : 'none';
        }
        clearTimeout(storeDebounceTimeout);
        storeDebounceTimeout = setTimeout(() => {
          state.storesSearchQuery = val.trim().toLowerCase();
          applyStoresFiltersAndRender();
        }, 150);
      });
    }

    if (elements.btnClearStoresSearch) {
      elements.btnClearStoresSearch.addEventListener('click', () => {
        if (elements.storesSearchInput) {
          elements.storesSearchInput.value = '';
          elements.storesSearchInput.focus();
        }
        state.storesSearchQuery = '';
        elements.btnClearStoresSearch.style.display = 'none';
        applyStoresFiltersAndRender();
      });
    }

    if (elements.btnClearStoresEmpty) {
      elements.btnClearStoresEmpty.addEventListener('click', () => {
        state.filterStoreBrand = 'ALL';
        state.filterStoreStatus = 'ALL';
        state.filterStoreService = 'ALL';
        state.storesSearchQuery = '';
        elements.storeBrandChips.forEach((c) => c.classList.toggle('active', c.dataset.storeBrand === 'ALL'));
        elements.storeStatusChips.forEach((c) => c.classList.toggle('active', c.dataset.storeStatus === 'ALL'));
        elements.storeServiceChips.forEach((c) => c.classList.toggle('active', c.dataset.storeService === 'ALL'));
        if (elements.storesSearchInput) elements.storesSearchInput.value = '';
        if (elements.btnClearStoresSearch) elements.btnClearStoresSearch.style.display = 'none';
        applyStoresFiltersAndRender();
      });
    }
  }

  // Alternar vista no telemóvel
  function switchMobileView(view) {
    state.currentMobileView = view;
    if (view === 'promos') {
      if (elements.btnViewPromos) {
        elements.btnViewPromos.classList.add('active');
        elements.btnViewPromos.setAttribute('aria-selected', 'true');
      }
      if (elements.btnViewStores) {
        elements.btnViewStores.classList.remove('active');
        elements.btnViewStores.setAttribute('aria-selected', 'false');
      }
      if (elements.radarSection) elements.radarSection.classList.remove('mobile-view-hidden');
      if (elements.storesSection) elements.storesSection.classList.add('mobile-view-hidden');
    } else {
      if (elements.btnViewStores) {
        elements.btnViewStores.classList.add('active');
        elements.btnViewStores.setAttribute('aria-selected', 'true');
      }
      if (elements.btnViewPromos) {
        elements.btnViewPromos.classList.remove('active');
        elements.btnViewPromos.setAttribute('aria-selected', 'false');
      }
      if (elements.radarSection) elements.radarSection.classList.add('mobile-view-hidden');
      if (elements.storesSection) elements.storesSection.classList.remove('mobile-view-hidden');
    }
  }

  // Relógio em tempo real com atualização a cada 60 segundos
  function startLiveClock() {
    setInterval(() => {
      updateStoresHeaderCounts();
      applyStoresFiltersAndRender();
      // Se o filtro de marcas abertas estiver ativo nas promoções, re-renderiza promoções também
      if (state.filterOnlyOpenBrands) {
        applyFiltersAndRender();
      }
    }, 60000);
  }

  // Arranque
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

// Feedback Dashboard JavaScript - Optimized for Performance

// Professional Chart Color Palettes with high contrast and accessibility
const CHART_CONFIG = {
  priorityColors: {
    'CRITICAL': '#DC2626', // Red
    'HIGH': '#EA580C',     // Orange
    'MEDIUM': '#D97706',   // Amber
    'LOW': '#059669'       // Green
  },
  
  statusColors: {
    'NEW': '#3B82F6',      // Blue
    'IN_PROGRESS': '#EAB308', // Yellow
    'FINISHED': '#10B981', // Emerald
    'CLOSED': '#6B7280'    // Gray
  },
  
  // Professional color palette for reporters (distinct, accessible colors)
  reporterColors: [
    '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
    '#06B6D4', '#F97316', '#84CC16', '#EC4899', '#6366F1'
  ],
  
  // Chart options with professional styling
  chartOptions: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'bottom',
        labels: {
          padding: 20,
          font: {
            size: 13,
            weight: '600',
            family: 'Inter, system-ui, sans-serif'
          },
          usePointStyle: true,
          pointStyle: 'circle',
          boxWidth: 12,
          boxHeight: 12
        }
      },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        titleColor: '#fff',
        bodyColor: '#fff',
        padding: 16,
        borderColor: '#e2e8f0',
        borderWidth: 1,
        displayColors: true,
        cornerRadius: 8,
        titleFont: {
          size: 14,
          weight: '600'
        },
        bodyFont: {
          size: 13
        },
        callbacks: {
          label: function(context) {
            const label = context.label || '';
            const value = context.parsed || 0;
            const total = context.dataset.data.reduce((a, b) => a + b, 0);
            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
            return `${label}: ${value} (${percentage}%)`;
          }
        }
      }
    },
    elements: {
      arc: {
        borderWidth: 2,
        borderColor: '#ffffff',
        hoverBorderWidth: 3
      }
    }
  }
};

// Chart instances for cleanup
let chartInstances = {};

// Current filter state
let currentFilters = {
  status: '',
  type: '',
  priority: '',
  sort: 'id',
  order: 'desc'
};

// Debounced search function
let searchTimeout;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
  initializeCharts();
  initializeSearch();
  initializeFilters();
});

// Helper function to safely initialize chart
function initializeChart(canvasId, chartType, data, colorMap) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.error(`Canvas element ${canvasId} not found`);
    return null;
  }

  if (!data.labels || !data.values || data.labels.length === 0) {
    console.warn(`No data available for ${canvasId}`);
    // Show empty state
    const ctx = canvas.getContext('2d');
    ctx.font = '14px Arial';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';
    ctx.fillText('No data available', canvas.width / 2, canvas.height / 2);
    return null;
  }

  try {
    // Destroy existing chart if it exists
    if (chartInstances[canvasId]) {
      chartInstances[canvasId].destroy();
    }

    const ctx = canvas.getContext('2d');
    const chart = new Chart(ctx, {
      type: chartType,
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: Array.isArray(colorMap)
            ? colorMap.slice(0, data.labels.length)
            : data.labels.map(label => {
                return colorMap[label] || colorMap[label.toUpperCase()] || '#94A3B8';
              }),
          borderWidth: 2,
          borderColor: '#ffffff',
          hoverBorderWidth: 3,
          hoverBorderColor: '#ffffff',
          hoverBackgroundColor: Array.isArray(colorMap)
            ? colorMap.slice(0, data.labels.length).map(color => color + 'E6')
            : data.labels.map(label => (colorMap[label] || colorMap[label.toUpperCase()] || '#94A3B8') + 'E6')
        }]
      },
      options: CHART_CONFIG.chartOptions
    });

    chartInstances[canvasId] = chart;
    return chart;
  } catch (error) {
    console.error(`Error initializing chart ${canvasId}:`, error);
    return null;
  }
}

// Initialize charts with error handling
function initializeCharts() {
  // Get chart data from template
  let rawChartData;
  try {
    rawChartData = window.chartData || {
      priority: {labels: [], values: []},
      status: {labels: [], values: []},
      reporter: {labels: [], values: []}
    };
  } catch (e) {
    console.error('Error parsing chart data:', e);
    rawChartData = {
      priority: {labels: [], values: []},
      status: {labels: [], values: []},
      reporter: {labels: [], values: []}
    };
  }

  // Validate and sanitize chart data
  const chartData = {
    priority: {
      labels: Array.isArray(rawChartData.priority?.labels) ? rawChartData.priority.labels : [],
      values: Array.isArray(rawChartData.priority?.values) ? rawChartData.priority.values.map(v => Number(v) || 0) : []
    },
    status: {
      labels: Array.isArray(rawChartData.status?.labels) ? rawChartData.status.labels : [],
      values: Array.isArray(rawChartData.status?.values) ? rawChartData.status.values.map(v => Number(v) || 0) : []
    },
    reporter: {
      labels: Array.isArray(rawChartData.reporter?.labels) ? rawChartData.reporter.labels : [],
      values: Array.isArray(rawChartData.reporter?.values) ? rawChartData.reporter.values.map(v => Number(v) || 0) : []
    }
  };

  console.log('Initializing charts with data:', chartData);
  
  initializeChart('priorityChart', 'pie', chartData.priority, CHART_CONFIG.priorityColors);
  initializeChart('statusChart', 'pie', chartData.status, CHART_CONFIG.statusColors);
  initializeChart('reporterChart', 'pie', chartData.reporter, CHART_CONFIG.reporterColors);
}

// Initialize search functionality
function initializeSearch() {
  const searchInput = document.getElementById('globalSearch');
  const searchResults = document.getElementById('searchResults');
  
  if (!searchInput || !searchResults) return;

  searchInput.addEventListener('input', function() {
    const query = this.value.trim();

    clearTimeout(searchTimeout);

    if (query.length < 3) {
      searchResults.classList.remove('show');
      searchResults.innerHTML = '';
      return;
    }

    searchTimeout = setTimeout(() => {
      fetch(`/projects/search_feedback/?q=${encodeURIComponent(query)}`)
        .then(response => {
          if (!response.ok) {
            throw new Error('Network response was not ok');
          }
          return response.json();
        })
        .then(data => {
          displaySearchResults(data.results || []);
        })
        .catch(error => {
          console.error('Search error:', error);
          searchResults.innerHTML = '<div class="search-no-results">Search failed. Please try again.</div>';
          searchResults.classList.add('show');
        });
    }, 300);
  });

  // Close search results when clicking outside
  document.addEventListener('click', function(event) {
    if (!searchInput.contains(event.target) && !searchResults.contains(event.target)) {
      searchResults.classList.remove('show');
    }
  });
}

// Display search results
function displaySearchResults(results) {
  const searchResults = document.getElementById('searchResults');
  if (!searchResults) return;

  if (results.length === 0) {
    searchResults.innerHTML = '<div class="search-no-results">No results found</div>';
    searchResults.classList.add('show');
    return;
  }

  let html = '';
  results.forEach(result => {
    html += `
      <div class="search-result-item" onclick="window.location.href='/projects/feedback/${result.id}/'">
        <span class="search-result-id">${result.issue_id || ''}</span>
        <span class="search-result-summary">${result.summary || 'No summary'}</span>
      </div>
    `;
  });

  searchResults.innerHTML = html;
  searchResults.classList.add('show');
}

// Initialize filters
function initializeFilters() {
  // Get initial filter values from template
  currentFilters.status = document.getElementById('statusFilter')?.value || '';
  currentFilters.type = document.getElementById('typeFilter')?.value || '';
  currentFilters.priority = document.getElementById('priorityFilter')?.value || '';
}

// Load table data with optimized AJAX
function loadTableData(page = 1) {
  const params = new URLSearchParams();
  if (currentFilters.status) params.set('status', currentFilters.status);
  if (currentFilters.type) params.set('type', currentFilters.type);
  if (currentFilters.priority) params.set('priority', currentFilters.priority);
  if (currentFilters.sort) params.set('sort', currentFilters.sort);
  if (currentFilters.order) params.set('order', currentFilters.order);
  if (page > 1) params.set('page', page);

  // Add loading animation
  const tbody = document.getElementById('issuesTableBody');
  if (tbody) {
    tbody.classList.add('loading');
  }

  fetch(`/projects/feedback_table_ajax/?${params.toString()}`)
    .then(response => {
      if (!response.ok) {
        throw new Error('Network response was not ok');
      }
      return response.json();
    })
    .then(data => {
      if (tbody) {
        tbody.innerHTML = data.table_html;
      }
      
      const paginationContainer = document.querySelector('.pagination-container');
      if (paginationContainer) {
        paginationContainer.innerHTML = data.pagination_html;
      }
      
      // Update URL without reload
      const newUrl = new URL(window.location);
      newUrl.search = params.toString();
      window.history.pushState({}, '', newUrl);
    })
    .catch(error => {
      console.error('Error loading table data:', error);
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #dc2626;">Error loading data. Please refresh the page.</td></tr>';
      }
    })
    .finally(() => {
      if (tbody) {
        tbody.classList.remove('loading');
      }
    });
}

// Apply filters
function applyFilters() {
  currentFilters.status = document.getElementById('statusFilter')?.value || '';
  currentFilters.type = document.getElementById('typeFilter')?.value || '';
  currentFilters.priority = document.getElementById('priorityFilter')?.value || '';
  loadTableData(1);
}

// Sort table
function sortTable(column) {
  // Remove previous sorting class
  document.querySelectorAll('.issues-table th').forEach(th => th.classList.remove('sorting'));
  
  // Add sorting class to clicked header
  if (event && event.target) {
    const th = event.target.closest('th');
    if (th) {
      th.classList.add('sorting');
    }
  }
  
  if (currentFilters.sort === column) {
    currentFilters.order = currentFilters.order === 'asc' ? 'desc' : 'asc';
  } else {
    currentFilters.sort = column;
    currentFilters.order = 'asc';
  }
  
  loadTableData(1);
  
  // Remove sorting class after animation
  setTimeout(() => {
    document.querySelectorAll('.issues-table th').forEach(th => th.classList.remove('sorting'));
  }, 600);
}

// Cleanup function for page unload
window.addEventListener('beforeunload', function() {
  // Destroy all chart instances to prevent memory leaks
  Object.values(chartInstances).forEach(chart => {
    if (chart && typeof chart.destroy === 'function') {
      chart.destroy();
    }
  });
  chartInstances = {};
});
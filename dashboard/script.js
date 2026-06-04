document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const sidebar = document.getElementById('sidebar');
  const openSidebarBtn = document.getElementById('open-sidebar');
  const closeSidebarBtn = document.getElementById('close-sidebar');
  const mainContent = document.querySelector('.main-content');
  const reportsList = document.getElementById('reports-list');
  const reportCount = document.getElementById('report-count');
  const toastContainer = document.getElementById('toast-container');
  const logoutBtn = document.getElementById('logout-btn');
  const logoutModal = document.getElementById('logout-modal');
  const cancelLogoutBtn = document.getElementById('cancel-logout');
  const confirmLogoutBtn = document.getElementById('confirm-logout');
  const fullscreenLoader = document.getElementById('fullscreen-loader');

  // Navigation Logic
  const navItems = document.querySelectorAll('[data-view]');
  const viewSections = document.querySelectorAll('.view-section');
  const pageTitle = document.querySelector('.header-left h1');

  const titles = {
    'reports': 'Received Reports',
    'database': 'Database Management',
    'settings': 'System Settings'
  };

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const viewId = item.getAttribute('data-view');
      
      // Update active nav items
      navItems.forEach(nav => {
        if (nav.getAttribute('data-view') === viewId) {
          nav.classList.add('active');
        } else {
          nav.classList.remove('active');
        }
      });

      // Update header title
      if (titles[viewId] && pageTitle) {
        pageTitle.textContent = titles[viewId];
      }

      // Update views
      viewSections.forEach(section => {
        if (section.id === `view-${viewId}`) {
          section.style.display = 'block';
        } else {
          section.style.display = 'none';
        }
      });
      
      // On mobile, close sidebar after navigation
      if (window.innerWidth < 768 && !sidebar.classList.contains('closed')) {
        sidebar.classList.add('closed');
      }
    });
  });

  // Logout Logic
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      logoutModal.style.display = 'flex'; // show modal
    });
  }

  if (cancelLogoutBtn) {
    cancelLogoutBtn.addEventListener('click', () => {
      logoutModal.style.display = 'none'; // hide modal
    });
  }

  if (confirmLogoutBtn) {
    confirmLogoutBtn.addEventListener('click', () => {
      logoutModal.style.display = 'none'; // hide modal
      fullscreenLoader.style.display = 'flex'; // show fullscreen loader

      // Simulate logout process
      setTimeout(() => {
        // Redirect to login page or reload (for now, we'll just reload the page as a placeholder)
        window.location.reload();
      }, 2000);
    });
  }

  // Sidebar Toggle Logic
  const toggleSidebar = () => {
    sidebar.classList.toggle('closed');
    // On desktop, we want to adjust the main content margin
    if (window.innerWidth >= 768) {
      mainContent.classList.toggle('full-width');
    }
  };

  openSidebarBtn.addEventListener('click', toggleSidebar);
  closeSidebarBtn.addEventListener('click', toggleSidebar);

  // Handle window resize to reset sidebar state correctly
  window.addEventListener('resize', () => {
    if (window.innerWidth >= 768) {
      sidebar.classList.remove('closed');
      mainContent.classList.remove('full-width');
    } else {
      sidebar.classList.add('closed');
    }
  });

  // Mock Data for Reports
  let reports = [
    {
      id: 'rep_123',
      company: 'cFDYdGDC',
      url: 'https://www.google.com/search?q=mindfiti&oq=mindf',
      reason: 'htyrhuIGFElidh.fcfqufuEFKLJDIH',
      date: '2 hours ago',
      status: 'pending'
    },
    {
      id: 'rep_124',
      company: 'Global Tech Recruiting',
      url: 'https://linkedin.com/jobs/view/fake-job',
      reason: 'They asked me to pay $50 for a background check before scheduling an interview.',
      date: '5 hours ago',
      status: 'pending'
    },
    {
      id: 'rep_125',
      company: 'DataEntry Pro Ltd',
      url: 'https://glassdoor.com/job-listing/12345',
      reason: 'The email address is a gmail account and the person refused to do a video call.',
      date: '1 day ago',
      status: 'pending'
    }
  ];

  // Render Reports
  const renderReports = () => {
    const pendingReports = reports.filter(r => r.status === 'pending');
    reportCount.textContent = pendingReports.length;

    if (pendingReports.length === 0) {
      reportsList.innerHTML = `
        <div class="empty-state">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin: 0 auto 1rem; opacity: 0.5;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
          <h3>All caught up!</h3>
          <p>There are no pending reports to review.</p>
        </div>
      `;
      return;
    }

    reportsList.innerHTML = pendingReports.map(report => `
      <div class="report-card" id="card-${report.id}">
        <div class="report-header">
          <div>
            <h3 class="company-name">${escapeHTML(report.company)}</h3>
            <a href="${escapeHTML(report.url)}" target="_blank" rel="noopener noreferrer" class="job-link">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
              View Job Link
            </a>
          </div>
          <span class="report-date">${report.date}</span>
        </div>
        
        <div>
          <h4 style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem;">Report Reason</h4>
          <div class="report-reason">
            ${escapeHTML(report.reason)}
          </div>
        </div>

        <div class="report-actions">
          <button class="btn btn-secondary" onclick="dismissReport('${report.id}')">Dismiss</button>
          <button class="btn btn-primary" onclick="sendToDatabase('${report.id}')">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>
            Send to Database
          </button>
        </div>
      </div>
    `).join('');
  };

  // Utility to prevent XSS
  const escapeHTML = (str) => {
    return str.replace(/[&<>'"]/g, 
      tag => ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          "'": '&#39;',
          '"': '&quot;'
        }[tag])
    );
  };

  // Action Handlers
  window.sendToDatabase = (id) => {
    const btn = document.querySelector(`#card-${id} .btn-primary`);
    btn.innerHTML = `<div class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></div> Sending...`;
    btn.disabled = true;

    // Simulate API call
    setTimeout(() => {
      reports = reports.map(r => r.id === id ? { ...r, status: 'approved' } : r);
      animateCardRemoval(id, () => {
        renderReports();
        showToast('Report successfully sent to database!');
      });
    }, 800);
  };

  window.dismissReport = (id) => {
    reports = reports.map(r => r.id === id ? { ...r, status: 'dismissed' } : r);
    animateCardRemoval(id, () => {
      renderReports();
      showToast('Report dismissed.', '#64748b'); // Gray toast for dismiss
    });
  };

  // UI Helpers
  const animateCardRemoval = (id, callback) => {
    const card = document.getElementById(`card-${id}`);
    if (card) {
      card.style.transform = 'scale(0.95)';
      card.style.opacity = '0';
      setTimeout(callback, 200); // Matches var(--transition-fast)
    } else {
      callback();
    }
  };

  const showToast = (message, bgColor = '') => {
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (bgColor) toast.style.backgroundColor = bgColor;
    
    toast.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
      ${message}
    `;
    
    toastContainer.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => {
      toast.classList.add('show');
    });

    // Remove after 3s
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300); // Wait for transition
    }, 3000);
  };

  // Initial setup: clear loading and render
  setTimeout(() => {
    // Initial responsive check
    if (window.innerWidth < 768) {
      sidebar.classList.add('closed');
    } else {
      sidebar.classList.remove('closed');
    }
    
    renderReports();
  }, 500); // Small delay to simulate initial fetch
});

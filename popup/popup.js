import { initNavigation } from '../scripts/navigation.js';

// Define the routes available in the SPA
const routes = {
  analysis: {
    template: '../pages/analysis/index.html',
    init: () => {
      const btn = document.getElementById('rescan-btn');
      if (btn) {
        btn.addEventListener('click', () => {
          const textSpan = btn.querySelector('.btn-text');
          const spinner = btn.querySelector('.spinner');
          const originalText = textSpan.textContent;
          
          textSpan.textContent = 'Scanning...';
          spinner.classList.remove('hidden');
          btn.disabled = true;
          btn.classList.add('opacity-75', 'cursor-not-allowed');

          // Simulate scanning delay
          setTimeout(() => {
            textSpan.textContent = originalText;
            spinner.classList.add('hidden');
            btn.disabled = false;
            btn.classList.remove('opacity-75', 'cursor-not-allowed');
          }, 1500);
        });
      }
    }
  },
  learn: {
    template: '../pages/learn/index.html',
    init: () => {
      console.log('Learn page loaded');
    }
  },
  report: {
    template: '../pages/report/index.html',
    init: () => {
      const btn = document.getElementById('submit-report-btn');
      if (btn) {
        btn.addEventListener('click', () => {
          const textSpan = btn.querySelector('.btn-text');
          const spinner = btn.querySelector('.spinner');
          const originalText = textSpan.textContent;
          
          textSpan.textContent = 'Submitting...';
          spinner.classList.remove('hidden');
          btn.disabled = true;
          btn.classList.add('opacity-75', 'cursor-not-allowed');

          // Simulate submitting delay
          setTimeout(() => {
            textSpan.textContent = 'Submitted!';
            spinner.classList.add('hidden');
            
            setTimeout(() => {
              textSpan.textContent = originalText;
              btn.disabled = false;
              btn.classList.remove('opacity-75', 'cursor-not-allowed');
            }, 2000);
          }, 1500);
        });
      }
    }
  },
  settings: {
    template: '../pages/settings/index.html',
    init: () => {
      console.log('Settings page loaded');
    }
  },
  privacy: {
    template: '../pages/privacy/index.html',
    init: () => {
      console.log('Privacy page loaded');
    }
  },
  terms: {
    template: '../pages/terms/index.html',
    init: () => {
      console.log('Terms page loaded');
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize navigation with 'analysis' as the default route
  const nav = initNavigation(routes, 'analysis');
});

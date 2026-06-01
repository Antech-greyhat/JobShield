import { initNavigation } from '../scripts/navigation.js';

// Define the routes available in the SPA
const routes = {
  analysis: {
    template: '../pages/analysis/index.html',
    init: () => {
      // Securely capture current website
      if (typeof chrome !== 'undefined' && chrome.tabs) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs && tabs.length > 0 && tabs[0].url) {
            try {
              const url = new URL(tabs[0].url);
              const websiteEl = document.getElementById('current-website');
              if (websiteEl) {
                // Keep the SVG icon but update the text node
                websiteEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                  ${url.hostname}`;
              }
            } catch (e) {
              console.error("Invalid URL");
            }
          }
        });
      }

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
      // Securely pre-fill current URL
      if (typeof chrome !== 'undefined' && chrome.tabs) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs && tabs.length > 0 && tabs[0].url) {
            const urlInput = document.getElementById('report-url');
            if (urlInput && !tabs[0].url.startsWith('chrome://')) {
              urlInput.value = tabs[0].url;
            }
          }
        });
      }

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

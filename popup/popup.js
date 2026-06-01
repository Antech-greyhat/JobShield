import { initNavigation } from '../scripts/navigation.js';
import { analyzeJobText } from '../scripts/scanner.js';

// Global dark mode apply
const applyTheme = (isDark) => {
  if (isDark) {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
};

if (typeof chrome !== 'undefined' && chrome.storage) {
  chrome.storage.local.get(['settings'], (result) => {
    const settings = result.settings || { darkMode: false };
    applyTheme(settings.darkMode);
  });
}

// Define the routes available in the SPA
const routes = {
  analysis: {
    template: '../pages/analysis/index.html',
    init: () => {
      let currentTab = null;
      // Securely capture current website
      if (typeof chrome !== 'undefined' && chrome.tabs) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs && tabs.length > 0 && tabs[0].url) {
            currentTab = tabs[0];
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

      const performScan = async () => {
        if (!currentTab || currentTab.url.startsWith('chrome://')) {
           document.getElementById('score-message').textContent = "Cannot scan this page.";
           document.getElementById('flags-container').innerHTML = '<p class="text-xs text-text-muted text-center py-4">No flags detected.</p>';
           return;
        }

        try {
          const response = await fetch('../data/scamkeywords.json');
          const data = await response.json();
          const scamKeywords = data.keywords || [];

          chrome.scripting.executeScript({
            target: { tabId: currentTab.id },
            func: () => document.body.innerText
          }, (results) => {
            if (results && results[0] && results[0].result) {
              const pageText = results[0].result;
              const analysis = analyzeJobText(pageText, scamKeywords, []);
              
              const scoreText = document.getElementById('score-text');
              const scoreBar = document.getElementById('score-bar');
              const scoreMsg = document.getElementById('score-message');
              const badge = document.getElementById('status-badge');
              const flagsContainer = document.getElementById('flags-container');

              scoreText.textContent = `${analysis.score}/100`;
              scoreBar.style.width = `${analysis.score}%`;
              
              scoreText.className = 'text-2xl font-bold';
              scoreBar.className = 'h-2.5 rounded-full transition-all duration-500';
              badge.className = 'px-2 py-1 rounded text-xs font-semibold';

              if (analysis.status === 'safe') {
                scoreText.classList.add('text-success');
                scoreBar.classList.add('bg-success');
                scoreMsg.textContent = "This job post appears to be legitimate based on our checks.";
                badge.classList.add('bg-green-100', 'text-green-700');
                badge.textContent = 'Safe';
              } else if (analysis.status === 'unknown') {
                scoreText.textContent = '--/100';
                scoreText.classList.add('text-gray-500');
                scoreBar.classList.add('bg-gray-500');
                scoreMsg.textContent = "This page doesn't look like a job posting.";
                badge.classList.add('bg-gray-200', 'text-gray-800');
                badge.textContent = 'N/A';
              } else if (analysis.status === 'warning') {
                scoreText.classList.add('text-warning');
                scoreBar.classList.add('bg-warning');
                scoreMsg.textContent = "Proceed with caution. Some suspicious flags detected.";
                badge.classList.add('bg-yellow-100', 'text-yellow-700');
                badge.textContent = 'Caution';
              } else {
                scoreText.classList.add('text-danger');
                scoreBar.classList.add('bg-danger');
                scoreMsg.textContent = "High risk! Multiple scam indicators detected.";
                badge.classList.add('bg-red-100', 'text-red-700');
                badge.textContent = 'High Risk';
              }

              if (analysis.flags.length === 0) {
                 flagsContainer.innerHTML = '<p class="text-xs text-text-muted text-center py-4">No suspicious flags detected.</p>';
              } else {
                 flagsContainer.innerHTML = analysis.flags.map(flag => {
                   let borderClass = flag.type === 'danger' ? 'border-danger bg-red-50' : 'border-warning bg-yellow-50';
                   let textClass = flag.type === 'danger' ? 'text-red-800' : 'text-yellow-800';
                   let descClass = flag.type === 'danger' ? 'text-red-700' : 'text-yellow-700';

                   return `<div class="p-3 border-l-4 ${borderClass} rounded-r-lg">
                      <h4 class="text-sm font-semibold ${textClass}">${flag.message}</h4>
                      <p class="text-xs ${descClass} mt-1">${flag.description}</p>
                    </div>`;
                 }).join('');
              }
            } else {
               document.getElementById('score-message').textContent = "Failed to extract page text.";
            }
          });
        } catch (e) {
          console.error("Scan error", e);
          document.getElementById('score-message').textContent = "Error running scan.";
        }
      };

      setTimeout(performScan, 300);

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

          performScan().then(() => {
            setTimeout(() => {
              textSpan.textContent = originalText;
              spinner.classList.add('hidden');
              btn.disabled = false;
              btn.classList.remove('opacity-75', 'cursor-not-allowed');
            }, 500);
          });
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
      const autoScanToggle = document.getElementById('autoscan-toggle');
      const darkModeToggle = document.getElementById('dark-mode-toggle');
      const notificationsToggle = document.getElementById('notifications-toggle');
      const clearHistoryBtn = document.getElementById('clear-history-btn');
      const clearHistoryMsg = document.getElementById('clear-history-msg');

      if (typeof chrome !== 'undefined' && chrome.storage) {
        chrome.storage.local.get(['settings'], (result) => {
          const settings = result.settings || { 
            autoScan: true, 
            darkMode: false,
            notifications: true
          };
          
          if (autoScanToggle) autoScanToggle.checked = settings.autoScan !== false;
          if (darkModeToggle) darkModeToggle.checked = settings.darkMode === true;
          if (notificationsToggle) notificationsToggle.checked = settings.notifications !== false;
        });
      }

      const saveSettings = () => {
        if (typeof chrome !== 'undefined' && chrome.storage) {
          const newSettings = {
            autoScan: autoScanToggle ? autoScanToggle.checked : true,
            darkMode: darkModeToggle ? darkModeToggle.checked : false,
            notifications: notificationsToggle ? notificationsToggle.checked : true
          };
          chrome.storage.local.set({ settings: newSettings });
          applyTheme(newSettings.darkMode);
        }
      };

      if (autoScanToggle) autoScanToggle.addEventListener('change', saveSettings);
      if (darkModeToggle) darkModeToggle.addEventListener('change', saveSettings);
      if (notificationsToggle) notificationsToggle.addEventListener('change', saveSettings);

      if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', () => {
          if (typeof chrome !== 'undefined' && chrome.storage) {
            chrome.storage.local.remove(['scanHistory'], () => {
              clearHistoryMsg.classList.remove('hidden');
              setTimeout(() => {
                clearHistoryMsg.classList.add('hidden');
              }, 3000);
            });
          }
        });
      }
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

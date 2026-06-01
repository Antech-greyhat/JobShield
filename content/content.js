// Content script to interact with job boards
(async () => {
  // Utility to inject UI into the page
  const injectShieldUI = (score, status) => {
    // Check if already injected
    if (document.getElementById('jobshield-badge')) return;

    const badge = document.createElement('div');
    badge.id = 'jobshield-badge';
    
    // Styling based on status
    let bg = '#10b981'; // success
    let text = 'Safe';
    if (status === 'warning') {
      bg = '#f59e0b';
      text = 'Caution';
    } else if (status === 'danger') {
      bg = '#ef4444';
      text = 'High Risk';
    }

    badge.innerHTML = `
      <div style="background-color: ${bg};" class="jobshield-container">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
        <span>JobShield: ${text} (${score}/100)</span>
      </div>
    `;

    // Try to find a good place to inject (this varies heavily by site)
    // For now, we just append to body with fixed positioning via CSS
    document.body.appendChild(badge);
  };

  // Extract job text
  const extractText = () => {
    // Basic extraction, grab body text.
    // In production, this would use site-specific selectors
    return document.body.innerText;
  };

  // Run the scan
  const runScan = () => {
    const text = extractText();
    
    // Request data from background script
    chrome.runtime.sendMessage({ action: "scanRequest", text }, (response) => {
      if (response && response.keywords) {
        // Simplified scan using scanner logic (in a real app we'd import scanner.js, 
        // but content scripts can't easily import ES modules without a bundler, 
        // so we duplicate minimal logic here or do the analysis in background)
        
        let score = 100;
        let status = 'safe';
        const textLower = text.toLowerCase();

        for (const keyword of response.keywords) {
          if (textLower.includes(keyword.term.toLowerCase())) {
            score -= keyword.weight;
          }
        }

        if (score < 40) status = 'danger';
        else if (score < 70) status = 'warning';

        injectShieldUI(Math.max(0, score), status);
      }
    });
  };

  // Check settings and run
  chrome.storage.local.get(['settings'], (result) => {
    const autoScan = result.settings?.autoScan ?? true;
    if (autoScan) {
      setTimeout(runScan, 1500); // Wait a bit for SPA sites to render
    }
  });
})();

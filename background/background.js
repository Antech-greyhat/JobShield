// Background Service Worker
chrome.runtime.onInstalled.addListener(() => {
  console.log("JobShield Installed");
  
  // Set default settings
  chrome.storage.local.set({
    settings: {
      autoScan: true,
      darkMode: false
    }
  });
});

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "scanRequest") {
    // We could fetch real data from an API here in the future
    // For now, we simulate fetching the mock data
    Promise.all([
      fetch(chrome.runtime.getURL('data/scamkeywords.json')).then(res => res.json()),
      fetch(chrome.runtime.getURL('data/verifiedcompanies.json')).then(res => res.json())
    ]).then(([keywords, companies]) => {
      sendResponse({ keywords, companies });
    }).catch(err => {
      console.error("Error loading mock data", err);
      sendResponse({ error: "Failed to load data" });
    });
    
    // Return true to indicate we will respond asynchronously
    return true; 
  }
});

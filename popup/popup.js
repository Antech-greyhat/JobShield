import { initNavigation } from '../scripts/navigation.js';

// Define the routes available in the SPA
const routes = {
  analysis: {
    template: '../pages/analysis/index.html',
    init: () => {
      // Logic when analysis page loads
      console.log('Analysis page loaded');
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
      console.log('Report page loaded');
    }
  },
  settings: {
    template: '../pages/settings/index.html',
    init: () => {
      console.log('Settings page loaded');
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize navigation with 'analysis' as the default route
  const nav = initNavigation(routes, 'analysis');
});

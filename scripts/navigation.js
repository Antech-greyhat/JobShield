// SPA navigation controller for the popup
export const initNavigation = (routes, defaultRoute = 'home') => {
  const container = document.getElementById('page-container');

  const navigate = async (routeId) => {
    const route = routes[routeId];
    if (!route) return;

    // Load HTML fragment
    try {
      const response = await fetch(route.template);
      const html = await response.text();
      container.innerHTML = html;

      // Update active nav state for bottom navigation
      document.querySelectorAll('.nav-item').forEach(item => {
        if (item.dataset.route === routeId) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      });

      // Execute route specific logic if provided
      if (typeof route.init === 'function') {
        route.init(navigate);
      }
    } catch (err) {
      console.error('Failed to load page:', err);
    }
  };

  // Event delegation for all route links (handles dynamically injected content)
  document.body.addEventListener('click', (e) => {
    const link = e.target.closest('[data-route]');
    if (link) {
      e.preventDefault();
      navigate(link.dataset.route);
    }
  });

  // Initial load
  navigate(defaultRoute);

  return { navigate };
};

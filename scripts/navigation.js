// SPA navigation controller for the popup
export const initNavigation = (routes, defaultRoute = 'home') => {
  const container = document.getElementById('page-container');
  const navItems = document.querySelectorAll('.nav-item');

  const navigate = async (routeId) => {
    const route = routes[routeId];
    if (!route) return;

    // Load HTML fragment
    try {
      const response = await fetch(route.template);
      const html = await response.text();
      container.innerHTML = html;

      // Update active nav state
      navItems.forEach(item => {
        if (item.dataset.route === routeId) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      });

      // Execute route specific logic if provided
      if (typeof route.init === 'function') {
        route.init();
      }
    } catch (err) {
      console.error('Failed to load page:', err);
    }
  };

  // Setup click listeners on nav items
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(item.dataset.route);
    });
  });

  // Initial load
  navigate(defaultRoute);

  return { navigate };
};

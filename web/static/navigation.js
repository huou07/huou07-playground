const routeTitles = {
  home: 'Home', apps: 'Applications', system: 'System', services: 'Services & Processes',
  files: 'Files', ssh: 'SSH', network: 'Network & VPN', storage: 'Storage', settings: 'Settings'
};

function closeNavigation() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('scrim').classList.remove('show');
  document.getElementById('menu').setAttribute('aria-expanded', 'false');
}

function showRoute(route) {
  if (!Object.hasOwn(routeTitles, route)) route = 'home';
  for (const page of document.querySelectorAll('[data-view]')) {
    const active = page.dataset.view === route;
    page.hidden = !active;
    page.classList.toggle('active', active);
  }
  for (const link of document.querySelectorAll('[data-route]')) {
    const active = link.dataset.route === route;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  document.title = `${routeTitles[route]} · huou07 playground`;
  const search = document.getElementById('search');
  if (search.value) {
    search.value = '';
    search.dispatchEvent(new Event('input', { bubbles: true }));
  }
  closeNavigation();
  window.scrollTo(0, 0);
}

function readRoute() {
  const route = location.hash.startsWith('#/') ? location.hash.slice(2) : 'home';
  if (route in routeTitles) showRoute(route);
  else {
    history.replaceState(null, '', `${location.pathname}${location.search}#/home`);
    showRoute('home');
  }
}

window.addEventListener('hashchange', readRoute);
document.addEventListener('click', event => {
  const link = event.target.closest('[data-route]');
  if (link) closeNavigation();
});
document.getElementById('menu').addEventListener('click', () => {
  const open = document.getElementById('sidebar').classList.contains('open');
  document.getElementById('menu').setAttribute('aria-expanded', String(open));
});
document.getElementById('scrim').addEventListener('click', closeNavigation);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeNavigation();
});
readRoute();

const themeButton = document.getElementById('theme');
const themeSetting = document.getElementById('theme-setting');
themeSetting.value = document.documentElement.dataset.theme;
themeButton.addEventListener('click', () => {
  themeSetting.value = document.documentElement.dataset.theme;
});
themeSetting.addEventListener('change', () => {
  if (themeSetting.value !== document.documentElement.dataset.theme) themeButton.click();
});

const refreshSetting = document.getElementById('refresh-interval');
const allowedIntervals = ['5000', '10000', '15000', '30000'];
const savedInterval = localStorage.getItem('metricsRefreshMs');
refreshSetting.value = allowedIntervals.includes(savedInterval) ? savedInterval : '5000';
refreshSetting.addEventListener('change', () => {
  localStorage.setItem('metricsRefreshMs', refreshSetting.value);
  window.dispatchEvent(new CustomEvent('metrics-refresh-change', { detail: Number(refreshSetting.value) }));
});

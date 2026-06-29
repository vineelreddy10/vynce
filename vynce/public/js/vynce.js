/* ── Vynce SPA Framework ───────────────────────────── */
/* Frappe-backed dating app with Stitch design parity   */
/* ──────────────────────────────────────────────────── */

(function() {
  'use strict';

  const V = window.VYNCE = {};

  /* ======================================================
   * SECTION 1: API Client
   * ====================================================== */

  V.api = {
    call(method, args = {}) {
      return new Promise((resolve, reject) => {
        frappe.call({
          method: `vynce.${method}`,
          args,
          callback(r) { resolve(r.message); },
          error(e) { reject(e); },
        });
      });
    },
    getCsrf() {
      return frappe.csrf_token;
    },
  };

  /* ======================================================
   * SECTION 2: Session / Auth
   * ====================================================== */

  V.session = { user: null, profile: null };

  V.initSession = async function() {
    try {
      const data = await V.api.call('api.get_session_user');
      if (data && data.user) {
        V.session.user = data.user;
        V.session.profile = await V.api.call('profile.get_my_profile');
        return true;
      }
    } catch (e) { /* not logged in */ }
    return false;
  };

  V.register = async function(email, password, displayName, birthDate, gender) {
    return V.api.call('api.register', { email, password, display_name: displayName, birth_date: birthDate, gender });
  };

  V.login = async function(email, password) {
    return new Promise((resolve, reject) => {
      frappe.call({
        method: 'login',
        args: { usr: email, pwd: password },
        callback(r) {
          if (r.message && r.message === 'Logged In') resolve(r);
          else reject(new Error('Login failed'));
        },
        error: reject,
      });
    });
  };

  V.logout = async function() {
    return new Promise((resolve) => {
      frappe.call({ method: 'logout', callback: resolve });
    });
  };

  /* ======================================================
   * SECTION 3: Router
   * ====================================================== */

  const screens = {};
  let currentScreen = null;
  let currentRoute = null;
  const routeParams = {};

  V.router = {
    register(name, config) {
      screens[name] = config;
    },
    async go(name, params = {}) {
      if (currentScreen === name && !params.force) return;
      const screen = screens[name];
      if (!screen) { console.error(`Screen "${name}" not found`); return; }

      // Deactivate current
      if (currentScreen && screens[currentScreen] && screens[currentScreen].onLeave) {
        screens[currentScreen].onLeave();
      }

      currentScreen = name;
      currentRoute = name;
      Object.assign(routeParams, params);

      const container = document.getElementById('app');
      // Remove all screens
      container.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));

      let el = document.getElementById(`screen-${name}`);
      if (!el) {
        el = document.createElement('div');
        el.id = `screen-${name}`;
        el.className = 'screen';
        container.appendChild(el);
        if (screen.render) {
          el.innerHTML = screen.render(params);
        }
      }
      el.classList.add('active');

      window.scrollTo(0, 0);

      if (screen.onEnter) screen.onEnter(el, params);
    },
    get current() { return currentRoute; },
    params: routeParams,
  };

  /* ======================================================
   * SECTION 4: Utilities
   * ====================================================== */

  V.utils = {
    $(sel, ctx) { return (ctx || document).querySelector(sel); },
    $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); },
    escape(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    },
    age(birthDate) {
      if (!birthDate) return '';
      const today = new Date();
      const bd = new Date(birthDate);
      let age = today.getFullYear() - bd.getFullYear();
      const m = today.getMonth() - bd.getMonth();
      if (m < 0 || (m === 0 && today.getDate() < bd.getDate())) age--;
      return age;
    },
    timeAgo(dateStr) {
      if (!dateStr) return '';
      const now = new Date();
      const d = new Date(dateStr);
      const sec = Math.floor((now - d) / 1000);
      if (sec < 60) return 'just now';
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}m ago`;
      const hrs = Math.floor(min / 60);
      if (hrs < 24) return `${hrs}h ago`;
      const days = Math.floor(hrs / 24);
      if (days < 7) return `${days}d ago`;
      return d.toLocaleDateString();
    },
    formatDate(dateStr) {
      if (!dateStr) return '';
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },
    formatTime(dateStr) {
      if (!dateStr) return '';
      const d = new Date(dateStr);
      return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    },
    month(dateStr) {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', { month: 'short' });
    },
    day(dateStr) {
      const d = new Date(dateStr);
      return d.getDate();
    },
  };

  /* ======================================================
   * SECTION 5: Common UI Components
   * ====================================================== */

  V.ui = {
    topbar(title, icon = 'hub', actions = '') {
      return `
        <header class="topbar">
          <div class="topbar-inner">
            <div class="topbar-brand">
              <span class="material-symbols-outlined icon">${icon}</span>
              <h1>${V.utils.escape(title)}</h1>
            </div>
            <div class="topbar-actions">${actions}</div>
          </div>
        </header>`;
    },

    searchInput(placeholder) {
      return `
        <div class="search-bar">
          <span class="material-symbols-outlined icon">search</span>
          <input type="text" placeholder="${V.utils.escape(placeholder)}">
        </div>`;
    },

    bottomNav() {
      const items = [
        { id: 'discover', icon: 'explore', label: 'Discover' },
        { id: 'feed', icon: 'diversity_3', label: 'Feed' },
        { id: 'messages', icon: 'chat', label: 'Messages' },
        { id: 'groups', icon: 'groups', label: 'Groups' },
        { id: 'events', icon: 'event', label: 'Events' },
        { id: 'profile', icon: 'person', label: 'Profile' },
      ];
      return `
        <nav class="bottom-nav">
          ${items.map(item => `
            <button class="nav-item${currentRoute === item.id ? ' active' : ''}" data-nav="${item.id}">
              <span class="material-symbols-outlined icon">${item.icon}</span>
              <span>${item.label}</span>
            </button>`).join('')}
        </nav>`;
    },

    loading() {
      return '<div class="empty-state"><div class="material-symbols-outlined icon" style="animation: spin 1s linear infinite;">sync</div><h3>Loading...</h3></div>';
    },

    bottomNavEvents() {
      setTimeout(() => {
        document.querySelectorAll('.nav-item[data-nav]').forEach(el => {
          el.addEventListener('click', () => {
            V.router.go(el.dataset.nav);
          });
        });
      }, 0);
    },
  };

  /* ======================================================
   * SECTION 6: Screen Registration
   * ====================================================== */

  // Each screen module will call V.router.register()
  // Screens are loaded from separate files and registered here

  V.registerScreens = async function() {
    // Load all screen modules
    const screenModules = [
      'auth', 'discover', 'feed', 'messages', 'groups', 'events', 'profile'
    ];
    for (const mod of screenModules) {
      try {
        const script = document.createElement('script');
        script.src = `/assets/vynce/js/screens/${mod}.js`;
        script.async = false;
        document.head.appendChild(script);
        await new Promise((resolve, reject) => {
          script.onload = resolve;
          script.onerror = reject;
        });
      } catch (e) {
        console.warn(`Screen module "${mod}" failed to load:`, e);
      }
    }
  };

  /* ======================================================
   * SECTION 7: Bootstrap
   * ====================================================== */

  V.bootstrap = async function() {
    const app = document.getElementById('app');

    // Show loading
    app.innerHTML = `
      <div class="app-container">
        <div class="empty-state" style="min-height:100vh;justify-content:center;">
          <div class="material-symbols-outlined icon" style="font-size:48px;animation:spin 1s linear infinite;">sync</div>
          <h3>Loading Vynce...</h3>
        </div>
      </div>`;

    // Register screens
    await V.registerScreens();

    // Check session
    const loggedIn = await V.initSession();

    // Navigate
    if (loggedIn) {
      V.router.go('discover');
    } else {
      V.router.go('login');
    }
  };

  // Boot when Frappe is ready
  frappe.ready(() => {
    // Add spin animation
    const style = document.createElement('style');
    style.textContent = `@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
    document.head.appendChild(style);
    V.bootstrap();
  });

})();

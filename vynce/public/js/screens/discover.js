(function() {
  const V = window.VYNCE;
  let profiles = [];
  let currentIndex = 0;
  let isLoading = false;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragCurrentX = 0;

  V.router.register('discover', {
    render() {
      return `
      <div class="app-container">
        ${V.ui.topbar('Discover', 'explore')}
        <main class="flex-grow flex flex-col items-center justify-center px-4 pt-4 pb-24 overflow-hidden max-w-container">
          <!-- Swipeable Card Container -->
          <div class="relative w-full max-w-md aspect-[3/4]" id="card-container">
            <div class="text-center text-[#594141] body-md mt-20" id="no-profiles">
              <div class="material-symbols-outlined" style="font-size:64px;color:var(--outline);margin-bottom:16px;">search_off</div>
              <h3 class="headline-md mb-2">No profiles to show</h3>
              <p class="body-md">Check back later or adjust your preferences.</p>
            </div>
            <div id="profile-card" class="profile-card" style="display:none;">
              <img id="card-img" src="" alt="">
              <div class="gradient-overlay"></div>
              <div class="card-badge" id="card-badge" style="display:none;">
                <span class="material-symbols-outlined icon">star</span>
                <span id="badge-text">Community Leader</span>
              </div>
              <div class="card-info">
                <h2 id="card-name">Name, Age</h2>
                <p id="card-bio">Bio text</p>
                <div class="tags" id="card-tags"></div>
              </div>
            </div>
          </div>

          <!-- Desktop Grid (hidden on mobile) -->
          <div id="discover-grid" class="desktop-only" style="display:none;width:100%;">
            <div class="flex items-center justify-between mb-6">
              <h2 class="headline-md">Discover People</h2>
              <p class="text-[#594141]">Find your next community spark</p>
            </div>
            <div class="profile-grid" id="profile-grid"></div>
          </div>

          <!-- Swipe Actions -->
          <div class="swipe-actions mobile-only" id="swipe-actions" style="display:none;">
            <button class="swipe-btn pass" id="btn-pass">
              <span class="material-symbols-outlined">close</span>
            </button>
            <button class="swipe-btn super-like" id="btn-super">
              <span class="material-symbols-outlined">star</span>
            </button>
            <button class="swipe-btn like" id="btn-like">
              <span class="material-symbols-outlined">favorite</span>
            </button>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      await this.loadProfiles(el);
      this.bindEvents(el);
    },

    async loadProfiles(el) {
      if (isLoading) return;
      isLoading = true;
      try {
        profiles = await V.api.call('discover.get_feed', { page: 1, page_size: 20 });
        if (!profiles || profiles.length === 0) profiles = [];
        currentIndex = 0;
        if (profiles.length > 0) {
          this.showProfile(el);
        } else {
          this.showEmpty(el);
        }
      } catch (e) {
        console.error('Failed to load profiles:', e);
        this.showEmpty(el);
      }
      isLoading = false;
      this.updateGrid(el);
    },

    showProfile(el) {
      const card = el.querySelector('#profile-card');
      const grid = el.querySelector('#discover-grid');
      const swipe = el.querySelector('#swipe-actions');
      const empty = el.querySelector('#no-profiles');

      if (window.innerWidth < 768) {
        if (currentIndex < profiles.length) {
          const p = profiles[currentIndex];
          card.style.display = 'block';
          swipe.style.display = 'flex';
          empty.style.display = 'none';
          grid.style.display = 'none';

          el.querySelector('#card-img').src = (p.photos && p.photos[0] && p.photos[0].image) || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400';
          el.querySelector('#card-name').textContent = `${p.display_name || 'Unknown'}, ${V.utils.age(p.birth_date)}`;
          el.querySelector('#card-bio').textContent = p.bio || 'No bio yet';

          const tagsEl = el.querySelector('#card-tags');
          tagsEl.innerHTML = '';
          if (p.interests && p.interests.length > 0) {
            p.interests.slice(0, 3).forEach(i => {
              const span = document.createElement('span');
              span.textContent = typeof i === 'string' ? i : (i.title || i.interest || '');
              tagsEl.appendChild(span);
            });
          }

          const badge = el.querySelector('#card-badge');
          badge.style.display = 'none';
        } else {
          card.style.display = 'none';
          swipe.style.display = 'none';
          empty.style.display = 'flex';
        }
      } else {
        card.style.display = 'none';
        swipe.style.display = 'none';
        grid.style.display = 'block';
        this.renderGrid(el);
      }
    },

    renderGrid(el) {
      const grid = el.querySelector('#profile-grid');
      if (profiles.length === 0) {
        grid.innerHTML = '<div class="empty-state col-span-full"><h3>No profiles found</h3></div>';
        return;
      }
      grid.innerHTML = profiles.map(p => `
        <div class="profile-grid-item" data-user="${V.utils.escape(p.user || '')}">
          <img src="${(p.photos && p.photos[0] && p.photos[0].image) || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400'}" alt="">
          <div class="info">
            <h3>${V.utils.escape(p.display_name || 'Unknown')}, ${V.utils.age(p.birth_date)}</h3>
            <p>${V.utils.escape((p.bio || '').substring(0, 60))}</p>
            ${p.interests && p.interests.length > 0 ? `<div style="display:flex;gap:4px;margin-top:8px;flex-wrap:wrap;">${p.interests.slice(0,3).map(i => `<span class="interest-tag">${typeof i === 'string' ? i : (i.title || i.interest || '')}</span>`).join('')}</div>` : ''}
          </div>
        </div>`).join('');
    },

    updateGrid(el) {
      const grid = el.querySelector('#discover-grid');
      if (grid && grid.style.display !== 'none') {
        this.renderGrid(el);
      }
    },

    showEmpty(el) {
      el.querySelector('#profile-card').style.display = 'none';
      el.querySelector('#swipe-actions').style.display = 'none';
      el.querySelector('#no-profiles').style.display = 'block';
    },

    async doLike(el) {
      if (currentIndex >= profiles.length) return;
      const p = profiles[currentIndex];
      try {
        await V.api.call('discover.like_user', { liked_user: p.user });
        const match = await V.api.call('match.check_and_create_match', { liked_user: p.user });
        currentIndex++;
        this.showProfile(el);
        if (match) {
          this.showMatchModal(el, p, match);
        }
      } catch (e) {
        currentIndex++;
        this.showProfile(el);
      }
    },

    async doPass(el) {
      if (currentIndex >= profiles.length) return;
      currentIndex++;
      this.showProfile(el);
    },

    async doSuperLike(el) {
      if (currentIndex >= profiles.length) return;
      const p = profiles[currentIndex];
      try {
        await V.api.call('discover.like_user', { liked_user: p.user, like_type: 'Super Like' });
        currentIndex++;
        this.showProfile(el);
      } catch (e) {
        currentIndex++;
        this.showProfile(el);
      }
    },

    showMatchModal(el, p, match) {
      const modal = document.createElement('div');
      modal.className = 'match-modal';
      modal.innerHTML = `
        <div class="avatars">
          <img src="${V.session.profile && V.session.profile.photos && V.session.profile.photos[0] ? V.session.profile.photos[0].image : 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200'}" alt="">
          <img src="${(p.photos && p.photos[0] && p.photos[0].image) || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200'}" alt="">
        </div>
        <h2>It's a Match!</h2>
        <p class="body-lg" style="opacity:0.9;">You and ${V.utils.escape(p.display_name)} liked each other</p>
        <button class="btn-primary" id="btn-keep-swiping" style="background:white;color:#b3263a;box-shadow:none;">Keep Swiping</button>
        <button class="btn-ghost" id="btn-send-message" style="color:white;">Send a Message</button>
      `;
      document.body.appendChild(modal);
      modal.querySelector('#btn-keep-swiping').addEventListener('click', () => modal.remove());
      modal.querySelector('#btn-send-message').addEventListener('click', () => {
        modal.remove();
        V.router.go('messages');
      });
    },

    bindEvents(el) {
      el.querySelector('#btn-like').addEventListener('click', () => this.doLike(el));
      el.querySelector('#btn-pass').addEventListener('click', () => this.doPass(el));
      el.querySelector('#btn-super').addEventListener('click', () => this.doSuperLike(el));

      // Swipe gestures
      const card = el.querySelector('#profile-card');
      if (card) {
        card.addEventListener('mousedown', (e) => this.startDrag(e, el));
        card.addEventListener('touchstart', (e) => this.startDrag(e, el), { passive: true });
        document.addEventListener('mousemove', (e) => this.onDrag(e));
        document.addEventListener('mouseup', () => this.endDrag(el));
        document.addEventListener('touchmove', (e) => this.onDrag(e), { passive: true });
        document.addEventListener('touchend', () => this.endDrag(el));
      }

      // Keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        if (V.router.current !== 'discover') return;
        if (e.key === 'ArrowLeft') this.doPass(el);
        if (e.key === 'ArrowRight') this.doLike(el);
        if (e.key === 'ArrowUp') this.doSuperLike(el);
      });
    },

    startDrag(e, el) {
      if (currentIndex >= profiles.length) return;
      isDragging = true;
      const pos = e.touches ? e.touches[0] : e;
      dragStartX = pos.clientX;
      dragStartY = pos.clientY;
      dragCurrentX = pos.clientX;
    },

    onDrag(e) {
      if (!isDragging) return;
      const pos = e.touches ? e.touches[0] : e;
      dragCurrentX = pos.clientX;
      const diff = dragCurrentX - dragStartX;
      const card = document.querySelector('#profile-card');
      if (card) {
        const rotate = diff * 0.08;
        const opacity = Math.max(0, 1 - Math.abs(diff) / 400);
        card.style.transform = `translateX(${diff}px) rotate(${rotate}deg)`;
        card.style.opacity = opacity;
      }
    },

    endDrag(el) {
      if (!isDragging) return;
      isDragging = false;
      const diff = dragCurrentX - dragStartX;
      const card = document.querySelector('#profile-card');
      if (card) {
        if (Math.abs(diff) > 100) {
          if (diff > 0) this.doLike(el);
          else this.doPass(el);
        }
        card.style.transform = '';
        card.style.opacity = '';
      }
    },
  });
})();

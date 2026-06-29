(function() {
  const V = window.VYNCE;
  let feedPosts = [];

  V.router.register('feed', {
    render() {
      return `
      <div class="app-container">
        <header class="fixed top-0 w-full z-50" style="background:rgba(248,249,250,0.8);backdrop-filter:blur(20px);border-bottom:1px solid rgba(0,0,0,0.06);">
          <div class="flex items-center justify-between px-5 h-16">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[#b3263a]" style="font-variation-settings:'FILL'1;">diversity_3</span>
              <h1 class="headline-lg-mobile font-bold text-[#b3263a]">Vynce</h1>
            </div>
            <button class="hover:opacity-80 transition-opacity">
              <span class="material-symbols-outlined text-[#594141]">settings</span>
            </button>
          </div>
        </header>

        <main class="pt-20 pb-24 px-5 max-w-container">
          <!-- Hero Profile Section -->
          <section class="relative mb-6" id="feed-hero"></section>

          <div class="flex items-center justify-between mb-4">
            <h2 class="headline-md">Community Feed</h2>
            <span class="caption text-[#b3263a] font-bold" id="feed-count">0 Posts</span>
          </div>

          <!-- Desktop Two-Column -->
          <div class="md:flex md:gap-6">
            <div class="md:w-2/3 space-y-4" id="posts-container">
              <div class="empty-state"><h3>No posts yet</h3><p>Connect with your community!</p></div>
            </div>
            <aside class="hidden md:block md:w-1/3 space-y-4">
              <div class="card p-4">
                <h3 class="headline-md mb-3">Upcoming Events</h3>
                <div id="feed-events-sidebar">
                  <div class="skeleton" style="height:60px;margin-bottom:8px;"></div>
                  <div class="skeleton" style="height:60px;margin-bottom:8px;"></div>
                </div>
              </div>
            </aside>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      await this.loadProfile(el);
      await this.loadPosts(el);
      await this.loadEvents(el);
    },

    async loadProfile(el) {
      try {
        const profile = V.session.profile;
        if (!profile) return;

        const container = el.querySelector('#feed-hero');
        const heroImg = (profile.photos && profile.photos[0] && profile.photos[0].image) || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400';

        container.innerHTML = `
          <div class="relative w-full aspect-[4/5] rounded-xl overflow-hidden shadow-lg">
            <img src="${heroImg}" class="w-full h-full object-cover" alt="">
            <div class="absolute inset-0" style="background:linear-gradient(to top,rgba(0,0,0,0.7),transparent);"></div>
            <div class="absolute top-4 right-4" style="background:rgba(255,255,255,0.9);backdrop-filter:blur(8px);padding:6px 12px;border-radius:9999px;display:flex;align-items:center;gap:6px;border:1px solid var(--outline-variant);">
              <span class="material-symbols-outlined text-[#5b5d72]" style="font-size:18px;font-variation-settings:'FILL'1;">verified</span>
              <span class="caption text-[#191c1d]">Community Leader</span>
            </div>
            <div class="absolute bottom-6 left-6 text-white">
              <h2 class="headline-lg">${V.utils.escape(profile.display_name || 'You')}, ${V.utils.age(profile.birth_date)}</h2>
              <p class="body-md" style="opacity:0.9;">${V.utils.escape(profile.bio || '')}</p>
              <div class="flex gap-2 mt-2">
                <span class="interest-tag" style="background:rgba(255,255,255,0.2);color:white;backdrop-filter:blur(4px);font-size:11px;">${profile.interests ? profile.interests.length : 0} Interests</span>
              </div>
            </div>
          </div>
          <div class="mt-4 p-4 rounded-xl" style="background:var(--surface-container-low);border:1px solid var(--outline-variant);">
            <div class="flex justify-between items-center mb-2">
              <span class="caption uppercase tracking-wider text-[#594141]">Community Profile Strength</span>
              <span class="caption text-[#b3263a] font-bold">${profile.profile_strength || 0}%</span>
            </div>
            <div class="strength-bar">
              <div class="fill" style="width:${profile.profile_strength || 0}%;"></div>
            </div>
          </div>`;
      } catch (e) {
        console.error('Failed to load profile:', e);
      }
    },

    async loadPosts(el) {
      try {
        const groups = await V.api.call('group.list_groups', { page: 1, page_size: 5 });
        const container = el.querySelector('#posts-container');

        if (!groups || !groups.groups || groups.groups.length === 0) {
          container.innerHTML = '<div class="empty-state"><span class="material-symbols-outlined" style="font-size:64px;opacity:0.3;">forum</span><h3>No posts yet</h3><p>Join groups to see community posts here.</p></div>';
          return;
        }

        container.innerHTML = groups.groups.map(g => `
          <div class="card p-4">
            <div class="flex items-center gap-3 mb-3">
              <img src="${g.cover_image || 'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=100'}" class="w-10 h-10 rounded-full object-cover" alt="">
              <div>
                <h4 class="font-semibold">${V.utils.escape(g.title)}</h4>
                <p class="caption text-[#594141]">${V.utils.escape(g.location || '')} · ${g.member_count || 0} members</p>
              </div>
            </div>
            <p class="body-md text-[#594141] mb-3">${V.utils.escape((g.description || '').substring(0, 120))}</p>
            <div class="flex items-center gap-4 text-sm text-[#594141]">
              <span class="flex items-center gap-1"><span class="material-symbols-outlined" style="font-size:18px;">group</span> ${g.member_count || 0}</span>
              <span class="interest-tag caption">${V.utils.escape(g.category || 'General')}</span>
              ${g.is_member ? '<span class="interest-tag active caption">Member</span>' : ''}
            </div>
          </div>`).join('');

        el.querySelector('#feed-count').textContent = `${groups.groups.length} Groups`;
      } catch (e) {
        console.error('Failed to load posts:', e);
      }
    },

    async loadEvents(el) {
      try {
        const sidebar = el.querySelector('#feed-events-sidebar');
        if (!sidebar) return;
        const events = await V.api.call('event.list_events', { page: 1, page_size: 3 });
        if (!events || !events.events || events.events.length === 0) {
          sidebar.innerHTML = '<p class="text-sm text-[#594141]">No upcoming events.</p>';
          return;
        }
        sidebar.innerHTML = events.events.slice(0, 3).map(ev => `
          <div class="flex items-center gap-3 py-2 border-b border-[#e1e3e4] last:border-0">
            <div class="text-center min-w-[40px]">
              <div class="caption uppercase text-[#b3263a] font-bold">${V.utils.month(ev.start_time)}</div>
              <div class="headline-md text-[#191c1d]">${V.utils.day(ev.start_time)}</div>
            </div>
            <div>
              <p class="font-semibold text-sm">${V.utils.escape(ev.title)}</p>
              <p class="caption text-[#594141]">${V.utils.escape(ev.location || '')}</p>
            </div>
          </div>`).join('');
      } catch (e) {
        console.error('Failed to load events:', e);
      }
    },
  });
})();

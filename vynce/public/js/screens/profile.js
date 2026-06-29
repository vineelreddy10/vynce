(function() {
  const V = window.VYNCE;
  let myProfile = null;

  V.router.register('profile', {
    render() {
      return `
      <div class="app-container">
        ${V.ui.topbar('Profile', 'person', `
          <button id="btn-edit-profile" class="btn-ghost">
            <span class="material-symbols-outlined">edit</span>
          </button>
        `)}
        <main class="px-5 pt-4 pb-24 max-w-container">
          <div class="max-w-lg mx-auto" id="profile-content">
            <div class="text-center">
              <div class="skeleton" style="width:120px;height:120px;border-radius:50%;margin:0 auto 16px;"></div>
              <div class="skeleton" style="height:32px;width:200px;margin:0 auto 8px;"></div>
              <div class="skeleton" style="height:20px;width:150px;margin:0 auto;"></div>
            </div>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      myProfile = V.session.profile;
      await this.loadProfile(el);
      this.bindEvents(el);
    },

    async loadProfile(el) {
      const container = el.querySelector('#profile-content');

      try {
        if (!myProfile) {
          myProfile = await V.api.call('profile.get_my_profile');
          V.session.profile = myProfile;
        }

        const p = myProfile;
        if (!p || !p.display_name) {
          container.innerHTML = this.renderEmptyProfile(el);
          return;
        }

        const primaryPhoto = (p.photos && p.photos.find(ph => ph.is_primary)?.image) ||
          (p.photos && p.photos[0]?.image) ||
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400';

        container.innerHTML = `
          <!-- Photo & Name -->
          <div class="text-center mb-8">
            <div class="relative inline-block">
              <img src="${primaryPhoto}" class="w-32 h-32 rounded-full object-cover border-4 border-white shadow-lg" alt="">
              <div class="absolute bottom-1 right-1 w-6 h-6 rounded-full flex items-center justify-center" style="background:var(--gradient);">
                <span class="material-symbols-outlined text-white" style="font-size:14px;">photo_camera</span>
              </div>
            </div>
            <h2 class="headline-lg mt-4">${V.utils.escape(p.display_name)}, ${V.utils.age(p.birth_date)}</h2>
            <p class="body-md text-[#594141]">${V.utils.escape(p.gender || '')}</p>
          </div>

          <!-- Profile Strength -->
          <div class="mb-6 p-4 rounded-xl" style="background:var(--surface-container-low);border:1px solid var(--outline-variant);">
            <div class="flex justify-between items-center mb-2">
              <span class="caption uppercase tracking-wider text-[#594141]">Profile Strength</span>
              <span class="caption text-[#b3263a] font-bold">${p.profile_strength || 0}%</span>
            </div>
            <div class="strength-bar">
              <div class="fill" style="width:${p.profile_strength || 0}%;"></div>
            </div>
          </div>

          <!-- Bio -->
          ${p.bio ? `
          <div class="mb-6">
            <h3 class="font-semibold mb-2 text-[#191c1d]">About</h3>
            <p class="body-md text-[#594141]">${V.utils.escape(p.bio)}</p>
          </div>` : ''}

          <!-- Interests -->
          ${p.interests && p.interests.length > 0 ? `
          <div class="mb-6">
            <h3 class="font-semibold mb-3 text-[#191c1d]">Interests</h3>
            <div class="flex flex-wrap gap-2">
              ${p.interests.map(i => `<span class="interest-tag">${typeof i === 'string' ? i : (i.title || i.interest || '')}</span>`).join('')}
            </div>
          </div>` : ''}

          <!-- Photos -->
          ${p.photos && p.photos.length > 0 ? `
          <div class="mb-6">
            <h3 class="font-semibold mb-3 text-[#191c1d]">Photos</h3>
            <div class="flex gap-3 overflow-x-auto hide-scrollbar">
              ${p.photos.map(ph => `
                <img src="${ph.image}" class="w-24 h-24 rounded-xl object-cover flex-shrink-0" alt="">
              `).join('')}
            </div>
          </div>` : ''}

          <!-- Account Actions -->
          <div class="space-y-3 mt-8">
            <button class="btn-secondary w-full" id="btn-settings">
              <span class="material-symbols-outlined">settings</span>
              Account Settings
            </button>
            <button class="btn-ghost w-full text-center text-[#ba1a1a]" id="btn-logout">
              <span class="material-symbols-outlined">logout</span>
              Sign Out
            </button>
          </div>
        `;
      } catch (e) {
        console.error('Failed to load profile:', e);
        container.innerHTML = '<div class="empty-state"><h3>Could not load profile</h3></div>';
      }
    },

    renderEmptyProfile(el) {
      return `
        <div class="empty-state">
          <span class="material-symbols-outlined" style="font-size:64px;opacity:0.3;">person</span>
          <h3>Set up your profile</h3>
          <p>Add photos and interests to get started</p>
          <button id="btn-create-profile" class="btn-primary mt-4">
            <span class="material-symbols-outlined">edit</span>
            Create Profile
          </button>
        </div>`;
    },

    bindEvents(el) {
      const logoutBtn = el.querySelector('#btn-logout');
      if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
          await V.logout();
          V.session.user = null;
          V.session.profile = null;
          V.router.go('login');
        });
      }
    },
  });
})();

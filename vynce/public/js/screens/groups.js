(function() {
  const V = window.VYNCE;
  let groups = [];
  const categories = ['All', 'Tech', 'Fitness', 'Travel', 'Arts', 'Music', 'Food', 'Wellness', 'Lifestyle', 'Books'];

  V.router.register('groups', {
    render() {
      return `
      <div class="app-container">
        ${V.ui.topbar('Groups', 'groups', `<button class="text-[#b3263a] flex items-center gap-1 font-semibold" id="btn-create-group"><span>Create</span><span class="material-symbols-outlined">add</span></button>`)}
        <main class="px-5 pt-4 pb-24 max-w-container">
          <h2 class="headline-lg-mobile md:headline-lg mb-2">Discover Groups</h2>
          <p class="body-md text-[#594141] mb-6">Find your people, find your vibe</p>

          ${V.ui.searchInput('Search groups...')}

          <div class="category-pills mt-4 mb-6" id="group-categories">
            ${categories.map(cat => `
              <button class="chip ${cat === 'All' ? 'active' : ''}" data-cat="${cat}">${cat}</button>
            `).join('')}
          </div>

          <!-- Cards Grid -->
          <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3" id="groups-grid">
            <div class="skeleton" style="height:280px;border-radius:16px;"></div>
            <div class="skeleton" style="height:280px;border-radius:16px;"></div>
            <div class="skeleton" style="height:280px;border-radius:16px;"></div>
          </div>

          <div id="groups-empty" class="empty-state" style="display:none;">
            <span class="material-symbols-outlined" style="font-size:64px;opacity:0.3;">groups</span>
            <h3>No groups found</h3>
            <p>Try a different category or search term</p>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      this.bindEvents(el);
      await this.loadGroups(el, 'All');
    },

    bindEvents(el) {
      const searchInput = el.querySelector('.search-bar input');
      searchInput.addEventListener('input', () => {
        const q = searchInput.value.trim();
        this.loadGroups(el, this.activeCategory || 'All', q);
      });

      el.querySelectorAll('#group-categories .chip').forEach(chip => {
        chip.addEventListener('click', () => {
          el.querySelectorAll('#group-categories .chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          this.activeCategory = chip.dataset.cat;
          this.loadGroups(el, this.activeCategory, searchInput.value.trim());
        });
      });

      el.querySelector('#btn-create-group').addEventListener('click', () => {
        V.router.go('groups');
      });
    },

    async loadGroups(el, category, search = '') {
      try {
        const result = await V.api.call('group.list_groups', {
          category: category === 'All' ? '' : category,
          search,
          page: 1,
          page_size: 20,
        });

        groups = (result && result.groups) || [];
        this.renderGroups(el);
      } catch (e) {
        console.error('Failed to load groups:', e);
        groups = [];
        this.renderGroups(el);
      }
    },

    renderGroups(el) {
      const grid = el.querySelector('#groups-grid');
      const empty = el.querySelector('#groups-empty');

      if (groups.length === 0) {
        grid.innerHTML = '';
        empty.style.display = 'flex';
        return;
      }

      empty.style.display = 'none';
      grid.innerHTML = groups.map(g => `
        <div class="group-card">
          <img class="cover" src="${g.cover_image || 'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=400'}" alt="">
          <div class="body">
            <h3>${V.utils.escape(g.title)}</h3>
            <p>${V.utils.escape((g.description || '').substring(0, 80))}</p>
            <div class="flex gap-2 mt-3">
              <span class="interest-tag caption">${V.utils.escape(g.category || 'General')}</span>
              ${g.is_member ? '<span class="interest-tag active caption">Member</span>' : ''}
            </div>
          </div>
          <div class="footer">
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined" style="font-size:18px;">group</span>
              ${g.member_count || 0} members
            </span>
            ${g.location ? `<span class="flex items-center gap-1"><span class="material-symbols-outlined" style="font-size:18px;">location_on</span>${V.utils.escape(g.location)}</span>` : ''}
          </div>
        </div>`).join('');
    },
  });
})();

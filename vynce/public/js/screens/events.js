(function() {
  const V = window.VYNCE;
  let events = [];
  const categories = ['All', 'Workshops', 'Social', 'Music', 'Food', 'Outdoors', 'Tech', 'Wellness'];

  V.router.register('events', {
    render() {
      return `
      <div class="app-container">
        ${V.ui.topbar('Events', 'event', `<button class="text-[#b3263a] flex items-center gap-1 font-semibold"><span>Create</span><span class="material-symbols-outlined">add</span></button>`)}
        <main class="px-5 pt-4 pb-24 max-w-container">
          <h2 class="headline-lg-mobile md:headline-lg mb-6">Events</h2>

          <div class="relative group mb-6">
            <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-[#8d7070]">search</span>
            <input class="w-full rounded-full py-4 pl-12 pr-6 border border-[#e1bebe] focus:ring-2 focus:ring-[#5b5d72] focus:border-transparent transition-all outline-none text-base" placeholder="Find local meetups near you..." type="text" id="events-search">
          </div>

          <div class="flex gap-3 overflow-x-auto hide-scrollbar mb-8" id="event-categories">
            ${categories.map(cat => `
              <button class="chip ${cat === 'All' ? 'active' : ''}" data-cat="${cat}">${cat}</button>
            `).join('')}
          </div>

          <!-- Calendar Strip (Desktop) -->
          <div class="hidden md:flex gap-3 mb-6 overflow-x-auto hide-scrollbar" id="event-dates">
            ${[0,1,2,3,4,5,6].map(i => {
              const d = new Date();
              d.setDate(d.getDate() + i);
              const isToday = i === 0;
              const dayName = d.toLocaleDateString('en-US', { weekday: 'short' });
              const dayNum = d.getDate();
              return `
                <button class="flex flex-col items-center px-4 py-2 rounded-xl ${isToday ? 'text-white' : 'text-[#594141] bg-[#edeeef]'}" style="${isToday ? 'background:linear-gradient(135deg,#b3263a,#ff5f6d);' : ''}">
                  <span class="caption uppercase tracking-wider">${dayName}</span>
                  <span class="headline-md">${dayNum}</span>
                </button>`;
            }).join('')}
          </div>

          <!-- Event List -->
          <div class="space-y-4" id="events-list">
            <div class="skeleton" style="height:120px;border-radius:16px;"></div>
            <div class="skeleton" style="height:120px;border-radius:16px;"></div>
          </div>

          <div id="events-empty" class="empty-state" style="display:none;">
            <span class="material-symbols-outlined" style="font-size:64px;opacity:0.3;">event_busy</span>
            <h3>No events found</h3>
            <p>Check back later or adjust your filters</p>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      this.bindEvents(el);
      await this.loadEvents(el, 'All');
    },

    bindEvents(el) {
      const searchInput = el.querySelector('#events-search');
      searchInput.addEventListener('input', () => {
        const q = searchInput.value.trim();
        this.loadEvents(el, this.activeCategory || 'All', q);
      });

      el.querySelectorAll('#event-categories .chip').forEach(chip => {
        chip.addEventListener('click', () => {
          el.querySelectorAll('#event-categories .chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          this.activeCategory = chip.dataset.cat;
          this.loadEvents(el, this.activeCategory, searchInput.value.trim());
        });
      });
    },

    async loadEvents(el, category, search = '') {
      try {
        const result = await V.api.call('event.list_events', {
          category: category === 'All' ? '' : category,
          search,
          page: 1,
          page_size: 20,
          sort_by: 'start_time',
          sort_order: 'asc',
        });

        events = (result && result.events) || [];
        this.renderEvents(el);
      } catch (e) {
        console.error('Failed to load events:', e);
        events = [];
        this.renderEvents(el);
      }
    },

    renderEvents(el) {
      const list = el.querySelector('#events-list');
      const empty = el.querySelector('#events-empty');

      if (events.length === 0) {
        list.innerHTML = '';
        empty.style.display = 'flex';
        return;
      }

      empty.style.display = 'none';
      list.innerHTML = events.map(ev => `
        <div class="event-card">
          <div class="date-badge">
            <div class="month">${V.utils.month(ev.start_time)}</div>
            <div class="day">${V.utils.day(ev.start_time)}</div>
          </div>
          <div class="body">
            <h3>${V.utils.escape(ev.title)}</h3>
            <p>${V.utils.escape((ev.subtitle || ev.description || '').substring(0, 80))}</p>
            <div class="meta">
              <span><span class="material-symbols-outlined" style="font-size:16px;">schedule</span>${V.utils.formatTime(ev.start_time)}</span>
              ${ev.location ? `<span><span class="material-symbols-outlined" style="font-size:16px;">location_on</span>${V.utils.escape(ev.location)}</span>` : ''}
              <span><span class="material-symbols-outlined" style="font-size:16px;">group</span>${ev.going_count || 0} going</span>
            </div>
            <div class="flex gap-2 mt-3">
              <span class="interest-tag caption">${V.utils.escape(ev.category || 'General')}</span>
              ${ev.is_free ? '<span class="interest-tag caption" style="background:var(--tertiary-container);color:var(--on-tertiary-container);">Free</span>' : ''}
              ${ev.is_featured ? '<span class="interest-tag active caption">Featured</span>' : ''}
            </div>
          </div>
        </div>`).join('');
    },
  });
})();

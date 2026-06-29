(function() {
  const V = window.VYNCE;
  let conversations = [];
  let currentConv = null;

  V.router.register('messages', {
    render() {
      return `
      <div class="app-container">
        <header class="fixed top-0 w-full z-50" style="background:rgba(248,249,250,0.8);backdrop-filter:blur(20px);border-bottom:1px solid rgba(0,0,0,0.06);">
          <div class="flex items-center justify-between px-5 h-16">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[#b3263a]" style="font-variation-settings:'FILL'1;">electric_bolt</span>
              <h1 class="headline-lg-mobile font-bold text-[#b3263a]">Vynce</h1>
            </div>
            <div class="flex items-center gap-4">
              <button class="hover:opacity-80 transition-opacity">
                <span class="material-symbols-outlined text-[#b3263a]">group_add</span>
              </button>
              <button class="hover:opacity-80 transition-opacity">
                <span class="material-symbols-outlined text-[#b3263a]">tune</span>
              </button>
            </div>
          </div>
        </header>

        <main class="pt-16 pb-24">
          <!-- Desktop Layout -->
          <div class="desktop-layout max-w-container">
            <!-- Sidebar -->
            <div class="desktop-sidebar">
              <div class="px-5 pt-4 pb-2">
                ${V.ui.searchInput('Search chats, groups or events')}
              </div>

              <!-- New Connections -->
              <section class="mt-4" id="connections-section">
                <div class="px-5 mb-3 flex justify-between items-end">
                  <h3 class="font-semibold text-[#191c1d]">Messages</h3>
                  <span class="caption text-[#b3263a] font-bold" id="conv-count">0</span>
                </div>
                <div id="conversations-list"></div>
              </section>
            </div>

            <!-- Main Chat Area -->
            <div class="desktop-main flex flex-col" id="chat-main">
              <div class="empty-state flex-1 flex flex-col items-center justify-center" id="chat-empty">
                <span class="material-symbols-outlined" style="font-size:64px;opacity:0.4;">chat</span>
                <h3>Your Messages</h3>
                <p>Match with someone to start chatting</p>
              </div>
              <div id="chat-view" style="display:none;flex:1;display:none;flex-direction:column;">
                <div id="chat-header" class="flex items-center gap-3 p-4 border-b border-[#e1e3e4]">
                  <img id="chat-avatar" class="w-10 h-10 rounded-full object-cover" src="" alt="">
                  <div>
                    <h3 id="chat-name" class="font-semibold"></h3>
                    <p id="chat-status" class="caption text-[#594141]">Online</p>
                  </div>
                </div>
                <div id="chat-messages" class="flex-1 overflow-y-auto p-4 space-y-2" style="display:flex;flex-direction:column;">
                  <div class="text-center caption text-[#594141] py-8">Start a conversation</div>
                </div>
                <div class="flex items-center gap-3 p-4 border-t border-[#e1e3e4]">
                  <input id="chat-input" type="text" class="input-field" placeholder="Type a message..." style="border-radius:9999px;">
                  <button id="btn-send" class="swipe-btn like" style="width:48px;height:48px;">
                    <span class="material-symbols-outlined" style="font-size:24px;">send</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
        ${V.ui.bottomNav()}
      </div>`;
    },

    async onEnter(el) {
      V.ui.bottomNavEvents();
      await this.loadConversations(el);
      this.bindEvents(el);
    },

    async loadConversations(el) {
      try {
        const matches = await V.api.call('match.get_matches');
        if (matches && matches.length > 0) {
          conversations = matches;
      } else {
        conversations = [];
        }
        this.renderConversations(el);
      } catch (e) {
        console.error('Failed to load conversations:', e);
        conversations = [];
        this.renderConversations(el);
      }
    },

    renderConversations(el) {
      const list = el.querySelector('#conversations-list');
      const count = el.querySelector('#conv-count');

      if (!conversations || conversations.length === 0) {
        list.innerHTML = `
          <div class="flex overflow-x-auto gap-4 px-5 pb-2 hide-scrollbar" id="new-connections">
            <div class="empty-state w-full" style="padding:24px;">
              <p class="text-sm text-[#594141]">No conversations yet.</p>
            </div>
          </div>`;
        count.textContent = '0';
        return;
      }

      const newConns = conversations.slice(0, 5);
      const newConnsHtml = `
        <div class="px-5 mb-4">
          <div class="flex overflow-x-auto gap-4 pb-2 hide-scrollbar">
            ${newConns.map(c => `
              <div class="text-center flex-shrink-0 cursor-pointer" data-match="${V.utils.escape(c.name || c.match_id || '')}">
                <div class="w-16 h-16 rounded-full mx-auto mb-1 overflow-hidden border-2 border-[#b3263a]">
                  <img src="${c.photos && c.photos[0] ? c.photos[0].image : 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200'}" class="w-full h-full object-cover" alt="">
                </div>
                <p class="caption font-semibold">${V.utils.escape(c.display_name || 'User')}</p>
              </div>`).join('')}
          </div>
        </div>`;

      // Message list
      const msgListHtml = conversations.map(c => {
        const lastMsg = c.last_message || '';
        return `
          <div class="msg-item" data-match="${V.utils.escape(c.name || c.match_id || '')}">
            <img class="avatar" src="${c.photos && c.photos[0] ? c.photos[0].image : 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200'}" alt="">
            <div class="content">
              <div class="top">
                <span class="name">${V.utils.escape(c.display_name || 'User')}</span>
                <span class="time">${c.last_active ? V.utils.timeAgo(c.last_active) : ''}</span>
              </div>
              <div class="preview">${V.utils.escape(lastMsg.substring(0, 60)) || 'Say hello!'}</div>
            </div>
            ${c.unread ? '<div class="unread"></div>' : ''}
          </div>`;
      }).join('');

      list.innerHTML = newConnsHtml + msgListHtml;
      count.textContent = conversations.length;

      // Bind click events
      list.querySelectorAll('.msg-item, [data-match]').forEach(el2 => {
        el2.addEventListener('click', () => {
          const matchId = el2.dataset.match;
          this.openConversation(matchId, el);
        });
      });
    },

    openConversation(matchId, el) {
      currentConv = conversations.find(c => (c.name === matchId || c.match_id === matchId));
      if (!currentConv) return;

      const empty = el.querySelector('#chat-empty');
      const view = el.querySelector('#chat-view');
      empty.style.display = 'none';
      view.style.display = 'flex';

      el.querySelector('#chat-avatar').src = (currentConv.photos && currentConv.photos[0]) ? currentConv.photos[0].image : 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200';
      el.querySelector('#chat-name').textContent = currentConv.display_name || 'User';
      el.querySelector('#chat-messages').innerHTML = this.renderMessages(currentConv);
    },

    renderMessages(conv) {
      if (conv.messages && conv.messages.length > 0) {
        return conv.messages.map(m => `
          <div class="chat-bubble ${m.is_sender ? 'sent' : 'received'}" style="align-self:${m.is_sender ? 'flex-end' : 'flex-start'};">
            ${V.utils.escape(m.content || m.text || '')}
            <div class="caption" style="opacity:0.6;margin-top:4px;font-size:10px;">${m.created_at ? V.utils.formatTime(m.created_at) : ''}</div>
          </div>`).join('');
      }
      return '<div class="text-center caption text-[#594141] py-8">Start a conversation</div>';
    },

    async sendMessage(el) {
      const input = el.querySelector('#chat-input');
      const text = input.value.trim();
      if (!text || !currentConv) return;

      try {
        await V.api.call('chat.send_message', { match_id: currentConv.name || currentConv.match_id, message: text });
        // Optimistically add message
        const msgContainer = el.querySelector('#chat-messages');
        const msgEl = document.createElement('div');
        msgEl.className = 'chat-bubble sent';
        msgEl.style.alignSelf = 'flex-end';
        msgEl.innerHTML = `${V.utils.escape(text)}<div class="caption" style="opacity:0.6;margin-top:4px;font-size:10px;">just now</div>`;
        msgContainer.appendChild(msgEl);
        msgContainer.scrollTop = msgContainer.scrollHeight;
        input.value = '';
      } catch (e) {
        console.error('Failed to send:', e);
      }
    },

    bindEvents(el) {
      el.querySelector('#btn-send').addEventListener('click', () => this.sendMessage(el));
      el.querySelector('#chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this.sendMessage(el);
      });
    },
  });
})();

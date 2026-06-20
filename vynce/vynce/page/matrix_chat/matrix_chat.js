frappe.pages['matrix-chat'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Matrix Chat',
		single_column: true
	});

	// Inject the HTML template into the page body
	$(page.body).html(frappe.templates["matrix_chat"]);

	// Initialize the chat
	MC.init(page);
};

var MC = {
	token: null,
	userId: null,
	currentRoom: null,
	pollTimer: null,

	init: function(page) {
		this.page = page;
		this.loadRooms();
		this.startPolling();

		var self = this;
		setTimeout(function() {
			var input = document.getElementById('mc-input');
			if (input) {
				input.addEventListener('keydown', function(e) {
					if (e.key === 'Enter') self.sendMessage();
				});
			}
		}, 200);
	},

	_api: function(method, params, callback) {
		frappe.call({
			method: 'vynce.matrix.frappe_api.' + method,
			args: params || {},
			callback: function(r) {
				if (callback) callback(r.message);
			}
		});
	},

	_matrix: function(endpoint, method, body, token, callback) {
		var xhr = new XMLHttpRequest();
		xhr.open(method, '/' + endpoint, true);
		xhr.setRequestHeader('Content-Type', 'application/json');
		if (token) xhr.setRequestHeader('Authorization', 'Bearer ' + token);
		xhr.onload = function() {
			if (callback) callback(JSON.parse(xhr.responseText));
		};
		xhr.send(body ? JSON.stringify(body) : null);
	},

	loadRooms: function() {
		var self = this;
		this._api('list_rooms', {}, function(rooms) {
			var list = document.getElementById('mc-room-list');
			if (!list) return;
			if (!rooms || rooms.length === 0) {
				list.innerHTML = '<div style="text-align:center;padding:20px;color:rgba(255,255,255,0.3);font-size:12px;">No rooms yet. Create one above.</div>';
				return;
			}
			var html = '';
			rooms.forEach(function(r) {
				html += '<div class="mc-room-item" data-room="' + r.room_id + '" style="padding:12px;border-radius:10px;cursor:pointer;margin-bottom:4px;color:#e8e3dd;" onclick="MC.selectRoom(\'' + r.room_id + '\')">';
				html += '<div style="font-size:13px;font-weight:500;">' + (r.name || 'Unnamed Room') + '</div>';
				html += '<div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:2px;">' + (r.member_count || 0) + ' members';
				if (r.last_message) html += ' \u00b7 ' + r.last_message.substring(0, 30);
				html += '</div></div>';
			});
			list.innerHTML = html;
		});
	},

	selectRoom: function(roomId) {
		var self = this;
		this.currentRoom = roomId;
		var items = document.querySelectorAll('.mc-room-item');
		items.forEach(function(el) { el.style.background = ''; });
		var activeEl = document.querySelector('.mc-room-item[data-room="' + roomId + '"]');
		if (activeEl) activeEl.style.background = 'rgba(255,255,255,0.08)';

		this._api('get_room_detail', { room_id: roomId }, function(detail) {
			if (!detail) return;
			var hdr = document.getElementById('mc-chat-header');
			if (hdr) hdr.style.display = 'block';
			var rn = document.getElementById('mc-room-name');
			if (rn) rn.textContent = detail.room.name || 'Unnamed Room';
			var rm = document.getElementById('mc-room-members');
			if (rm) rm.textContent = (detail.members ? detail.members.length : 0) + ' members';
			var msgs = document.getElementById('mc-messages');
			if (msgs) msgs.style.display = 'flex';
			var mt = document.getElementById('mc-empty');
			if (mt) mt.style.display = 'none';
			var inp = document.getElementById('mc-input-area');
			if (inp) inp.style.display = 'block';
			self.renderMessages(detail.events);
		});
	},

	renderMessages: function(events) {
		var container = document.getElementById('mc-messages');
		if (!container) return;
		if (!events || events.length === 0) {
			container.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;font-size:13px;">No messages yet.</div>';
			return;
		}
		var html = '';
		var prevSender = '';
		events.forEach(function(ev) {
			if (ev.type !== 'm.room.message') return;
			var body = ev.content ? (ev.content.body || '') : '';
			if (!body) return;
			var isMe = ev.sender === MC.userId;
			var showSender = ev.sender !== prevSender;
			prevSender = ev.sender;
			html += '<div style="display:flex;' + (isMe ? 'justify-content:flex-end' : 'justify-content:flex-start') + ';margin-bottom:4px;">';
			html += '<div style="max-width:70%;padding:8px 14px;border-radius:16px;font-size:13px;">';
			if (isMe) {
				html += 'background:linear-gradient(135deg,#ff5f6d,#ffc371);color:#fff;border-bottom-right-radius:4px;';
			} else {
				html += 'background:#f1f5f9;color:#1e293b;border-bottom-left-radius:4px;';
			}
			html += '">';
			if (!isMe && showSender) {
				html += '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:2px;">' + ev.sender + '</div>';
			}
			html += body + '</div></div>';
		});
		container.innerHTML = html;
	},

	sendMessage: function() {
		if (!this.currentRoom || !this.token) {
			frappe.msgprint('Create a test room first using the button in the sidebar.');
			return;
		}
		var input = document.getElementById('mc-input');
		if (!input) return;
		var text = input.value.trim();
		if (!text) return;
		input.value = '';
		var self = this;
		this._matrix('_matrix/client/v3/rooms/' + encodeURIComponent(this.currentRoom) + '/send/m.room.message/' + Date.now(),
			'PUT', { msgtype: 'm.text', body: text },
			this.token,
			function(resp) {
				if (resp.event_id) self.refreshMessages();
			}
		);
	},

	refreshMessages: function() {
		var self = this;
		if (this.currentRoom) {
			this._api('get_room_detail', { room_id: this.currentRoom }, function(detail) {
				if (detail) self.renderMessages(detail.events);
			});
		}
	},

	startPolling: function() {
		var self = this;
		if (this.pollTimer) clearInterval(this.pollTimer);
		this.pollTimer = setInterval(function() {
			self.loadRooms();
			if (self.currentRoom) self.refreshMessages();
		}, 3000);
	},

	createTestRoom: function() {
		var self = this;
		this._api('create_test_room', { name: 'Test Room ' + new Date().toLocaleTimeString() }, function(result) {
			if (result && result.room_id) {
				frappe.msgprint({
					title: 'Room Created',
					message: 'Room ID: ' + result.room_id + '<br>Users: ' + (result.users || []).join(', ') + '<br>Tokens: ' + (result.tokens || []).join(', ')
				});
				self.token = result.tokens[0];
				self.userId = '@' + result.users[0] + ':localhost';
				self.loadRooms();
				setTimeout(function() { self.selectRoom(result.room_id); }, 500);
			}
		});
	}
};

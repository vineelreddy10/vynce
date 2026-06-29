/* Auth screen - Login & Registration */
(function() {
  const V = window.VYNCE;

  V.router.register('login', {
    render() {
      return `
      <div class="app-container">
        <main class="min-h-screen flex flex-col md:flex-row">
          <!-- Visual Column -->
          <div class="relative h-[50vh] md:h-screen md:w-1/2 overflow-hidden">
            <div class="absolute inset-0 bg-cover bg-center" style="background-image: url('https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=1200');">
            </div>
            <div class="absolute inset-0 hero-gradient md:hidden" style="background:linear-gradient(180deg,transparent 0%,rgba(248,249,250,0.8) 60%,rgba(248,249,250,1) 100%);"></div>
            <div class="absolute inset-0 hidden md:block" style="background:linear-gradient(90deg,transparent 0%,rgba(248,249,250,0.2) 60%,rgba(248,249,250,1) 100%);"></div>
            <div class="absolute top-4 left-4 md:top-8 md:left-8 z-10 flex items-center gap-2">
              <span class="material-symbols-outlined text-[#b3263a] text-3xl">hub</span>
              <span class="headline-lg text-[#b3263a]">Vynce</span>
            </div>
          </div>

          <!-- Interactive Column -->
          <div class="flex-1 flex flex-col justify-center items-center px-5 md:px-16 py-12 bg-background md:w-1/2">
            <div class="max-w-md w-full space-y-8 text-center md:text-left">
              <!-- Typography -->
              <div class="space-y-4">
                <h1 class="headline-lg-mobile md:headline-lg text-[#191c1d]">Connect with your community.</h1>
                <p class="body-lg text-[#594141] max-w-sm mx-auto md:mx-0">
                  Join Vynce to discover local groups, shared interests, and meaningful connections.
                </p>
              </div>

              <!-- Login Form -->
              <div id="auth-form" class="space-y-4">
                <div class="space-y-3">
                  <input id="login-email" type="email" class="input-field" placeholder="Email" autocomplete="email">
                  <input id="login-password" type="password" class="input-field" placeholder="Password" autocomplete="current-password">
                </div>
                <button id="btn-login" class="btn-primary w-full">
                  <span class="material-symbols-outlined">login</span>
                  Sign In
                </button>
                <div class="flex items-center gap-4 py-2">
                  <div class="h-px flex-1" style="background:var(--outline-variant);"></div>
                  <span class="caption text-[#8d7070] uppercase tracking-widest">or</span>
                  <div class="h-px flex-1" style="background:var(--outline-variant);"></div>
                </div>
                <button id="btn-show-register" class="btn-secondary w-full">
                  <span class="material-symbols-outlined">person_add</span>
                  Create Account
                </button>
              </div>

              <!-- Register Form (hidden initially) -->
              <div id="register-form" class="space-y-4" style="display:none;">
                <div class="space-y-3">
                  <input id="reg-name" type="text" class="input-field" placeholder="Display Name">
                  <input id="reg-email" type="email" class="input-field" placeholder="Email" autocomplete="email">
                  <input id="reg-password" type="password" class="input-field" placeholder="Password (8+ chars, 1 uppercase, 1 number)" autocomplete="new-password">
                  <div class="flex gap-3">
                    <input id="reg-birth" type="date" class="input-field" placeholder="Birth Date">
                    <select id="reg-gender" class="input-field">
                      <option value="">Gender</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Non-Binary">Non-Binary</option>
                      <option value="Prefer not to say">Prefer not to say</option>
                    </select>
                  </div>
                </div>
                <button id="btn-register" class="btn-primary w-full">
                  <span class="material-symbols-outlined">how_to_reg</span>
                  Create Account
                </button>
                <button id="btn-show-login" class="btn-ghost w-full text-center">Already have an account? Sign In</button>
              </div>

              <p id="auth-error" class="text-sm text-[#ba1a1a] min-h-[20px]"></p>
            </div>
          </div>
        </main>
      </div>`;
    },

    onEnter(el) {
      el.querySelector('#btn-login').addEventListener('click', () => this.doLogin(el));
      el.querySelector('#btn-show-register').addEventListener('click', () => this.showRegister(el));
      el.querySelector('#btn-show-login')?.addEventListener('click', () => this.showLogin(el));
      el.querySelector('#btn-register').addEventListener('click', () => this.doRegister(el));

      el.querySelector('#login-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this.doLogin(el);
      });
      el.querySelector('#login-email').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') el.querySelector('#login-password').focus();
      });
    },

    showRegister(el) {
      el.querySelector('#auth-form').style.display = 'none';
      el.querySelector('#register-form').style.display = 'block';
      el.querySelector('#auth-error').textContent = '';
    },

    showLogin(el) {
      el.querySelector('#register-form').style.display = 'none';
      el.querySelector('#auth-form').style.display = 'block';
      el.querySelector('#auth-error').textContent = '';
    },

    async doLogin(el) {
      const email = el.querySelector('#login-email').value.trim();
      const password = el.querySelector('#login-password').value;
      const errEl = el.querySelector('#auth-error');
      errEl.textContent = '';

      if (!email || !password) { errEl.textContent = 'Please fill in all fields.'; return; }

      try {
        await V.login(email, password);
        V.session.user = email;
        V.session.profile = await V.api.call('profile.get_my_profile');
        V.router.go('discover');
      } catch (e) {
        errEl.textContent = 'Invalid email or password.';
      }
    },

    async doRegister(el) {
      const name = el.querySelector('#reg-name').value.trim();
      const email = el.querySelector('#reg-email').value.trim();
      const password = el.querySelector('#reg-password').value;
      const birth = el.querySelector('#reg-birth').value;
      const gender = el.querySelector('#reg-gender').value;
      const errEl = el.querySelector('#auth-error');
      errEl.textContent = '';

      if (!name || !email || !password || !birth || !gender) {
        errEl.textContent = 'Please fill in all fields.';
        return;
      }

      try {
        await V.register(email, password, name, birth, gender);
        V.session.user = email;
        V.session.profile = await V.api.call('profile.get_my_profile');
        V.router.go('discover');
      } catch (e) {
        errEl.textContent = e.message || 'Registration failed.';
      }
    },
  });
})();

import frappe, traceback
from datetime import date
from .utils import calculate_age, GENDER_MAP


@frappe.whitelist(allow_guest=True)
def ping():
	return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	return frappe.sessions.get_csrf_token()


@frappe.whitelist(allow_guest=True)
def get_session_user():
	user = frappe.session.user
	if user == "Guest":
		return {"user": None}
	return {"user": user}


@frappe.whitelist(allow_guest=True)
def register(email: str, password: str, display_name: str, birth_date: str, gender: str):
	"""Register a new user. Creates Frappe User + VY User Profile + logs in."""
	try:
		return _register(email, password, display_name, birth_date, gender)
	except frappe.exceptions.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(f"Register failed: {e}\n{traceback.format_exc()}", "Vynce Registration")
		frappe.throw(str(e))


def _register(email, password, display_name, birth_date, gender):
	email = email.strip().lower()
	display_name = display_name.strip()

	# ── Validation ──────────────────────────────────────────
	if not email or "@" not in email:
		frappe.throw("Please enter a valid email address.")

	if frappe.db.exists("User", email):
		frappe.throw("An account with this email already exists.")

	if len(password) < 8:
		frappe.throw("Password must be at least 8 characters.")
	if not any(c.isupper() for c in password):
		frappe.throw("Password must contain at least one uppercase letter.")
	if not any(c.isdigit() for c in password):
		frappe.throw("Password must contain at least one number.")

	try:
		birth = date.fromisoformat(birth_date)
	except ValueError:
		frappe.throw("Invalid date format. Use YYYY-MM-DD.")

	age = calculate_age(birth)
	if age < 18:
		frappe.throw("You must be at least 18 years old to register.")

	if gender not in GENDER_MAP:
		frappe.throw(f"Gender must be one of: {', '.join(GENDER_MAP.keys())}")

	# ── Ensure VY User role exists ──────────────────────────
	if not frappe.db.exists("Role", "VY User"):
		role_doc = frappe.get_doc({
			"doctype": "Role",
			"role_name": "VY User",
			"desk_access": 0,
		})
		role_doc.insert(ignore_permissions=True)

	# ── Create Frappe User (bypass Frappe's password policy) ─
	user_doc = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": display_name,
		"send_welcome_email": 0,
		"new_password": password,
		"roles": [{"role": "VY User"}],
	})
	user_doc.insert(ignore_permissions=True, ignore_links=True)

	# ── Create or update VY User Profile ───────────────────
	# (sync_user_profile hook may have already created a basic one)
	if frappe.db.exists("VY User Profile", {"user": email}):
		profile = frappe.get_doc("VY User Profile", {"user": email})
		profile.display_name = display_name
		profile.birth_date = birth_date
		profile.gender = GENDER_MAP[gender]
		profile.is_active = 1
		profile.profile_strength = 10
		profile.save(ignore_permissions=True)
	else:
		profile = frappe.get_doc({
			"doctype": "VY User Profile",
			"user": email,
			"display_name": display_name,
			"birth_date": birth_date,
			"gender": GENDER_MAP[gender],
			"is_active": 1,
			"profile_strength": 10,
		})
		profile.insert(ignore_permissions=True, ignore_links=True)

	# ── Login ───────────────────────────────────────────────
	frappe.local.login_manager.login_as(email)
	frappe.db.commit()

	return {
		"status": "ok",
		"user": email,
		"profile": profile.name,
	}


@frappe.whitelist()
def set_onboarding(interests: str = "[]", prompts: str = "[]",
                   age_min: int = 18, age_max: int = 60,
                   max_distance_km: int = 50, gender_preference: str = "All"):
	"""Save onboarding data to the user's VY User Profile."""
	import json
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("You must be logged in.")

	if not frappe.db.exists("VY User Profile", {"user": user}):
		frappe.throw("Profile not found.")

	profile = frappe.get_doc("VY User Profile", {"user": user})
	profile.age_min = age_min
	profile.age_max = age_max
	profile.max_distance_km = max_distance_km
	profile.gender_preference = gender_preference
	profile.profile_strength = min(profile.profile_strength + 40, 100)
	profile.save(ignore_permissions=True)

	# Save interests as VY Interest records if they don't exist
	interest_list = json.loads(interests)
	for title in interest_list:
		if title and not frappe.db.exists("VY Interest", title):
			try:
				frappe.get_doc({
					"doctype": "VY Interest",
					"title": title,
					"category": "Other",
				}).insert(ignore_permissions=True)
			except Exception:
				pass

	# Save prompts
	prompt_list = json.loads(prompts)
	profile.prompts = []
	for p in prompt_list:
		if p.get("answer"):
			profile.append("prompts", {"prompt": p["prompt"], "answer": p["answer"]})
	profile.save(ignore_permissions=True)

	frappe.db.commit()
	return {"status": "ok", "profile_strength": profile.profile_strength}

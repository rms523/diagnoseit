# DiagnoseIt — common project tasks (task runner, not a build graph)

.PHONY: help up down logs shell test migrate expo-start eas-android-apk eas-android-aab eas-submit-android

MOBILE_DIR := frontend/DiagnoseItApp
COMPOSE      := docker compose

# API URL baked into the JS bundle. Default = this machine's first IP.
# Override when the phone reaches this machine on another address:
#   make expo-start HOST_IP=192.168.x.x
HOST_IP ?= $(shell hostname -I 2>/dev/null | awk '{print $$1}')
EXPO_PUBLIC_API_URL ?= http://$(HOST_IP):8000/api

# Path to a local .aab from make eas-android-aab (required for submit)
# Example: make eas-submit-android AAB=./build-xxx.aab
AAB ?=

help:
	@echo "Dev(Docker):     up down logs shell test migrate"
	@if [ -f Makefile.local ]; then echo "Remote:          deploy-prod (sync local files)"; fi
	@echo "Mobile:          expo-start  (Metro --lan for Expo Go)"
	@echo "                 eas-android-apk eas-android-aab  (EAS --local only)"
	@echo "                 eas-submit-android AAB=path.aab  (Play Store via EAS Submit)"

# --- Dev (Docker Compose) ---

# Publishes the API on all interfaces so a phone can reach it; add the LAN IP to ALLOWED_HOSTS in .env.
up:
	DIAGNOSEIT_API_BIND=0.0.0.0 $(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

shell:
	$(COMPOSE) exec backend uv run python manage.py shell

# Installed apps + utils (utils is not in INSTALLED_APPS; include explicitly)
test:
	$(COMPOSE) exec backend uv run python manage.py test \
		users medical_reports prescriptions symptoms diagnosis lab_tests ai_settings utils

migrate:
	$(COMPOSE) exec backend uv run python manage.py migrate
	$(COMPOSE) exec backend uv run python manage.py populate_lab_tests

# --- Mobile ---

# Dev: Metro for Expo Go. Backend must be up (make up).
# Default: --lan (fully local). Prefer this + phone/emulator reachability.
# EXPO_HOST=tunnel uses Expo's ngrok relay (NOT local) — avoid unless you accept a third-party tunnel.
EXPO_HOST ?= lan
expo-start:
	@echo "API: $(EXPO_PUBLIC_API_URL)"
	@echo "Metro host mode: $(EXPO_HOST)"
	cd $(MOBILE_DIR) && EXPO_PUBLIC_API_URL=$(EXPO_PUBLIC_API_URL) npx expo start --$(EXPO_HOST)

# Release artifacts (EAS local only; never cloud)
eas-android-apk:
	@test -n "$(EXPO_PUBLIC_API_URL)" || (echo "EXPO_PUBLIC_API_URL is required"; exit 1)
	@case "$(EXPO_PUBLIC_API_URL)" in https://*) ;; *) echo "Release API URL must use HTTPS"; exit 1;; esac
	cd $(MOBILE_DIR) && EXPO_PUBLIC_API_URL=$(EXPO_PUBLIC_API_URL) npx eas-cli build --platform android --profile preview --local --non-interactive

eas-android-aab:
	@test -n "$(EXPO_PUBLIC_API_URL)" || (echo "EXPO_PUBLIC_API_URL is required"; exit 1)
	@case "$(EXPO_PUBLIC_API_URL)" in https://*) ;; *) echo "Release API URL must use HTTPS"; exit 1;; esac
	cd $(MOBILE_DIR) && EXPO_PUBLIC_API_URL=$(EXPO_PUBLIC_API_URL) npx eas-cli build --platform android --profile production --local --non-interactive

# Upload a locally built AAB to Google Play (does not run an EAS cloud build).
# Requires: eas login, Play Console app + credentials (service account or interactive).
eas-submit-android:
	@if [ -z "$(AAB)" ]; then echo "Usage: make eas-submit-android AAB=/path/to/app.aab"; exit 1; fi
	@test -f "$(AAB)" || (echo "AAB not found: $(AAB)"; exit 1)
	cd $(MOBILE_DIR) && npx eas-cli submit --platform android --profile production --path "$(abspath $(AAB))"

# Maintainer-only targets for the private parser corpus, when present.
-include samples/corpus.mk

# Optional machine-specific deployment target (gitignored).
-include Makefile.local

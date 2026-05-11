PODMAN_COMPOSE ?= podman compose
TFE_ENV_FILE ?= platform/tfe/.env
TFE_COMPOSE_FILE ?= platform/tfe/podman-compose.yml
DEMO_TERRAFORM_DIR ?= terraform/demo-workspace
DEMO_SENTINEL_POLICY ?= sentinel/policies/no-public-management-ingress.sentinel
PODMAN_ACTIVE_SOCKET_CMD = podman info --format '{{.Host.RemoteSocket.Path}}' 2>/dev/null | sed 's|^unix://||' || true
PODMAN_MACHINE_ROOTFUL_SOCKET_CMD = podman machine ssh 'if sudo test -S /run/podman/podman.sock; then printf "/run/podman/podman.sock\n"; fi' 2>/dev/null || true
PODMAN_MACHINE_ROOTLESS_SOCKET_CMD = podman machine ssh 'guest_socket="$${XDG_RUNTIME_DIR:-/run/user/$$(id -u)}/podman/podman.sock"; if ! test -S "$$guest_socket"; then systemctl --user start podman.socket >/dev/null 2>&1 || true; fi; if test -S "$$guest_socket"; then printf "%s\n" "$$guest_socket"; fi' 2>/dev/null || true
PODMAN_MACHINE_HOST_SOCKET_CMD = podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null || true
PODMAN_MACHINE_PORT_THRESHOLD_CMD = podman machine ssh 'sysctl -n net.ipv4.ip_unprivileged_port_start' 2>/dev/null || true

.PHONY: help check-prereqs check-tfe-env podman-socket podman-machine-allow-443 generate-certs podman-up podman-down podman-logs tfe-health terraform-fmt terraform-validate sentinel-test mcp-health demo-validate

help:
	@printf '%s\n' \
	  'Terraform AI Workflow Demo - Available targets:' \
	  '  make check-prereqs     # verify required local tools are installed' \
	  '  make check-tfe-env     # verify the local TFE env file and Podman socket' \
          '  make detect-host-alias-ip # detect the correct TFE_HOST_ALIAS_IP value for your system' \
	  '  make podman-socket     # print the detected local Podman API socket path' \
	  '  make podman-machine-allow-443 # lower the Podman machine port threshold so host 443 can be published' \
	  '  make generate-certs    # create self-signed TLS certs for tfe.localdemo.me' \
	  '  make podman-up         # start the local TFE, Postgres, and MinIO stack' \
	  '  make podman-down       # stop the local TFE stack' \
	  '  make podman-logs       # tail service logs from the local TFE stack' \
	  '  make tfe-health        # run the built-in Terraform Enterprise health check' \
	  '  make terraform-fmt     # format the Terraform configuration' \
	  '  make terraform-validate# init and validate the Terraform configuration' \
	  '  make sentinel-test     # run Sentinel tests for the example policy' \
	  '  make mcp-health        # check the optional streamable-http MCP endpoint' \
	  '  make demo-validate     # run local validation commands'

check-prereqs:
	@./scripts/check-prereqs.sh

check-tfe-env:
	@test -f "$(TFE_ENV_FILE)" || { printf 'missing %s; copy platform/tfe/.env.example to platform/tfe/.env\n' "$(TFE_ENV_FILE)" >&2; exit 1; }
	@set -a; . "$(TFE_ENV_FILE)"; set +a; \
	test -n "$$TFE_LICENSE" || { printf 'TFE_LICENSE is not set in %s\n' "$(TFE_ENV_FILE)" >&2; exit 1; }; \
	test -n "$$TFE_ENCRYPTION_PASSWORD" || { printf 'TFE_ENCRYPTION_PASSWORD is not set in %s\n' "$(TFE_ENV_FILE)" >&2; exit 1; }; \
	test -n "$$PODMAN_SOCKET" || { printf 'PODMAN_SOCKET is not set in %s\n' "$(TFE_ENV_FILE)" >&2; exit 1; }; \
	tfe_https_port="$${TFE_HTTPS_PORT:-443}"; \
	case "$$tfe_https_port" in \
		''|*[!0-9]*) printf 'TFE_HTTPS_PORT must be a numeric host port in %s\n' "$(TFE_ENV_FILE)" >&2; exit 1 ;; \
	esac; \
	active_socket="$$( $(PODMAN_ACTIVE_SOCKET_CMD) )"; \
	detected_rootful_socket="$$( $(PODMAN_MACHINE_ROOTFUL_SOCKET_CMD) )"; \
	detected_rootless_socket="$$( $(PODMAN_MACHINE_ROOTLESS_SOCKET_CMD) )"; \
	active_rootless="$$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"; \
	detected_guest_socket="$$detected_rootful_socket"; \
	if [ -z "$$detected_guest_socket" ]; then \
		detected_guest_socket="$$detected_rootless_socket"; \
	fi; \
	detected_host_socket="$$( $(PODMAN_MACHINE_HOST_SOCKET_CMD) )"; \
	if [ -n "$$detected_host_socket" ] && [ "$$PODMAN_SOCKET" = "$$detected_host_socket" ]; then \
		printf 'PODMAN_SOCKET points to the macOS host-side Podman machine socket at %s\n' "$$PODMAN_SOCKET" >&2; \
		printf 'That socket exists, but Podman cannot bind-mount it into the TFE container.\n' >&2; \
		if [ -n "$$active_socket" ]; then \
			printf 'Set PODMAN_SOCKET=%s in %s and retry.\n' "$$active_socket" "$(TFE_ENV_FILE)" >&2; \
		elif [ -n "$$detected_guest_socket" ]; then \
			printf 'Set PODMAN_SOCKET=%s in %s and retry.\n' "$$detected_guest_socket" "$(TFE_ENV_FILE)" >&2; \
		else \
			printf 'Run `make podman-socket` to print a guest-side socket path and retry.\n' >&2; \
		fi; \
		exit 1; \
	fi; \
	if [ -n "$$active_socket" ] && [ "$$PODMAN_SOCKET" != "$$active_socket" ]; then \
		printf 'PODMAN_SOCKET=%s does not match the active Podman connection socket %s\n' "$$PODMAN_SOCKET" "$$active_socket" >&2; \
		printf 'Set PODMAN_SOCKET=%s in %s, or switch Podman connections and rerun `make podman-socket`.\n' "$$active_socket" "$(TFE_ENV_FILE)" >&2; \
		exit 1; \
	fi; \
	socket_ok=0; \
	if [ -n "$$active_socket" ] && [ "$$PODMAN_SOCKET" = "$$active_socket" ]; then \
		socket_ok=1; \
	elif [ -n "$$detected_guest_socket" ] && [ "$$PODMAN_SOCKET" = "$$detected_guest_socket" ]; then \
		socket_ok=1; \
	elif test -S "$$PODMAN_SOCKET"; then \
		socket_ok=1; \
	elif podman machine ssh "test -S '$$PODMAN_SOCKET'" >/dev/null 2>&1; then \
		socket_ok=1; \
	fi; \
	if [ "$$socket_ok" -ne 1 ]; then \
		printf 'Podman socket not found at %s\n' "$$PODMAN_SOCKET" >&2; \
		if [ -n "$$detected_guest_socket" ]; then \
			printf 'For Podman machine on macOS, set PODMAN_SOCKET=%s in %s and retry.\n' "$$detected_guest_socket" "$(TFE_ENV_FILE)" >&2; \
		elif [ -n "$$detected_host_socket" ]; then \
			printf 'Podman machine reported a host-side socket at %s, but that path is not mountable into containers.\n' "$$detected_host_socket" >&2; \
			printf 'Run `make podman-socket` to print a guest-side socket path that TFE can use.\n' >&2; \
		else \
			printf 'If you want a fixed local socket path, start one with:\n' >&2; \
			printf '  podman system service --time=0 unix:///tmp/podman.sock\n' >&2; \
		fi; \
		exit 1; \
	fi; \
	if [ "$$active_rootless" = "true" ]; then \
		printf 'The active Podman connection is rootless (%s).\n' "$$active_socket" >&2; \
		printf 'Terraform Enterprise bundles Vault, and rootless Podman cannot grant the memlock limit Vault needs to boot.\n' >&2; \
		if [ -n "$$detected_rootful_socket" ]; then \
			printf 'Switch Podman to a rootful connection, set PODMAN_SOCKET=%s in %s, and rerun `make podman-up`.\n' "$$detected_rootful_socket" "$(TFE_ENV_FILE)" >&2; \
			printf 'Use `podman system connection list` to find the rootful connection for your machine.\n' >&2; \
		else \
			printf 'Use a rootful Podman service/socket for this demo instead of a rootless connection.\n' >&2; \
		fi; \
		exit 1; \
	fi; \
	if [ -n "$$detected_guest_socket" ] || [ -n "$$detected_host_socket" ]; then \
		unprivileged_port_start="$$( $(PODMAN_MACHINE_PORT_THRESHOLD_CMD) )"; \
		if [ -n "$$unprivileged_port_start" ] && [ "$$tfe_https_port" -lt 1024 ] && [ "$$unprivileged_port_start" -gt "$$tfe_https_port" ]; then \
			printf 'Rootless Podman machine cannot publish host port %s because net.ipv4.ip_unprivileged_port_start is %s.\n' "$$tfe_https_port" "$$unprivileged_port_start" >&2; \
			printf 'Run `make podman-machine-allow-443` to lower the threshold inside the Podman machine, or set TFE_HTTPS_PORT=8443 in %s if you need an unprivileged fallback.\n' "$(TFE_ENV_FILE)" >&2; \
			exit 1; \
		fi; \
	fi; \
	exit 0

podman-socket:
	@active_socket="$$( $(PODMAN_ACTIVE_SOCKET_CMD) )"; \
	detected_rootful_socket="$$( $(PODMAN_MACHINE_ROOTFUL_SOCKET_CMD) )"; \
	detected_rootless_socket="$$( $(PODMAN_MACHINE_ROOTLESS_SOCKET_CMD) )"; \
	detected_guest_socket="$$detected_rootful_socket"; \
	if [ -z "$$detected_guest_socket" ]; then \
		detected_guest_socket="$$detected_rootless_socket"; \
	fi; \
	if [ -n "$$active_socket" ]; then \
		printf '%s\n' "$$active_socket"; \
	elif [ -n "$$detected_guest_socket" ]; then \
		printf '%s\n' "$$detected_guest_socket"; \
	elif test -S /tmp/podman.sock; then \
		printf '%s\n' /tmp/podman.sock; \
	else \
		detected_host_socket="$$( $(PODMAN_MACHINE_HOST_SOCKET_CMD) )"; \
		printf 'Unable to determine a live Podman socket path.\n' >&2; \
		if [ -n "$$detected_host_socket" ]; then \
			printf 'Podman machine reported a host-side socket at %s, but that path is not mountable into containers.\n' "$$detected_host_socket" >&2; \
			printf 'Start Podman and rerun `make podman-socket`; it should print the guest-side socket for the active connection.\n' >&2; \
		else \
			printf 'On macOS, start Podman and rerun: make podman-socket\n' >&2; \
			printf 'On Linux, you can expose /tmp/podman.sock with: podman system service --time=0 unix:///tmp/podman.sock\n' >&2; \
		fi; \
		exit 1; \
	fi

podman-machine-allow-443:
	@threshold="$$( $(PODMAN_MACHINE_PORT_THRESHOLD_CMD) )"; \
	test -n "$$threshold" || { printf 'Unable to read net.ipv4.ip_unprivileged_port_start from the active Podman machine.\n' >&2; printf 'Start Podman machine and make sure the active Podman connection points to it, then retry.\n' >&2; exit 1; }; \
	if [ "$$threshold" -le 443 ]; then \
		printf 'Podman machine already allows host port 443 (net.ipv4.ip_unprivileged_port_start=%s).\n' "$$threshold"; \
	else \
		podman machine ssh "sudo install -d /etc/sysctl.d >/dev/null 2>&1 && printf 'net.ipv4.ip_unprivileged_port_start=443\n' | sudo tee /etc/sysctl.d/60-tfe-demo-unprivileged-port-443.conf >/dev/null && sudo sysctl -w net.ipv4.ip_unprivileged_port_start=443 >/dev/null"; \
		updated_threshold="$$( $(PODMAN_MACHINE_PORT_THRESHOLD_CMD) )"; \
		if [ -z "$$updated_threshold" ] || [ "$$updated_threshold" -gt 443 ]; then \
			printf 'Failed to lower net.ipv4.ip_unprivileged_port_start; current value is %s\n' "$$updated_threshold" >&2; \
			exit 1; \
		fi; \
		printf 'Podman machine now allows host port 443 (net.ipv4.ip_unprivileged_port_start=%s).\n' "$$updated_threshold"; \
	fi

generate-certs:
	@./scripts/generate-dev-certs.sh

podman-up: check-tfe-env
	@$(PODMAN_COMPOSE) --env-file $(TFE_ENV_FILE) -f $(TFE_COMPOSE_FILE) up -d

podman-down: check-tfe-env
	@$(PODMAN_COMPOSE) --env-file $(TFE_ENV_FILE) -f $(TFE_COMPOSE_FILE) down

podman-logs: check-tfe-env
	@$(PODMAN_COMPOSE) --env-file $(TFE_ENV_FILE) -f $(TFE_COMPOSE_FILE) logs -f tfe postgres minio

tfe-health: check-tfe-env
	@$(PODMAN_COMPOSE) --env-file $(TFE_ENV_FILE) -f $(TFE_COMPOSE_FILE) exec tfe tfe-health-check-status

terraform-fmt:
	@terraform fmt -recursive terraform

terraform-validate:
	@terraform -chdir=$(DEMO_TERRAFORM_DIR) init -backend=false
	@terraform -chdir=$(DEMO_TERRAFORM_DIR) validate

sentinel-test:
	@sentinel test $(DEMO_SENTINEL_POLICY)

mcp-health:
	@curl --fail --silent http://127.0.0.1:8080/health

demo-validate: terraform-fmt terraform-validate sentinel-test

.PHONY: detect-host-alias-ip
detect-host-alias-ip:
	@printf 'Detecting correct TFE_HOST_ALIAS_IP value...\n'
	@if command -v podman >/dev/null 2>&1; then \
		if podman machine list 2>/dev/null | grep -q "Currently running"; then \
			printf 'Detected macOS Podman machine\n'; \
			IP=$$(podman machine ssh "ip addr show host0 2>/dev/null | grep 'inet ' | awk '{print \$$2}' | cut -d/ -f1" 2>/dev/null || echo "192.168.127.254"); \
			printf 'Recommended TFE_HOST_ALIAS_IP: %s\n' "$$IP"; \
		else \
			printf 'Detected Linux or non-machine Podman\n'; \
			IP=$$(podman network inspect podman 2>/dev/null | grep -oE '"gateway":\s*"[0-9.]+"' | grep -oE '[0-9.]+' | head -1 || echo "10.88.0.1"); \
			printf 'Recommended TFE_HOST_ALIAS_IP: %s\n' "$$IP"; \
		fi; \
	else \
		printf 'Podman not found. Please install Podman first.\n' >&2; \
		exit 1; \
	fi

.PHONY: runtime companion restart performance volume demo-akinator demo-elderly prep-elderly-negative reset

DEMO_ARGS ?=
VOLUME ?= 100
PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

runtime:
	@./scripts/ensure_gemma.sh

companion:
	@./scripts/run_companion.sh

restart:
	@./scripts/restart_remote_service.sh

performance:
	@$(PYTHON) scripts/test_performance.py

volume:
	@$(PYTHON) scripts/set_volume.py $(VOLUME)

demo-akinator: runtime
	@$(PYTHON) main.py --mode akinator $(DEMO_ARGS)

demo-elderly: runtime
	@$(PYTHON) main.py --mode elderly --text \
		--request 'Please find the Audio-Technica speaker' \
		--target 'small white oval Audio-Technica tabletop speaker' $(DEMO_ARGS)

prep-elderly-negative: runtime
	@$(PYTHON) scripts/prep_elderly_negative.py

reset:
	@$(PYTHON) -c 'from camera.obsbot import look_center; print("camera_center:", look_center())'
	@mkdir -p logs captures
	@echo 'session_state: fresh (each demo starts a new bounded session; logs retained)'

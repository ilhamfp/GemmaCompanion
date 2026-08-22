.PHONY: runtime demo-akinator demo-elderly prep-elderly-negative reset

DEMO_ARGS ?=

runtime:
	@./scripts/ensure_gemma.sh

demo-akinator: runtime
	@python3 main.py --mode akinator $(DEMO_ARGS)

demo-elderly: runtime
	@python3 main.py --mode elderly --text \
		--request 'Please find the Audio-Technica speaker' \
		--target 'small white oval Audio-Technica tabletop speaker' $(DEMO_ARGS)

prep-elderly-negative: runtime
	@python3 scripts/prep_elderly_negative.py

reset:
	@python3 -c 'from camera.obsbot import look_center; print("camera_center:", look_center())'
	@mkdir -p logs captures
	@echo 'session_state: fresh (each demo starts a new bounded session; logs retained)'

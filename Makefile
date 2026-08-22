.PHONY: runtime demo-akinator demo-elderly reset

DEMO_ARGS ?=

runtime:
	@./scripts/ensure_gemma.sh

demo-akinator: runtime
	@python3 main.py --mode akinator $(DEMO_ARGS)

demo-elderly: runtime
	@python3 main.py --mode elderly $(DEMO_ARGS)

reset:
	@python3 -c 'from camera.obsbot import look_center; print("camera_center:", look_center())'
	@mkdir -p logs captures

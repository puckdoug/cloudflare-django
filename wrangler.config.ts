import { defineWranglerConfig } from "wrangler/experimental-config";

export default defineWranglerConfig({
	pythonModules: {
		exclude: [
			"**/*.pyc",
			"**/__pycache__",
			"**/*.po",
			"**/*.css",
			"**/*.js",
			"**/*.svg",
			"**/*.png",
			"**/*.jpg",
		],
	},
	build: {
		command:
			"WORKERS_CI=1 uv run --locked python src/manage.py collectstatic --noinput",
	},
	assetsDirectory: "./staticfiles",
});

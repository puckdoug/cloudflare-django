import { bindings, defineConfig, exports } from "cf/config";

export default defineConfig({
	worker: {
		name: "cloudflare-django",
		compatibilityDate: "2026-03-08",
		compatibilityFlags: ["python_workers"],
		entrypoint: "src/index.py",
		domains: ["dj.heroic.ch"],
		observability: { enabled: true },
		exports: {
			DjangoDO: exports.durableObject({ storage: "sqlite" }),
		},
		env: {
			DO_STORAGE: bindings.durableObject({
				worker: "cloudflare-django",
				exportName: "DjangoDO",
			}),
			BOOTSTRAP_ENABLED: bindings.text("1"),
			DJANGO_SECRET_KEY: bindings.secret(),
			BOOTSTRAP_TOKEN: bindings.secret(),
			DJANGO_SUPERUSER_USERNAME: bindings.secret(),
			DJANGO_SUPERUSER_EMAIL: bindings.secret(),
			DJANGO_SUPERUSER_PASSWORD: bindings.secret(),
		},
	},
});

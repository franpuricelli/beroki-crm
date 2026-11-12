import { handleKaironWebhook, upstashDedupe } from "../../src/receiver/handler.js";

export function POST(request: Request) {
	const env = process.env;
	const kvUrl = env.KV_REST_API_URL ?? env.UPSTASH_REDIS_REST_URL;
	const kvToken = env.KV_REST_API_TOKEN ?? env.UPSTASH_REDIS_REST_TOKEN;
	return handleKaironWebhook(request, {
		secret: env.KAIRON_WEBHOOK_SECRET,
		dedupe: kvUrl && kvToken ? upstashDedupe(kvUrl, kvToken) : undefined,
		fire: env.ROUTINE_FIRE_URL && env.ROUTINE_FIRE_TOKEN ? { url: env.ROUTINE_FIRE_URL, token: env.ROUTINE_FIRE_TOKEN } : undefined,
	});
}

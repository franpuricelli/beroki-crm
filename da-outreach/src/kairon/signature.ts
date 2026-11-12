import { createHmac, timingSafeEqual } from "node:crypto";

/** Verifica `Kairon-Signature: t=…,v1=…` (HMAC-SHA256 de "{t}.{raw body}" con el secreto whsec_ completo). */
export function verifyKaironSignature(rawBody: string, header: string | null, secret: string, toleranceSeconds = 300, now = Date.now()): boolean {
	const parts: Record<string, string> = {};
	for (const piece of String(header ?? "").split(",")) {
		const at = piece.indexOf("=");
		if (at > 0) parts[piece.slice(0, at).trim()] ??= piece.slice(at + 1).trim();
	}
	const t = Number(parts.t);
	if (!Number.isInteger(t) || !parts.v1) return false;
	if (Math.abs(now / 1000 - t) > toleranceSeconds) return false;
	const expected = Buffer.from(createHmac("sha256", secret).update(`${t}.${rawBody}`).digest("hex"));
	const got = Buffer.from(parts.v1);
	return got.length === expected.length && timingSafeEqual(got, expected);
}

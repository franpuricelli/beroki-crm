import { timingSafeEqual } from "node:crypto";

export function bearerMatches(
	request: Request,
	secret: string | undefined,
): boolean {
	const expected = secret?.trim();
	if (!expected) return false;
	const header = request.headers.get("authorization");
	if (!header?.startsWith("Bearer ")) return false;
	const candidate = Buffer.from(header.slice("Bearer ".length));
	const wanted = Buffer.from(expected);
	if (candidate.length !== wanted.length) return false;

	return timingSafeEqual(candidate, wanted);
}

import "./env";
import crypto from "node:crypto";
import nodemailer from "nodemailer";
import { CONTACT_EMAIL } from "./info";

// Ported from the Flask app's contact form (app.py): the same rotation
// challenge, the same honeypot, the same limits, the same error strings.
export const CONTACT_FORWARD_TO = process.env.CONTACT_FORWARD_TO ?? "test.noreply909@gmail.com";
export const CONTACT_FROM_EMAIL = process.env.CONTACT_FROM_EMAIL ?? CONTACT_EMAIL;
const SMTP_HOST = process.env.CONTACT_SMTP_HOST ?? "";
const SMTP_PORT = Number(process.env.CONTACT_SMTP_PORT ?? "587");
const SMTP_USER = process.env.CONTACT_SMTP_USER ?? "";
const SMTP_PASSWORD = process.env.CONTACT_SMTP_PASSWORD ?? "";
const SMTP_USE_TLS = !["0", "false", "no"].includes((process.env.CONTACT_SMTP_USE_TLS ?? "true").toLowerCase());
const SMTP_TLS_VERIFY = !["0", "false", "no"].includes((process.env.CONTACT_SMTP_TLS_VERIFY ?? "true").toLowerCase());
const RATE_LIMIT_SECONDS = Number(process.env.CONTACT_RATE_LIMIT_SECONDS ?? "60");
const MIN_SUBMIT_SECONDS = Number(process.env.CONTACT_MIN_SUBMIT_SECONDS ?? "3");
const ROTATION_TOLERANCE = Number(process.env.CONTACT_ROTATION_TOLERANCE ?? "8");

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Flask kept the challenge in its signed session cookie, so the server stores
// nothing between the two requests. Same here — a signed cookie rather than a
// session store, which also means the blue/green pair can hand the form back
// and forth without sharing state. Falls back to a per-process key exactly
// like the old app's `secrets.token_hex(32)` default; set CONTACT_SECRET (or
// SECRET_KEY) so a restart mid-form doesn't invalidate it.
const CHALLENGE_SECRET = process.env.CONTACT_SECRET
  ?? process.env.SECRET_KEY
  ?? process.env.FLASK_SECRET_KEY
  ?? crypto.randomBytes(32).toString("hex");

export const CHALLENGE_COOKIE = "contact_challenge";
export const CHALLENGE_MAX_AGE_SECONDS = 60 * 30;

export type Challenge = {
  /** Degrees the puzzle piece starts rotated by. */
  rotationStart: number;
  /** Rotation that brings it back to upright. */
  answer: number;
  token: string;
  startedAt: number;
};

export type ContactValues = { name: string; email: string; subject: string; message: string };

export const EMPTY_VALUES: ContactValues = { name: "", email: "", subject: "", message: "" };

function sign(payload: string): string {
  return crypto.createHmac("sha256", CHALLENGE_SECRET).update(payload).digest("base64url");
}

export function newChallenge(): Challenge {
  const rotationStart = (crypto.randomInt(23) + 1) * 15;
  return {
    rotationStart,
    answer: (360 - rotationStart) % 360,
    token: crypto.randomBytes(18).toString("base64url"),
    startedAt: Date.now() / 1000,
  };
}

export function sealChallenge(challenge: Challenge): string {
  const payload = Buffer.from(JSON.stringify(challenge)).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

export function openChallenge(cookieValue?: string | null): Challenge | null {
  if (!cookieValue) return null;
  const [payload, signature] = cookieValue.split(".");
  if (!payload || !signature) return null;
  const expected = sign(payload);
  // Same length before comparing, or timingSafeEqual throws instead of
  // returning false.
  if (signature.length !== expected.length) return null;
  if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf-8"));
    if (typeof parsed?.answer !== "number" || typeof parsed?.token !== "string") return null;
    return parsed as Challenge;
  } catch {
    return null;
  }
}

export function angularDistance(left: number, right: number): number {
  return Math.abs(((left - right + 180) % 360 + 360) % 360 - 180);
}

function equalTokens(left: string, right: string): boolean {
  if (!left || !right || left.length !== right.length) return false;
  return crypto.timingSafeEqual(Buffer.from(left), Buffer.from(right));
}

export function validateSubmission(form: FormData, challenge: Challenge | null): { errors: string[]; values: ContactValues } {
  const read = (field: string) => String(form.get(field) ?? "").trim();
  const values: ContactValues = {
    name: read("name"),
    email: read("email"),
    subject: read("subject"),
    message: read("message"),
  };
  const errors: string[] = [];

  if (read("website")) errors.push("Spam check failed.");
  if (!challenge || !equalTokens(read("form_token"), challenge.token)) {
    errors.push("The form expired. Please try again.");
  }
  if (challenge && Date.now() / 1000 - challenge.startedAt < MIN_SUBMIT_SECONDS) {
    errors.push("Please take a moment before submitting the form.");
  }
  const rotationValue = Number.parseInt(read("rotation_response"), 10);
  if (!challenge || !Number.isFinite(rotationValue) || angularDistance(rotationValue, challenge.answer) > ROTATION_TOLERANCE) {
    errors.push("The rotation check is incorrect.");
  }
  if (values.name.length < 2 || values.name.length > 80) errors.push("Name must be between 2 and 80 characters.");
  if (!EMAIL_RE.test(values.email) || values.email.length > 120) errors.push("Enter a valid email address.");
  if (values.subject.length < 3 || values.subject.length > 140) errors.push("Subject must be between 3 and 140 characters.");
  if (values.message.length < 20 || values.message.length > 4000) errors.push("Message must be between 20 and 4000 characters.");

  return { errors, values };
}

// Per-process, like the old app's module-level dict: enough to stop a form
// being hammered from one address, and it costs nothing to keep.
const rateLimit = new Map<string, number>();

export function isRateLimited(ip: string): boolean {
  const last = rateLimit.get(ip) ?? 0;
  return Date.now() / 1000 - last < RATE_LIMIT_SECONDS;
}

export function markSubmitted(ip: string) {
  rateLimit.set(ip, Date.now() / 1000);
}

// Behind Cloudflare and nginx the real address arrives in a header; the socket
// address is the fallback (the old app's `request.remote_addr`), and it also
// keeps the rate limiter from filing every direct visitor under one empty key.
export function clientIp(request: Request, socketAddress?: string): string {
  const forwarded = request.headers.get("cf-connecting-ip")
    ?? request.headers.get("x-forwarded-for")
    ?? "";
  return forwarded.split(",")[0].trim() || (socketAddress ?? "").trim() || "unknown";
}

export async function sendContactEmail(data: ContactValues, meta: { ip: string; pageUrl: string }): Promise<void> {
  if (!SMTP_HOST) throw new Error("CONTACT_SMTP_HOST is not configured");

  const transport = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    // 465 is implicit TLS; every other port starts plaintext and upgrades
    // with STARTTLS, which is what CONTACT_SMTP_USE_TLS asked for.
    secure: SMTP_PORT === 465,
    requireTLS: SMTP_USE_TLS && SMTP_PORT !== 465,
    tls: { rejectUnauthorized: SMTP_TLS_VERIFY },
    auth: SMTP_USER || SMTP_PASSWORD ? { user: SMTP_USER, pass: SMTP_PASSWORD } : undefined,
    connectionTimeout: 15000,
    greetingTimeout: 15000,
  });

  await transport.sendMail({
    from: CONTACT_FROM_EMAIL,
    to: CONTACT_FORWARD_TO,
    replyTo: data.email,
    subject: `ExchangeHub contact: ${data.subject}`,
    text: [
      "New ExchangeHub contact form submission",
      "",
      `Name: ${data.name}`,
      `Email: ${data.email}`,
      `IP: ${meta.ip}`,
      `Page: ${meta.pageUrl}`,
      "",
      data.message,
    ].join("\n"),
  });
}

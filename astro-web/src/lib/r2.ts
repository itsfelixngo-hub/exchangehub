import "./env";
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

const TRUTHY = new Set(["1", "true", "yes", "on"]);

function truthy(name: string, fallback = ""): boolean {
  return TRUTHY.has((process.env[name] ?? fallback).trim().toLowerCase());
}

export function r2Enabled(): boolean {
  return truthy("R2_ENABLED");
}

export function localStorageEnabled(): boolean {
  return truthy("LOCAL_STORAGE_ENABLED", "true");
}

function r2Prefix(): string {
  return (process.env.R2_PREFIX ?? "").trim().replace(/^\/+|\/+$/g, "");
}

function objectKey(relativePath: string): string {
  const normalized = relativePath.replace(/^\/+/, "");
  const prefix = r2Prefix();
  return prefix ? `${prefix}/${normalized}` : normalized;
}

function getEndpoint(): string {
  const explicit = (process.env.R2_ENDPOINT_URL ?? "").trim();
  if (explicit) return explicit.replace(/\/+$/, "");
  const accountId = (process.env.R2_ACCOUNT_ID ?? "").trim();
  if (!accountId) throw new Error("Set R2_ENDPOINT_URL or R2_ACCOUNT_ID for Cloudflare R2 access");
  return `https://${accountId}.r2.cloudflarestorage.com`;
}

let client: S3Client | null = null;

function getClient(): S3Client {
  if (client) return client;
  const accessKeyId = (process.env.R2_ACCESS_KEY_ID ?? "").trim();
  const secretAccessKey = (process.env.R2_SECRET_ACCESS_KEY ?? "").trim();
  if (!accessKeyId || !secretAccessKey) {
    throw new Error("Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY for Cloudflare R2 access");
  }
  client = new S3Client({
    endpoint: getEndpoint(),
    region: process.env.R2_REGION ?? "auto",
    credentials: { accessKeyId, secretAccessKey },
  });
  return client;
}

async function streamToString(body: unknown): Promise<string> {
  const stream = body as AsyncIterable<Uint8Array>;
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf-8");
}

export async function getBytes(relativePath: string): Promise<string | null> {
  const bucket = (process.env.R2_BUCKET ?? "").trim();
  if (!bucket) throw new Error("Set R2_BUCKET for Cloudflare R2 access");
  try {
    const result = await getClient().send(
      new GetObjectCommand({ Bucket: bucket, Key: objectKey(relativePath) }),
    );
    return streamToString(result.Body);
  } catch (err: any) {
    const code = err?.name || err?.Code;
    if (code === "NoSuchKey" || code === "NotFound") return null;
    throw err;
  }
}

export async function getJson<T = unknown>(relativePath: string): Promise<T | null> {
  const text = await getBytes(relativePath);
  if (text === null) return null;
  return JSON.parse(text) as T;
}

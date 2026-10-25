import { z } from "zod";

declare global {
  interface ImportMeta {
    readonly env: Record<string, string | boolean | undefined>;
  }
}

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().url(),
  VITE_WS_BASE_URL: z.string().min(1),
  VITE_STRIPE_PUBLISHABLE_KEY: z.string().min(1),
});

export type FrontendEnv = z.infer<typeof envSchema>;

export function parseEnv(
  source: Record<string, string | boolean | undefined>,
): FrontendEnv {
  return envSchema.parse(source);
}

export const env: FrontendEnv = parseEnv(import.meta.env);

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables');
}

export const ACCESS_TOKEN_COOKIE = 'ai_holdings_access_token';
export const REFRESH_TOKEN_COOKIE = 'ai_holdings_refresh_token';

export function createBrowserClient() {
  return createClient(supabaseUrl, supabaseAnonKey);
}

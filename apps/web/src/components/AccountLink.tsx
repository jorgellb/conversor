"use client";

import Link from "next/link";

import { authClient } from "@/lib/auth-client";

export function AccountLink({ labels, accountHref, signInHref }: { locale: string; labels: { account: string; signIn: string }; accountHref: string; signInHref: string }) {
  const { data } = authClient.useSession();
  return data?.user ? <Link href={accountHref}>{labels.account}</Link> : <Link href={signInHref}>{labels.signIn}</Link>;
}

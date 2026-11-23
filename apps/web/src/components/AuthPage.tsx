"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { authClient } from "@/lib/auth-client";
import { getConfig } from "@/lib/runtime";
import { HeroArt } from "./art/HeroArt";

export function AuthPage({ mode }: { mode: "signIn" | "signUp" }) {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "busy" | "error" | "check" | "magic">("idle");
  const [google, setGoogle] = useState(false);
  const account = `/${locale}/${locale === "en" ? "account" : "cuenta"}`;
  useEffect(() => {
    void getConfig().then((c) => setGoogle(c.googleLogin));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus("busy");
    const res = mode === "signIn"
      ? await authClient.signIn.email({ email, password, callbackURL: account })
      : await authClient.signUp.email({ email, password, name: name || email.split("@")[0], callbackURL: account });
    if (res.error) setStatus("error");
    else if (mode === "signUp") setStatus("check");
    else router.push(account);
  };
  const magic = async () => {
    if (!email) return;
    setStatus("busy");
    const res = await authClient.signIn.magicLink({ email, callbackURL: account });
    setStatus(res.error ? "error" : "magic");
  };

  return (
    <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-[1fr_1.1fr]">
    <div className="card flex w-full max-w-md flex-col gap-4 justify-self-center p-6 sm:p-8" style={{ boxShadow: "var(--shadow-lg)" }}>
      <h1 className="text-3xl font-bold">{mode === "signIn" ? t("signInTitle") : t("signUpTitle")}</h1>
      <form className="flex flex-col gap-3" onSubmit={(e) => void submit(e)}>
        {mode === "signUp" && (
          <label className="flex flex-col gap-1">{t("name")}<input className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
        )}
        <label className="flex flex-col gap-1">{t("email")}<input className="field" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label className="flex flex-col gap-1">{t("password")}
          <input className="field" type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signIn" ? "current-password" : "new-password"} aria-describedby="pista-contrasena" />
          <span id="pista-contrasena" className="muted text-xs">{t("passwordHint")}</span>
        </label>
        <button className="btn" type="submit" disabled={status === "busy"}>{mode === "signIn" ? t("submitSignIn") : t("submitSignUp")}</button>
      </form>
      {mode === "signIn" && <button type="button" className="btn-secondary btn" onClick={() => void magic()}>{t("magic")}</button>}
      {google && (
        <button type="button" className="btn-secondary btn" onClick={() => void authClient.signIn.social({ provider: "google", callbackURL: account })}>{t("google")}</button>
      )}
      <div role="status" aria-live="polite">
        {status === "error" && <p className="text-red-600">{t("error")}</p>}
        {status === "check" && <p>{t("checkEmail")}</p>}
        {status === "magic" && <p>{t("magicSent")}</p>}
      </div>
      <p className="muted text-sm">
        {mode === "signIn" ? t("noAccount") : t("haveAccount")}{" "}
        <Link className="underline" href={`/${locale}/${mode === "signIn" ? (locale === "en" ? "sign-up" : "registro") : (locale === "en" ? "sign-in" : "entrar")}`}>
          {mode === "signIn" ? t("submitSignUp") : t("submitSignIn")}
        </Link>
      </p>
    </div>
    <div className="hidden lg:block" aria-hidden="true"><HeroArt className="h-auto w-full" /></div>
    </div>
  );
}

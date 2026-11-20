"use client";

// Controles del panel lateral de los editores del collage y de las tarjetas (crear-collage y crear-tarjeta).
import { useId, type ReactNode } from "react";

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card flex flex-col gap-3 p-4">
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function Range({ label, value, min, max, step = 1, onChange }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <span className="flex justify-between"><label htmlFor={id}>{label}</label><span className="muted tabular-nums">{Math.round(value * 100) / 100}</span></span>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

export function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="color" value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#000000"} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-8 w-12" />
    </div>
  );
}

export function Select<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="field" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </div>
  );
}

export function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = useId();
  return (
    <div className="flex items-center gap-2 text-sm">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

export function NumberInput({ label, value, min, max, step = 1, onChange }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  const id = useId();
  const round = (v: number) => Math.round(v / step) * step;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="number" className="field" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Math.max(min, Math.min(max, round(Number(e.target.value)) || min)))} />
    </div>
  );
}

export function TextInput({ label, value, maxLength, onChange }: { label: string; value: string; maxLength: number; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="text" className="field" maxLength={maxLength} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function TextArea({ label, value, maxLength, onChange }: { label: string; value: string; maxLength: number; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} className="field" rows={3} maxLength={maxLength} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

import {
  useEffect,
  type ButtonHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return <button className={`btn ${variant} ${className}`.trim()} {...props} />;
}

export function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error ? <small>{error}</small> : null}
    </label>
  );
}

export function Banner({
  tone = "error",
  children,
}: {
  tone?: "error" | "ok" | "info";
  children: ReactNode;
}) {
  return (
    <p className={`banner ${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return <p className="loading">{label}</p>;
}

export function Page({
  title,
  lede,
  actions,
  children,
}: {
  title: string;
  lede?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1>{title}</h1>
          {lede ? <p>{lede}</p> : null}
        </div>
        <div className="page-actions">{actions}</div>
      </header>
      {children}
    </section>
  );
}

export function Pager({
  page,
  count,
  pageSize,
  onPage,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return (
    <div className="pager">
      <Button variant="ghost" type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Anterior
      </Button>
      <span>
        {page} / {pages}
      </span>
      <Button
        variant="ghost"
        type="button"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Siguiente
      </Button>
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-back" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function SecretReveal({
  title,
  secret,
  hint,
}: {
  title: string;
  secret: string;
  hint: string;
}) {
  return (
    <div className="secret" role="status">
      <strong>{title}</strong>
      <code>{secret}</code>
      <div className="row-actions">
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            void navigator.clipboard?.writeText(secret);
          }}
        >
          Copiar
        </Button>
      </div>
      <p>{hint}</p>
    </div>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: "ok" | "off" | "warn" | "neutral";
  children: ReactNode;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function SelectField(
  props: SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string },
) {
  const { label, error, children, ...rest } = props;
  return (
    <Field label={label} error={error}>
      <select {...rest}>{children}</select>
    </Field>
  );
}

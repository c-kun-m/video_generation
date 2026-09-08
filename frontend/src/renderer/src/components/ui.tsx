import { useEffect, useRef, type ReactNode } from "react";
import { BridgeError } from "../shared/request";
import s from "../App.module.css";

export function Icon({
  name,
  size = 20,
}: {
  name:
    | "grid"
    | "plus"
    | "arrow"
    | "settings"
    | "film"
    | "archive"
    | "check"
    | "refresh";
  size?: number;
}) {
  const paths = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    settings: (
      <>
        <path d="M4 7h16M4 17h16" />
        <circle cx="9" cy="7" r="3" />
        <circle cx="15" cy="17" r="3" />
      </>
    ),
    film: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="3" />
        <path d="M8 4v16M16 4v16M3 9h5m-5 6h5m8-6h5m-5 6h5" />
      </>
    ),
    archive: (
      <>
        <rect x="3" y="3" width="18" height="5" rx="1" />
        <path d="M5 8v12h14V8M10 12h4" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    refresh: (
      <>
        <path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
export function ErrorBox({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div role="alert" className={s.error}>
      {error.message}
      {error instanceof BridgeError && error.detail.trace_id && (
        <small>请求编号 {error.detail.trace_id}</small>
      )}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog ref={ref} className={s.modal} onCancel={close} aria-label={title}>
      <div className={s.modalHead}>
        <h2>{title}</h2>
        <button
          onClick={close}
          className={s.iconButton}
          aria-label="关闭对话框"
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
export const date = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

export function Loading() {
  return (
    <div className={s.loading} role="status">
      <div className={s.spinner} />
      正在读取工作空间…
    </div>
  );
}

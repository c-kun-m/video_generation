import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ContentKind, Schema } from "../../../../shared/bridge";
import { ContentEditor } from "./ContentEditor";
import { ProductionPanel } from "./ProductionPanel";
import { contentNames, reviewNames, unwrap } from "./shared";
import s from "./Workbench.module.css";

export function Workbench({
  view,
  disabled,
}: {
  view: Schema["ProjectSnapshot"];
  disabled: boolean;
}) {
  const [tab, setTab] = useState<ContentKind | "production">("brief");
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => unwrap(window.video.me()),
  });
  return (
    <section className={s.workbench} aria-label="内容创作工作台">
      <nav className={s.tabs} aria-label="创作步骤">
        {(["brief", "script", "storyboard", "production"] as const).map(
          (kind, index) => {
            const head = view.contents?.find((h) => h.entity_kind === kind);
            return (
              <button
                key={kind}
                className={tab === kind ? s.activeTab : s.tab}
                aria-current={tab === kind ? "step" : undefined}
                onClick={() => setTab(kind)}
              >
                <span>0{index + 1}</span>
                <strong>
                  {kind === "production" ? "模拟演练" : contentNames[kind]}
                </strong>
                <small>
                  {kind === "production"
                    ? "暂停 · 恢复 · 取消"
                    : head
                      ? `v${head.current.revision} · ${reviewNames[head.review_status]}`
                      : "待填写"}
                </small>
              </button>
            );
          },
        )}
      </nav>
      {tab === "production" ? (
        <ProductionPanel
          view={view}
          disabled={disabled}
          role={me.data?.role ?? "viewer"}
        />
      ) : (
        <ContentEditor
          key={`${view.project.project_id}/${tab}`}
          view={view}
          kind={tab}
          disabled={disabled}
          role={me.data?.role ?? "viewer"}
        />
      )}
    </section>
  );
}

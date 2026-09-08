import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ContentKind,
  LocalDraft,
  Schema,
} from "../../../../shared/bridge";
import { ContentFields, emptyContent, exampleContent } from "./ContentFields";
import { contentNames, displayDate, reviewNames, unwrap } from "./shared";
import s from "./Workbench.module.css";

export function ContentEditor({
  view,
  kind,
  disabled,
  role,
}: {
  view: Schema["ProjectSnapshot"];
  kind: ContentKind;
  disabled: boolean;
  role: string;
}) {
  const qc = useQueryClient();
  const project_id = view.project.project_id;
  const heads = view.contents ?? [];
  const head = heads.find((h) => h.entity_kind === kind);
  const [draft, setDraft] = useState<LocalDraft | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [localError, setLocalError] = useState("");
  const [comment, setComment] = useState("");
  const [reviewDecision, setReviewDecision] = useState<
    Schema["SubmitApproval"]["decision"] | null
  >(null);
  const [reviewTarget, setReviewTarget] = useState<typeof head>();
  const [selected, setSelected] = useState<Schema["ContentRevision"] | null>(
    null,
  );
  const [before, setBefore] = useState<number>();
  const [showHistory, setShowHistory] = useState(false);
  const canEdit =
    ["owner", "editor"].includes(role) && !view.project.archived_at;
  const canReview =
    ["owner", "reviewer"].includes(role) && !view.project.archived_at;
  useEffect(() => {
    let stopped = false;
    void unwrap(window.video.getDraft({ project_id, entity_kind: kind }))
      .then((value) => {
        if (!stopped) {
          setDraft(value);
          setLoaded(true);
        }
      })
      .catch((error) => {
        if (!stopped) {
          setLocalError(error.message);
        }
      });
    return () => {
      stopped = true;
    };
  }, [project_id, kind]);
  const payload = draft?.payload ?? head?.current.payload ?? emptyContent(kind);
  const history = useQuery({
    queryKey: ["revisions", project_id, kind, before, head?.row_version],
    queryFn: () =>
      unwrap(window.video.revisions({ project_id, entity_kind: kind, before })),
    enabled: showHistory,
  });
  const edit = (payload: Schema["SaveRevision"]["payload"]) => {
    const next: LocalDraft = {
      project_id,
      entity_kind: kind,
      base_row_version: draft?.base_row_version ?? head?.row_version ?? 0,
      payload,
      updated_at: new Date().toISOString(),
    };
    setDraft(next);
    void unwrap(window.video.saveDraft(next))
      .then(() => setLocalError(""))
      .catch((error) => setLocalError(error.message));
  };
  const save = useMutation({
    mutationFn: async () => {
      if (!draft) return;
      const submitted = draft;
      const result = await unwrap(
        window.video.saveRevision({
          project_id,
          command: {
            command_id: crypto.randomUUID(),
            entity_kind: kind,
            expected_row_version: submitted.base_row_version,
            payload: submitted.payload,
          },
        }),
      );
      await unwrap(
        window.video.deleteDraft({
          project_id,
          entity_kind: kind,
          updated_at: submitted.updated_at,
        }),
      );
      await qc.invalidateQueries({ queryKey: ["snapshot", project_id] });
      setDraft((current) =>
        current?.updated_at === submitted.updated_at ? null : current,
      );
      return result;
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["desktop"] });
      void qc.invalidateQueries({ queryKey: ["snapshot", project_id] });
    },
  });
  const review = useMutation({
    mutationFn: async () => {
      if (!reviewTarget || !reviewDecision) return;
      await unwrap(
        window.video.submitApproval({
          project_id,
          command: {
            command_id: crypto.randomUUID(),
            subject_ref: reviewTarget.current.ref,
            expected_row_version: reviewTarget.row_version,
            decision: reviewDecision,
            comment,
          },
        }),
      );
      setReviewDecision(null);
      setComment("");
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["snapshot", project_id] });
      void qc.invalidateQueries({ queryKey: ["desktop"] });
    },
  });
  const busy = disabled || !loaded || save.isPending || review.isPending;
  const conflict =
    !!draft && draft.base_row_version !== (head?.row_version ?? 0);
  const approvals = (view.approvals ?? []).filter(
    (a) => a.subject_ref.entity_kind === kind,
  );
  return (
    <div className={s.editor}>
      <div className={s.row}>
        <div>
          <h2>{contentNames[kind]}编辑</h2>
          <p className={s.hint}>
            {head
              ? `服务器版本 v${head.current.revision} · ${reviewNames[head.review_status]}`
              : "尚无服务器版本"}
            {draft ? " · 有未提交修改" : ""}
          </p>
        </div>
        <div className={s.actions}>
          <button
            className={s.secondary}
            onClick={() => setShowHistory(!showHistory)}
          >
            版本历史
          </button>
          <button
            className={s.secondary}
            disabled={busy || !canEdit || !!draft}
            onClick={() => edit(exampleContent(kind, heads))}
          >
            填充示例
          </button>
          <button
            className={s.primary}
            disabled={busy || !canEdit || !draft || conflict}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "正在保存…" : "保存新版本"}
          </button>
        </div>
      </div>
      {(localError || save.error || review.error) && (
        <div role="alert" className={s.error}>
          {localError || save.error?.message || review.error?.message}
        </div>
      )}
      {head?.upstream_outdated && (
        <p className={s.warning}>
          上游内容已更新。请重新关联当前版本、检查内容并保存后审批。
        </p>
      )}
      {conflict && (
        <div className={s.warning}>
          <strong>服务器内容或审批已更新，本地修改已保留。</strong>
          <p>请先查看最新版本，核对后可将当前修改保存为一个新版本。</p>
          <div className={s.actions}>
            <button
              className={s.secondary}
              onClick={() => setSelected(head!.current)}
            >
              查看服务器最新版本
            </button>
            <button
              className={s.secondary}
              disabled={busy}
              onClick={() => {
                const next = {
                  ...draft!,
                  base_row_version: head?.row_version ?? 0,
                  updated_at: new Date().toISOString(),
                };
                setDraft(next);
                void unwrap(window.video.saveDraft(next)).catch((e) =>
                  setLocalError(e.message),
                );
              }}
            >
              已核对，保留修改并更新保存基准
            </button>
          </div>
        </div>
      )}
      <ContentFields
        payload={payload}
        heads={heads}
        onChange={edit}
        disabled={busy || !canEdit}
      />
      <section className={s.approval}>
        <div className={s.row}>
          <div>
            <h3>版本审批</h3>
            <p className={s.hint}>
              批准只对所查看的服务器版本有效。修改后需要重新审批。
            </p>
          </div>
          <div className={s.actions}>
            {(["APPROVED", "REJECTED", "REVOKED"] as const).map((decision) => (
              <button
                className={decision === "APPROVED" ? s.primary : s.secondary}
                key={decision}
                disabled={
                  busy ||
                  !canReview ||
                  !head ||
                  !!draft ||
                  (decision === "REVOKED" && head.review_status !== "APPROVED")
                }
                onClick={() => {
                  setReviewTarget(head);
                  setReviewDecision(decision);
                  review.reset();
                }}
              >
                {
                  {
                    APPROVED: "批准当前版本",
                    REJECTED: "拒绝",
                    REVOKED: "撤销批准",
                  }[decision]
                }
              </button>
            ))}
          </div>
        </div>
        {reviewDecision && reviewTarget && (
          <div className={s.card} role="region" aria-label="确认版本审批">
            <strong>
              确认
              {
                { APPROVED: "批准", REJECTED: "拒绝", REVOKED: "撤销批准" }[
                  reviewDecision
                ]
              }
              {contentNames[kind]} v{reviewTarget.current.revision}
            </strong>
            <p className={s.hint}>
              {reviewDecision === "REVOKED"
                ? "撤销批准会阻止新批次启动；已经启动的批次仍需单独取消。"
                : "提交前请核对本次内容版本。"}
            </p>
            <label className={s.field}>
              审批意见（选填）
              <textarea
                maxLength={2000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </label>
            <div className={s.actions}>
              <button
                className={s.primary}
                disabled={busy}
                onClick={() => review.mutate()}
              >
                确认提交审批
              </button>
              <button
                className={s.secondary}
                disabled={review.isPending}
                onClick={() => setReviewDecision(null)}
              >
                返回编辑
              </button>
            </div>
          </div>
        )}
        {approvals.length > 0 && (
          <details>
            <summary>审批记录（{approvals.length}）</summary>
            {approvals.map((a) => (
              <div className={s.record} key={a.approval_id}>
                <span>
                  {reviewNames[a.decision]} · {displayDate(a.created_at)}
                </span>
                <small>
                  版本标识 {a.subject_ref.revision_id.slice(0, 8)} ·{" "}
                  {a.comment || "无附加意见"}
                </small>
              </div>
            ))}
          </details>
        )}
      </section>
      {showHistory && (
        <section className={s.card}>
          <h3>历史版本</h3>
          {history.error && <p role="alert">{history.error.message}</p>}
          {history.data?.items.map((revision) => (
            <button
              className={s.historyRow}
              key={revision.ref.revision_id}
              onClick={() => setSelected(revision)}
            >
              <strong>v{revision.revision}</strong>
              <span>{displayDate(revision.created_at)}</span>
              <span>查看内容 →</span>
            </button>
          ))}
          <div className={s.actions}>
            {before && (
              <button
                className={s.secondary}
                onClick={() => setBefore(undefined)}
              >
                最新一页
              </button>
            )}
            {history.data?.next_before && (
              <button
                className={s.secondary}
                onClick={() => setBefore(history.data!.next_before!)}
              >
                更早版本
              </button>
            )}
          </div>
        </section>
      )}
      {selected && (
        <section className={s.card} role="region" aria-label="版本内容预览">
          <div className={s.row}>
            <h3>
              {contentNames[kind]} v{selected.revision} · 只读预览
            </h3>
            <button className={s.secondary} onClick={() => setSelected(null)}>
              关闭预览
            </button>
          </div>
          <ContentFields
            payload={selected.payload}
            heads={heads}
            disabled
            onChange={() => {}}
          />
        </section>
      )}
    </div>
  );
}

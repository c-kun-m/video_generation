import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Schema } from "../../../../shared/bridge";
import { contentNames, displayDate, unwrap } from "./shared";
import s from "./Workbench.module.css";

const statusNames: Record<Schema["ProductionRun"]["status"], string> = {
  CREATED: "等待执行服务",
  PREPARING: "校验冻结输入",
  RENDERING: "模拟处理中",
  PAUSED: "已暂停",
  COMPLETED: "演练完成",
  FAILED: "执行失败",
  CANCEL_REQUESTED: "取消处理中",
  CANCELLED: "已取消",
};
const terminal = ["COMPLETED", "FAILED", "CANCELLED"];

function RunDetails({
  run_id,
  disabled,
  canControl,
}: {
  run_id: string;
  disabled: boolean;
  canControl: boolean;
}) {
  const qc = useQueryClient();
  const [commandId, setCommandId] = useState<string>();
  const query = useQuery({
    queryKey: ["run", run_id],
    queryFn: () => unwrap(window.video.run({ run_id })),
    refetchInterval: (query) =>
      query.state.data && terminal.includes(query.state.data.run.status)
        ? false
        : document.hidden
          ? 5000
          : 1000,
  });
  const receipt = useQuery({
    queryKey: ["command", commandId],
    queryFn: () => unwrap(window.video.command({ command_id: commandId! })),
    enabled: !!commandId,
    refetchInterval: (query) =>
      query.state.data?.status === "ACCEPTED" ? 1000 : false,
  });
  const control = useMutation({
    mutationFn: async (action: Schema["ControlProductionRun"]["action"]) => {
      const command_id = crypto.randomUUID();
      const result = await unwrap(
        window.video.controlRun({ run_id, command: { command_id, action } }),
      );
      setCommandId(command_id);
      return result;
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["run", run_id] });
      void qc.invalidateQueries({ queryKey: ["snapshot"] });
      void qc.invalidateQueries({ queryKey: ["desktop"] });
    },
  });
  if (!query.data)
    return (
      <p className={s.hint}>{query.error?.message ?? "正在读取演练记录…"}</p>
    );
  const { run, snapshot, steps } = query.data;
  return (
    <section className={s.card} aria-label="演练详情">
      <div className={s.row}>
        <div>
          <span className={s.badge}>模拟演练</span>
          <h3>
            {statusNames[run.status]}
            {run.pause_requested && run.status !== "PAUSED"
              ? " · 暂停处理中"
              : ""}
          </h3>
          <p className={s.hint}>
            已完成镜头 {run.completed_shots} / {run.total_shots}
          </p>
        </div>
        <div className={s.actions}>
          <button
            className={s.secondary}
            disabled={
              disabled ||
              !canControl ||
              control.isPending ||
              terminal.includes(run.status) ||
              run.status === "CANCEL_REQUESTED"
            }
            onClick={() =>
              control.mutate(
                run.pause_requested || run.status === "PAUSED"
                  ? "resume"
                  : "pause",
              )
            }
          >
            {run.pause_requested || run.status === "PAUSED"
              ? "恢复演练"
              : "暂停演练"}
          </button>
          <button
            className={s.danger}
            disabled={
              disabled ||
              !canControl ||
              control.isPending ||
              terminal.includes(run.status) ||
              run.status === "CANCEL_REQUESTED"
            }
            onClick={() => control.mutate("cancel")}
          >
            取消演练
          </button>
        </div>
      </div>
      {(query.error || control.error || run.error) && (
        <p role="alert" className={s.error}>
          {query.error?.message || control.error?.message || run.error}
        </p>
      )}
      {query.data.deliveries?.some(
        (delivery) => delivery.transport_status === "DEAD",
      ) && (
        <p role="alert" className={s.error}>
          请求多次投递失败，已保留待处理记录。请在服务恢复后检查投递器的死信记录。
        </p>
      )}
      <details>
        <summary>命令处理记录</summary>
        {query.data.deliveries?.map((delivery) => (
          <p className={s.hint} key={delivery.event_id}>
            {delivery.kind === "start" ? "启动请求" : "控制请求"} ·{" "}
            {delivery.consumed
              ? "后台已处理"
              : delivery.transport_status === "SENT"
                ? "已送达，等待后台处理"
                : delivery.transport_status === "DEAD"
                  ? "投递失败，待处理"
                  : "等待投递"}
            {delivery.error ? ` · ${delivery.error}` : ""}
          </p>
        ))}
      </details>
      {receipt.data && (
        <p className={s.hint}>
          {receipt.data.status === "ACCEPTED"
            ? "控制命令已保存，等待后台处理。"
            : receipt.data.status === "APPLIED"
              ? "后台已处理控制命令。"
              : receipt.data.error?.message}
        </p>
      )}
      <div className={s.frozen}>
        {snapshot.contents.map((content) => (
          <div key={content.ref.revision_id}>
            <span>{contentNames[content.ref.entity_kind]}</span>
            <strong>v{content.revision}</strong>
            <small>{content.ref.digest.slice(0, 12)}</small>
          </div>
        ))}
      </div>
      <p className={s.hint}>
        本批次使用以上冻结版本。编辑当前项目不会改变这些输入。
      </p>
      <ol className={s.steps}>
        {steps.map((step) => (
          <li key={step.operation_id}>
            <span>✓</span>
            <div>
              <strong>
                {step.stage === "simulation_report"
                  ? "演练报告已保存"
                  : `模拟镜头 ${steps.filter((s) => s.stage === "simulate_shot").findIndex((s) => s.operation_id === step.operation_id) + 1} 已完成`}
              </strong>
              <small>{displayDate(step.completed_at)}</small>
            </div>
          </li>
        ))}
      </ol>
      {run.status === "COMPLETED" && (
        <p className={s.success}>本次流程演练完成，未生成视频文件。</p>
      )}
      {run.status === "CREATED" && (
        <p className={s.warning}>
          启动请求已持久化。请确保 Temporal、投递器和 Worker
          正在运行；桌面关闭后请求仍会保留。
        </p>
      )}
      <details>
        <summary>批次追踪信息</summary>
        <p className={s.mono}>
          批次 {run.production_run_id}
          <br />
          快照 {run.snapshot_id}
          <br />
          Workflow {run.workflow_id}
          <br />
          阶段 {run.stage}
        </p>
      </details>
    </section>
  );
}

export function ProductionPanel({
  view,
  disabled,
  role,
}: {
  view: Schema["ProjectSnapshot"];
  disabled: boolean;
  role: string;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string>();
  const [confirm, setConfirm] = useState<Schema["StartProductionRun"] | null>(
    null,
  );
  const [confirmedVersions, setConfirmedVersions] = useState<string[]>([]);
  const heads = view.contents ?? [];
  const runs = view.production_runs ?? [];
  function refFor<K extends "brief" | "script" | "storyboard">(kind: K) {
    const ref = heads.find((h) => h.entity_kind === kind)?.current.ref;
    if (!ref || ref.entity_kind !== kind)
      throw new Error("内容引用类型不匹配，请重新加载项目。");
    return { ...ref, entity_kind: kind };
  }

  const canControl = ["owner", "editor"].includes(role);
  const ready = ["brief", "script", "storyboard"].every((kind) =>
    heads.some(
      (h) =>
        h.entity_kind === kind &&
        h.review_status === "APPROVED" &&
        !h.upstream_outdated,
    ),
  );
  const start = useMutation({
    mutationFn: async () => {
      if (!confirm) return;
      const result = await unwrap(
        window.video.startRun({
          project_id: view.project.project_id,
          command: confirm,
        }),
      );
      if (result.business_result_ref?.kind === "production_run")
        setSelected(result.business_result_ref.production_run_id);
      setConfirm(null);
    },
    onSettled: () => {
      void qc.invalidateQueries({
        queryKey: ["snapshot", view.project.project_id],
      });
      void qc.invalidateQueries({ queryKey: ["desktop"] });
    },
  });
  return (
    <div className={s.editor}>
      <div className={s.row}>
        <div>
          <h2>制作流程演练</h2>
          <p className={s.hint}>
            验证审批、暂停、取消与恢复。生成步骤使用模拟实现。
          </p>
        </div>
        <button
          className={s.primary}
          disabled={
            disabled ||
            !canControl ||
            !ready ||
            !!view.project.archived_at ||
            start.isPending
          }
          onClick={() => {
            setConfirmedVersions(
              heads.map(
                (h) => `${contentNames[h.entity_kind]} v${h.current.revision}`,
              ),
            );
            setConfirm({
              command_id: crypto.randomUUID(),
              execution_mode: "simulation",
              expected_row_version: view.project.row_version,
              input_refs: {
                brief: refFor("brief"),
                script: refFor("script"),
                storyboard: refFor("storyboard"),
              },
            });
          }}
        >
          启动模拟演练
        </button>
      </div>
      {!ready && (
        <p className={s.warning}>
          请先保存并批准当前需求、剧本和分镜，确认上游引用没有过期。
        </p>
      )}
      {start.error && (
        <p role="alert" className={s.error}>
          {start.error.message}
        </p>
      )}
      {confirm && (
        <section className={s.card} aria-label="确认启动演练">
          <h3>冻结以下版本并启动</h3>
          <p className={s.hint}>{confirmedVersions.join(" · ")}</p>
          <div className={s.actions}>
            <button
              className={s.primary}
              disabled={disabled || start.isPending}
              onClick={() => start.mutate()}
            >
              确认冻结并启动
            </button>
            <button
              className={s.secondary}
              disabled={start.isPending}
              onClick={() => setConfirm(null)}
            >
              返回检查
            </button>
          </div>
        </section>
      )}
      <div className={s.runList}>
        {runs.map((run) => (
          <button
            key={run.production_run_id}
            className={
              selected === run.production_run_id ? s.runSelected : s.runItem
            }
            onClick={() => setSelected(run.production_run_id)}
          >
            <strong>{statusNames[run.status]}</strong>
            <span>
              {run.completed_shots}/{run.total_shots} 镜头 ·{" "}
              {displayDate(run.created_at)}
            </span>
          </button>
        ))}
      </div>
      {(selected ?? runs[0]?.production_run_id) && (
        <RunDetails
          key={selected ?? runs[0].production_run_id}
          run_id={selected ?? runs[0].production_run_id}
          disabled={disabled}
          canControl={canControl}
        />
      )}
      {!runs.length && !selected && (
        <div className={s.empty}>暂无演练批次。完成版本审批后即可开始。</div>
      )}
    </div>
  );
}

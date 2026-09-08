import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorBox } from "../../components/ui";
import { unwrap } from "../../shared/request";
import s from "../../App.module.css";

export function Settings() {
  const qc = useQueryClient();
  const state = useQuery({
    queryKey: ["desktop"],
    queryFn: () => unwrap(window.video.state()),
  });
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => unwrap(window.video.capabilities()),
  });
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => unwrap(window.video.me()),
  });
  const execution = useQuery({
    queryKey: ["execution-status"],
    queryFn: () => unwrap(window.video.executionStatus()),
    refetchInterval: 5000,
  });
  const online = (stamp: string | null | undefined) =>
    !!stamp && Date.now() - Date.parse(stamp) < 30000;
  const logout = useMutation({
    mutationFn: () => unwrap(window.video.logout()),
    onSuccess: () => {
      qc.clear();
      void qc.invalidateQueries();
    },
  });
  return (
    <>
      <div className={s.pageHeading}>
        <div>
          <span className={s.eyebrow}>WORKSPACE SETTINGS</span>
          <h1>
            服务设置<span className={s.headingDot}>.</span>
          </h1>
          <p>查看当前设备、服务连接与可用创作能力。</p>
        </div>
      </div>
      <section className={s.settingsPanel}>
        <div className={s.panelHeading}>
          <h2>本机连接</h2>
          <span className={s.outlineTag}>本地运行</span>
        </div>
        <dl>
          <div>
            <dt>服务地址</dt>
            <dd>{state.data?.service_url}</dd>
          </div>
          <div>
            <dt>工作空间</dt>
            <dd>{me.data?.workspace_name ?? "暂不可用"}</dd>
          </div>
          <div>
            <dt>当前身份</dt>
            <dd>
              {me.data?.display_name ?? "未验证"} / {me.data?.role ?? "—"}
            </dd>
          </div>
          <div>
            <dt>桌面版本</dt>
            <dd>{state.data?.version}</dd>
          </div>
        </dl>
        <ErrorBox error={logout.error} />
        <button
          className={s.secondary}
          disabled={logout.isPending || !!state.data?.pending.length}
          onClick={() => logout.mutate()}
        >
          解除设备配对
        </button>
        <p className={s.settingsHint}>
          解除配对会撤销当前设备会话。项目数据仍保留在工作空间中。
        </p>
      </section>
      <section className={s.settingsPanel}>
        <h2>创作能力</h2>
        <ErrorBox error={capabilities.error} />
        <div className={s.capabilities}>
          {capabilities.data?.capabilities.map((capability) => (
            <div key={capability.id}>
              <span>{capability.name}</span>
              <span
                className={
                  capability.status === "ready" ? s.readyTag : s.softTag
                }
              >
                {capability.status === "ready" ? "已就绪" : "尚未接入"}
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className={s.settingsPanel}>
        <h2>演练执行服务</h2>
        <ErrorBox error={execution.error} />
        <dl>
          <div>
            <dt>Worker</dt>
            <dd>
              {online(execution.data?.last_worker_seen_at)
                ? "在线"
                : "暂无近期心跳"}
            </dd>
          </div>
          <div>
            <dt>任务投递器</dt>
            <dd>
              {online(execution.data?.last_dispatcher_seen_at)
                ? "在线"
                : "暂无近期心跳"}
            </dd>
          </div>
          <div>
            <dt>等待投递</dt>
            <dd>{execution.data?.pending ?? "—"}</dd>
          </div>
          <div>
            <dt>投递失败待处理</dt>
            <dd>{execution.data?.dead_letters ?? "—"}</dd>
          </div>
        </dl>
        <p className={s.settingsHint}>
          缺少心跳时请检查独立的 Worker
          与投递器进程。内容编辑和审批不依赖它们在线。
        </p>
      </section>
    </>
  );
}

import { useEffect, useRef } from "react";
import { NavLink, Route, Routes, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BridgeError, unwrap } from "./shared/request";
import { Icon, ErrorBox, Loading } from "./components/ui";
import { Pairing } from "./features/pairing/Pairing";
import { Projects } from "./features/projects/Projects";
import { Detail } from "./features/projects/Detail";
import { Settings } from "./features/settings/Settings";
import s from "./App.module.css";

export default function App() {
  const qc = useQueryClient();
  const state = useQuery({
    queryKey: ["desktop"],
    queryFn: () => unwrap(window.video.state()),
    refetchInterval: 5000,
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(window.video.health()),
    refetchInterval: 5000,
    retry: false,
  });
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => unwrap(window.video.me()),
    enabled: !!state.data?.paired,
    refetchInterval: 30000,
    retry: false,
  });
  const attempted = useRef(new Set<string>());
  const recovery = useMutation({
    mutationFn: (id: string) =>
      unwrap(window.video.recover({ command_id: id })),
    onSettled: () => {
      void qc.invalidateQueries();
    },
  });
  useEffect(() => {
    const pending = state.data?.pending[0];
    const attemptKey = `${pending?.command_id}:${state.data?.identity?.session_id}`;
    if (
      health.isSuccess &&
      pending &&
      !attempted.current.has(attemptKey) &&
      !recovery.isPending
    ) {
      attempted.current.add(attemptKey);
      recovery.mutate(pending.command_id);
    }
  }, [state.data, health.isSuccess]);
  useEffect(() => {
    if (health.isSuccess) void qc.invalidateQueries({ queryKey: ["me"] });
  }, [health.isSuccess, qc]);
  const pending = state.data?.pending ?? [];
  return (
    <div className={s.shell}>
      <aside className={s.sidebar}>
        <Link to="/" className={s.brand}>
          <span className={s.brandMark}>
            <Icon name="film" size={23} />
          </span>
          <span>
            Video<span className={s.brandSub}>GENERATION</span>
          </span>
        </Link>
        <div className={s.workspace}>
          <span className={s.avatar}>我</span>
          <span>
            我的工作空间<small>本机创作空间</small>
          </span>
          <span className={s.tinyDot} />
        </div>
        <div className={s.navLabel}>工作台</div>
        <nav>
          <NavLink
            to="/"
            end
            className={({ isActive }) => (isActive ? s.activeNav : s.nav)}
          >
            <Icon name="grid" />
            项目库
          </NavLink>
          <NavLink
            to="/settings"
            className={({ isActive }) => (isActive ? s.activeNav : s.nav)}
          >
            <Icon name="settings" />
            服务设置
          </NavLink>
        </nav>
        <div className={s.sidebarBottom}>
          <div className={s.phase}>
            <span className={s.phaseTag}>B1 · PART 01</span>
            <strong>从一个想法开始</strong>
            <p>编辑故事与分镜，审批后演练制作流程。</p>
            <div className={s.phaseLine} />
            <small>内容版本与流程演练</small>
          </div>
          <span className={s.footerText}>
            桌面工作台 <span>v{state.data?.version ?? "—"}</span>
          </span>
        </div>
      </aside>
      <div className={s.body}>
        <header className={s.topbar}>
          <span>
            创作空间 <span className={s.slash}>/</span> 视频工作台
          </span>
          <div className={s.topRight}>
            <span className={health.isError ? s.offline : s.online}>
              <i />
              {health.isError
                ? "服务离线"
                : health.isPending
                  ? "正在连接"
                  : "本机服务在线"}
            </span>
            <span className={s.topDivider} />
            <span className={s.smallAvatar}>C</span>
          </div>
        </header>
        <main className={s.main}>
          {health.isError && (
            <div role="status" className={s.offlineBanner}>
              本机服务暂不可用。项目数据会保留，连接恢复后可继续操作。
              <button onClick={() => void health.refetch()}>重新连接</button>
            </div>
          )}
          {pending.map((item) => (
            <div
              key={item.command_id}
              className={s.pendingBanner}
              role="status"
            >
              <div>
                <strong>{item.label} · 结果待确认</strong>
                <small>已保存原操作，恢复时会先查询执行结果。</small>
              </div>
              <button
                disabled={recovery.isPending}
                onClick={() => recovery.mutate(item.command_id)}
              >
                {recovery.isPending ? "正在恢复…" : "恢复操作"}
              </button>
            </div>
          ))}
          <ErrorBox error={recovery.error} />
          {state.isPending ? (
            <Loading />
          ) : state.isError ? (
            <ErrorBox error={state.error} />
          ) : !state.data?.paired ||
            (me.error instanceof BridgeError &&
              me.error.detail.code === "UNAUTHENTICATED") ? (
            <Pairing />
          ) : (
            <>
              {me.error && (
                <div className={s.error}>
                  设备身份无法验证：{me.error.message}{" "}
                  <Link to="/settings">前往服务设置</Link>
                </div>
              )}
              <Routes>
                <Route
                  path="/"
                  element={
                    <Projects disabled={health.isError || !!pending.length} />
                  }
                />
                <Route
                  path="/projects/:id"
                  element={
                    <Detail disabled={health.isError || !!pending.length} />
                  }
                />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Link to="/">返回项目库</Link>} />
              </Routes>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

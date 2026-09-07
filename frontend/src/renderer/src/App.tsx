import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
  Link,
} from "react-router-dom";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { create } from "zustand";
import type { Fault, Project, Reply, Schema } from "../../shared/bridge";
import s from "./App.module.css";

class BridgeError extends Error {
  constructor(public detail: Fault) {
    super(detail.message);
  }
}
async function unwrap<T>(result: Promise<Reply<T>>): Promise<T> {
  const reply = await result;
  if (!reply.ok) throw new BridgeError(reply.error);
  return reply.data;
}
const useUi = create<{
  archived: boolean;
  setArchived: (value: boolean) => void;
}>((set) => ({
  archived: false,
  setArchived: (archived) => set({ archived }),
}));
function Icon({
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
function ErrorBox({ error }: { error: Error | null }) {
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
function Modal({
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
const date = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

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
            <span className={s.phaseTag}>PHASE 01</span>
            <strong>从一个想法开始</strong>
            <p>建立项目，整理你的下一支短片。</p>
            <div className={s.phaseLine} />
            <small>项目管理已就绪</small>
          </div>
          <span className={s.footerText}>
            桌面工作台 <span>v0.1.0</span>
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
function Loading() {
  return (
    <div className={s.loading} role="status">
      <div className={s.spinner} />
      正在读取工作空间…
    </div>
  );
}

function Pairing() {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      unwrap(
        window.video.pair({
          pairing_code: code.trim(),
          device_name: "我的桌面",
        }),
      ),
    onSuccess: () => {
      setCode("");
      void qc.invalidateQueries();
    },
  });
  return (
    <div className={s.pairLayout}>
      <div>
        <span className={s.eyebrow}>YOUR NEXT STORY STARTS HERE</span>
        <h1 className={s.pairTitle}>
          让想法，
          <br />
          成为下一支短片。
        </h1>
        <p className={s.lead}>
          连接本机创作服务，
          <br />
          为你的故事建立一个专属项目。
        </p>
        <div className={s.pairArt}>
          <div />
          <div />
          <div />
          <span>IDEA → STORY → VIDEO</span>
        </div>
      </div>
      <section className={s.pairCard}>
        <span className={s.stepNumber}>01 / CONNECT</span>
        <h2>配对你的设备</h2>
        <p>在项目目录运行下方命令，获取一次性配对码。</p>
        <code>.\scripts\dev.ps1 pair</code>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <label htmlFor="pair-code">一次性配对码</label>
          <input
            id="pair-code"
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
            placeholder="粘贴配对码"
            required
            minLength={16}
            maxLength={256}
          />
          <ErrorBox error={mutation.error} />
          <button className={s.primary} disabled={mutation.isPending}>
            {mutation.isPending ? "正在配对…" : "连接工作空间"}
            <Icon name="arrow" />
          </button>
        </form>
        <small>配对码 10 分钟内有效 · 凭据由系统加密保存</small>
      </section>
    </div>
  );
}

function Projects({ disabled }: { disabled: boolean }) {
  const { archived, setArchived } = useUi();
  const [showCreate, setShowCreate] = useState(false);
  const query = useInfiniteQuery({
    queryKey: ["projects", archived],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        window.video.projects({
          archived,
          ...(pageParam ? { cursor: pageParam } : {}),
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: (query) =>
      query.state.error ? 10000 : document.hidden ? 5000 : 1000,
  });
  const projects = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <div className={s.pageHeading}>
        <div>
          <span className={s.eyebrow}>YOUR CREATIVE SPACE</span>
          <h1>
            项目库<span className={s.headingDot}>.</span>
          </h1>
          <p>每一个好故事，都从这里开始。</p>
        </div>
        <button
          className={s.primary}
          disabled={disabled}
          onClick={() => setShowCreate(true)}
        >
          <Icon name="plus" />
          新建项目
        </button>
      </div>
      <section className={s.hero}>
        <div>
          <span className={s.heroLabel}>把灵感放进项目</span>
          <h2>一个想法，一段新的旅程。</h2>
          <p>为下一支短片命名，建立属于你的创作空间。</p>
          <span className={s.profileTag}>
            中文解说 <b>·</b> 9:16 竖屏 <b>·</b> 30–60 秒
          </span>
        </div>
        <div className={s.heroArt} aria-hidden="true">
          <div className={s.frameBack} />
          <div className={s.frameFront}>
            <span>
              STORY
              <br />
              IN THE
              <br />
              <em>MAKING.</em>
            </span>
            <i>01 — ∞</i>
          </div>
          <div className={s.orbit} />
        </div>
      </section>
      <div className={s.listToolbar}>
        <div className={s.tabs}>
          <button
            className={!archived ? s.selectedTab : ""}
            onClick={() => setArchived(false)}
          >
            进行中{" "}
            {!archived && query.data && (
              <span>{query.data.pages[0].total}</span>
            )}
          </button>
          <button
            className={archived ? s.selectedTab : ""}
            onClick={() => setArchived(true)}
          >
            已归档{" "}
            {archived && query.data && <span>{query.data.pages[0].total}</span>}
          </button>
        </div>
        <span className={s.sortLabel}>按创建时间排序 ↓</span>
      </div>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : !projects.length && !query.error ? (
        <div className={s.empty}>
          <span className={s.emptyIcon}>
            <Icon name={archived ? "archive" : "film"} size={32} />
          </span>
          <h3>{archived ? "还没有归档项目" : "你的第一个故事，等待开场"}</h3>
          <p>
            {archived
              ? "归档后的项目会保存在这里，随时可以恢复。"
              : "建立一个项目，为灵感留一个位置。"}
          </p>
          {!archived && (
            <button
              className={s.secondary}
              disabled={disabled}
              onClick={() => setShowCreate(true)}
            >
              创建第一个项目
              <Icon name="arrow" size={16} />
            </button>
          )}
        </div>
      ) : (
        <div className={s.projectGrid}>
          {projects.map((project, index) => (
            <Link
              className={s.projectCard}
              key={project.project_id}
              to={`/projects/${project.project_id}`}
            >
              <div className={`${s.projectVisual} ${s["color" + (index % 3)]}`}>
                <span className={s.cardNumber}>
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className={s.paperFrame}>
                  <Icon name="film" size={35} />
                </div>
                <span className={s.visualLabel}>等待你的故事</span>
                <span className={s.format}>9:16</span>
              </div>
              <div className={s.cardInfo}>
                <div>
                  <h3>{project.title}</h3>
                  <Icon name="arrow" size={18} />
                </div>
                <p>
                  <span className={s.statusTag}>
                    {project.archived_at ? "已归档" : "准备创作"}
                  </span>
                  <span>{date(project.updated_at)}</span>
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
      {query.hasNextPage && (
        <button
          className={s.loadMore}
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          加载更多项目
        </button>
      )}
      <div className={s.pageFoot}>
        <span>灵感由你发起，故事逐步成形。</span>
        <span>LOCAL WORKSPACE</span>
      </div>
      {showCreate && <ProjectForm close={() => setShowCreate(false)} />}
    </>
  );
}

function ProjectForm({
  project,
  close,
}: {
  project?: Project;
  close: () => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [title, setTitle] = useState(project?.title ?? "");
  const [version, setVersion] = useState(project?.row_version ?? 1);
  const [latest, setLatest] = useState<Project | null>(null);
  const mutation = useMutation({
    mutationFn: () =>
      project
        ? unwrap(
            window.video.update({
              project_id: project.project_id,
              command: {
                command_id: crypto.randomUUID(),
                expected_row_version: version,
                title: title.trim(),
              },
            }),
          )
        : unwrap(
            window.video.create({
              command_id: crypto.randomUUID(),
              title: title.trim(),
            }),
          ),
    onSuccess: (result) => {
      close();
      if (result.project) navigate(`/projects/${result.project.project_id}`);
    },
    onError: async (error) => {
      if (
        project &&
        error instanceof BridgeError &&
        error.detail.code === "VERSION_CONFLICT"
      ) {
        const reply = await window.video.snapshot({
          project_id: project.project_id,
        });
        if (reply.ok) setLatest(reply.data.project);
      }
    },
    onSettled: () => {
      void qc.invalidateQueries();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  return (
    <Modal title={project ? "重命名项目" : "新建项目"} close={close}>
      <form onSubmit={submit} className={s.projectForm}>
        <p>
          {project
            ? "一个清晰的名字，让故事更容易被找到。"
            : "先给你的故事起个名字，细节可以稍后完善。"}
        </p>
        <label htmlFor="project-title">项目名称</label>
        <input
          id="project-title"
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="例如：城市慢游 · 雨后的杭州"
          required
          maxLength={200}
        />
        <span className={s.inputHint}>{title.length} / 200</span>
        {!project && (
          <div className={s.profileSummary}>
            <Icon name="film" />
            <div>
              <strong>中文解说 · 竖屏短片</strong>
              <small>720 × 1280 · 24 fps · 30–60 秒</small>
            </div>
            <span>默认规格</span>
          </div>
        )}
        <ErrorBox error={mutation.error} />
        {latest && (
          <div className={s.conflict}>
            <strong>当前已保存：{latest.title}</strong>
            <p>你的输入：{title}</p>
            <button
              type="button"
              className={s.secondary}
              onClick={() => {
                setVersion(latest.row_version);
                setLatest(null);
                mutation.reset();
              }}
            >
              以最新版本为基础继续编辑
            </button>
          </div>
        )}
        <div className={s.formActions}>
          <button type="button" className={s.secondary} onClick={close}>
            取消
          </button>
          <button
            className={s.primary}
            disabled={mutation.isPending || !title.trim() || !!latest}
          >
            {mutation.isPending
              ? "正在保存…"
              : project
                ? "保存名称"
                : "创建项目"}
            <Icon name="arrow" size={17} />
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Detail({ disabled }: { disabled: boolean }) {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [rename, setRename] = useState(false);
  const snapshot = useQuery({
    queryKey: ["snapshot", id],
    queryFn: () => unwrap(window.video.snapshot({ project_id: id })),
  });
  useEffect(() => {
    if (!snapshot.data) return;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      cursor = snapshot.data.event_cursor,
      delay = 1000;
    const poll = async () => {
      const result = await window.video.events({
        project_id: id,
        after: cursor,
      });
      if (stopped) return;
      if (result.ok) {
        delay = document.hidden ? 5000 : 1000;
        if (result.data.items.length) {
          cursor = result.data.next_cursor;
          void qc.invalidateQueries({ queryKey: ["snapshot", id] });
        }
      } else {
        delay = Math.min(delay * 2, 30000);
        if (result.error.code === "SNAPSHOT_REQUIRED")
          void qc.invalidateQueries({ queryKey: ["snapshot", id] });
      }
      timer = setTimeout(poll, delay);
    };
    timer = setTimeout(poll, delay);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id, snapshot.data?.event_cursor, qc]);
  const events = useQuery({
    queryKey: ["events", id, snapshot.data?.event_cursor],
    enabled: !!snapshot.data,
    queryFn: () =>
      unwrap(
        window.video.events({
          project_id: id,
          after: Math.max(0, (snapshot.data?.event_cursor ?? 0) - 5),
        }),
      ),
  });
  const archive = useMutation({
    mutationFn: () =>
      unwrap(
        window.video.update({
          project_id: id,
          command: {
            command_id: crypto.randomUUID(),
            expected_row_version: snapshot.data!.project.row_version,
            archived: !snapshot.data!.project.archived_at,
          },
        }),
      ),
    onSettled: () => {
      void qc.invalidateQueries();
    },
  });
  if (snapshot.isPending) return <Loading />;
  if (!snapshot.data)
    return (
      <>
        <Link to="/" className={s.back}>
          ← 返回项目库
        </Link>
        <ErrorBox error={snapshot.error} />
        <button className={s.secondary} onClick={() => void snapshot.refetch()}>
          重新加载
        </button>
      </>
    );
  const project = snapshot.data.project;
  return (
    <>
      <Link to="/" className={s.back}>
        ← 返回项目库
      </Link>
      <div className={s.pageHeading}>
        <div>
          <span className={s.eyebrow}>
            PROJECT / {project.archived_at ? "ARCHIVED" : "READY TO CREATE"}
          </span>
          <h1 className={s.projectTitle}>{project.title}</h1>
          <p>
            创建于 {date(project.created_at)} <span className={s.slash}>/</span>{" "}
            {project.archived_at ? "已归档" : "准备创作"}
          </p>
        </div>
        <div className={s.actions}>
          <button
            className={s.secondary}
            disabled={disabled}
            onClick={() => setRename(true)}
          >
            重命名
          </button>
          <button
            className={s.secondary}
            disabled={disabled || archive.isPending}
            onClick={() => archive.mutate()}
          >
            <Icon name="archive" size={16} />
            {project.archived_at ? "恢复项目" : "归档"}
          </button>
        </div>
      </div>
      <ErrorBox error={archive.error} />
      <ErrorBox error={snapshot.error} />
      <div className={s.detailGrid}>
        <section className={s.storyPanel}>
          <div className={s.panelHeading}>
            <h2>创作旅程</h2>
            <span className={s.outlineTag}>项目已建立</span>
          </div>
          <div className={s.journey}>
            {["建立项目", "故事与分镜", "镜头生成", "配音与合成"].map(
              (name, index) => (
                <div
                  key={name}
                  className={index === 0 ? s.journeyActive : s.journeyStep}
                >
                  <span>
                    {index === 0 ? (
                      <Icon name="check" size={17} />
                    ) : (
                      `0${index + 1}`
                    )}
                  </span>
                  <strong>{name}</strong>
                  <small>{index === 0 ? "已完成" : "后续阶段"}</small>
                </div>
              ),
            )}
          </div>
          <div className={s.storyEmpty}>
            <div className={s.storyFrame}>
              <Icon name="film" size={44} />
            </div>
            <h2>故事的舞台，准备好了。</h2>
            <p>
              项目已保存。故事规划、镜头生成和成片合成
              <br />
              将在后续开发阶段逐步接入。
            </p>
            <span className={s.softTag}>当前可管理项目名称与归档状态</span>
          </div>
        </section>
        <aside className={s.detailAside}>
          <section className={s.specPanel}>
            <h3>成片规格</h3>
            <span className={s.specFormat}>
              9<span>:</span>16
            </span>
            <dl>
              <div>
                <dt>内容类型</dt>
                <dd>中文解说短片</dd>
              </div>
              <div>
                <dt>分辨率</dt>
                <dd>720 × 1280</dd>
              </div>
              <div>
                <dt>帧率</dt>
                <dd>24 fps</dd>
              </div>
              <div>
                <dt>目标时长</dt>
                <dd>30–60 秒</dd>
              </div>
            </dl>
          </section>
          <section className={s.activity}>
            <h3>最近动态</h3>
            <ErrorBox error={events.error} />
            {events.data?.items
              .slice()
              .reverse()
              .map((event) => (
                <div className={s.event} key={event.event_id}>
                  <i />
                  <div>
                    <strong>
                      {event.type === "project.created"
                        ? "项目已建立"
                        : "项目信息已更新"}
                    </strong>
                    <small>{date(event.occurred_at)}</small>
                  </div>
                </div>
              ))}
          </section>
        </aside>
      </div>
      <div className={s.pageFoot}>
        <span>项目数据保存在本机工作空间</span>
        <span>PROJECT / {project.project_id.slice(0, 8).toUpperCase()}</span>
      </div>
      {rename && (
        <ProjectForm project={project} close={() => setRename(false)} />
      )}
    </>
  );
}

function Settings() {
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
    </>
  );
}

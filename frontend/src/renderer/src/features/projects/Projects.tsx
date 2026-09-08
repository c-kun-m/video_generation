import { useState } from "react";
import { Link } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ErrorBox, Icon, Loading, date } from "../../components/ui";
import { useUi } from "./state";
import { ProjectForm } from "./ProjectForm";
import { unwrap } from "../../shared/request";
import s from "../../App.module.css";

export function Projects({ disabled }: { disabled: boolean }) {
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

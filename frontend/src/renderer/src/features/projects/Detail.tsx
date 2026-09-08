import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorBox, Icon, Loading, date } from "../../components/ui";
import { ProjectForm } from "./ProjectForm";
import { Workbench } from "../workbench/Workbench";
import { unwrap } from "../../shared/request";
import s from "../../App.module.css";

export function Detail({ disabled }: { disabled: boolean }) {
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
      <Workbench view={snapshot.data} disabled={disabled} />
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

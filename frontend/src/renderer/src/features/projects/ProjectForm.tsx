import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Project } from "../../../../shared/bridge";
import { BridgeError } from "../../shared/request";
import { ErrorBox, Icon, Modal } from "../../components/ui";
import { unwrap } from "../../shared/request";
import s from "../../App.module.css";

export function ProjectForm({
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
